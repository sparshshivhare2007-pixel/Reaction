from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - imported lazily by workers
    from pyrogram.client import Client
    from pyrogram.errors import (
        BadRequest,
        ChannelPrivate,
        FloodWait,
        PeerIdInvalid,
        RPCError,
        UsernameInvalid,
        UsernameNotOccupied,
    )


@dataclass(frozen=True)
class NormalizedTarget:
    """Lightweight representation of a Telegram target extracted from a URL."""

    raw: str
    username: str | None
    kind: str
    message_id: int | None = None
    invite: str | None = None
    supported: bool = True

    def cache_key(self) -> str | None:
        return self.username.lower() if self.username else None


@dataclass
class FailureRecord:
    reason: str
    expires_at: datetime


_failure_cache: dict[str, FailureRecord] = {}
_FAILURE_TTL = timedelta(hours=6)


def _clean_failure_cache() -> None:
    now = datetime.now(timezone.utc)
    expired = [key for key, record in _failure_cache.items() if record.expires_at <= now]
    for key in expired:
        _failure_cache.pop(key, None)


def normalize_telegram_target(url: str) -> NormalizedTarget:
    """Parse Telegram URLs into a normalized target.

    Supports usernames (t.me/<username>), public message links (t.me/<username>/<msg>),
    join-chat links (t.me/+<code> or t.me/joinchat/<code>) and ignores unsupported
    formats by marking them as ``supported=False`` so the worker can skip them.
    """

    from urllib.parse import urlparse

    raw = url.strip()
    parsed = urlparse(raw if raw.startswith("http") else f"https://{raw}")
    path_parts = [part for part in parsed.path.split("/") if part]

    if not parsed.netloc.endswith("t.me") or not path_parts:
        # Treat plain usernames as a username target
        username = raw.lstrip("@")
        return NormalizedTarget(raw=raw, username=username or None, kind="username")

    # Join-chat/invite links
    if path_parts[0].startswith("+"):
        return NormalizedTarget(raw=raw, username=None, kind="invite", invite=path_parts[0], supported=False)

    if path_parts[0].lower() == "joinchat" and len(path_parts) >= 2:
        return NormalizedTarget(raw=raw, username=None, kind="invite", invite=path_parts[1], supported=False)

    # Message links – we only care about the username for reporting
    if len(path_parts) >= 2 and path_parts[1].isdigit():
        return NormalizedTarget(
            raw=raw,
            username=path_parts[0].lstrip("@"),
            kind="message",
            message_id=int(path_parts[1]),
        )

    username = path_parts[0].lstrip("@")
    return NormalizedTarget(raw=raw, username=username, kind="username")


async def resolve_chat(
    client: "Client",
    target: NormalizedTarget,
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
) -> int | None:
    """Resolve a normalized target to a chat id with sensible retries.

    Permanent failures are cached for ``_FAILURE_TTL`` to avoid endless retries/log spam.
    """

    cache_key = target.cache_key()
    _clean_failure_cache()

    if not target.supported:
        logging.info("Skipping unsupported target %s (%s)", target.raw, target.kind)
        return None

    if cache_key and cache_key in _failure_cache:
        record = _failure_cache[cache_key]
        if record.expires_at > datetime.now(timezone.utc):
            logging.info("Skipping cached failure for %s: %s", cache_key, record.reason)
            return None

    attempts = 0
    last_reason: str | None = None

    while attempts < max_attempts:
        attempts += 1
        try:
            chat = await client.get_chat(target.username)
            resolved = await client.resolve_peer(chat.id)
            if hasattr(resolved, "user_id"):
                return int(getattr(resolved, "user_id"))
            if hasattr(resolved, "channel_id"):
                return int(f"-100{getattr(resolved, 'channel_id')}")
            if hasattr(resolved, "chat_id"):
                return int(getattr(resolved, "chat_id"))
            return int(resolved)
        except Exception as exc:  # noqa: BLE001 - deliberate branching
            from pyrogram.errors import (
                BadRequest,
                ChannelPrivate,
                FloodWait,
                PeerIdInvalid,
                RPCError,
                UsernameInvalid,
                UsernameNotOccupied,
            )

            if isinstance(exc, FloodWait):
                wait_seconds = min(getattr(exc, "value", 1), 60)
                logging.warning(
                    "Flood wait resolving %s via %s (attempt %s/%s): %ss",
                    target.raw,
                    getattr(client, "name", "client"),
                    attempts,
                    max_attempts,
                    wait_seconds,
                )
                await asyncio.sleep(wait_seconds)
                continue

            if isinstance(exc, (PeerIdInvalid, UsernameNotOccupied, UsernameInvalid, ChannelPrivate)):
                last_reason = exc.__class__.__name__
                if cache_key:
                    _failure_cache[cache_key] = FailureRecord(
                        reason=last_reason,
                        expires_at=datetime.now(timezone.utc) + _FAILURE_TTL,
                    )
                logging.warning(
                    "Permanent peer failure for %s via %s: %s",
                    target.raw,
                    getattr(client, "name", "client"),
                    exc,
                )
                return None

            if isinstance(exc, BadRequest):
                last_reason = exc.__class__.__name__
                if cache_key:
                    _failure_cache[cache_key] = FailureRecord(
                        reason=last_reason,
                        expires_at=datetime.now(timezone.utc) + _FAILURE_TTL,
                    )
                logging.warning("Bad request resolving %s: %s", target.raw, exc)
                return None

            # Transient RPC/network errors
            backoff = min(max_delay, base_delay * (2 ** (attempts - 1)))
            jitter = random.uniform(0, backoff / 2)
            delay = backoff + jitter
            logging.warning(
                "Transient resolution failure for %s via %s (attempt %s/%s): %s; retrying in %.1fs",
                target.raw,
                getattr(client, "name", "client"),
                attempts,
                max_attempts,
                exc.__class__.__name__,
                delay,
            )
            await asyncio.sleep(delay)

    if cache_key and last_reason:
        _failure_cache[cache_key] = FailureRecord(
            reason=last_reason,
            expires_at=datetime.now(timezone.utc) + _FAILURE_TTL,
        )
    return None


async def report_target(
    clients: list["Client"],
    target_url: str,
    *,
    invite_link: str | None = None,
) -> tuple[int | None, NormalizedTarget]:
    """Normalize and resolve a target across multiple clients.

    Returns a tuple of (chat_id, NormalizedTarget). chat_id is ``None`` when the
    target cannot be resolved or is unsupported.
    """

    target = normalize_telegram_target(target_url)

    if invite_link and target.invite is None and not target.supported:
        # Invite links are handled elsewhere; this prevents confusion when a
        # private join link is passed alongside a username target.
        logging.info("Received invite link but target is unsupported: %s", target_url)

    for client in clients:
        chat_id = await resolve_chat(client, target)
        if chat_id is not None:
            return chat_id, target

    logging.info("All clients failed to resolve target %s", target.raw)
    return None, target


__all__ = [
    "NormalizedTarget",
    "normalize_telegram_target",
    "resolve_chat",
    "report_target",
]
