from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

from pyrogram import Client, filters
from pyrogram.errors import (
    AuthKeyUnregistered,
    BadRequest,
    ChannelPrivate,
    ChatAdminRequired,
    ChatWriteForbidden,
    FloodWait,
    MessageIdInvalid,
    RPCError,
    SessionDeactivated,
    UserBannedInChannel,
    UserDeactivated,
    UserDeactivatedBan,
    UsernameNotOccupied,
)
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import config
from report import send_report


app = Client("my_session", api_id=config.API_ID, api_hash=config.API_HASH)


TARGET_MENU = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("Public", callback_data="public")],
        [InlineKeyboardButton("Private", callback_data="private")],
    ]
)


@dataclass
class UserState:
    stage: str = "session_verification"
    target_type: Optional[str] = None
    invite_link: Optional[str] = None
    last_target: Optional[str] = None
    join_status: str = "join not attempted"
    errors: list[Tuple[str, str]] = field(default_factory=list)

    def reset_target(self) -> None:
        self.target_type = None
        self.invite_link = None
        self.last_target = None
        self.join_status = "join not attempted"
        self.errors.clear()


user_states: Dict[int, UserState] = {}


def _clean_url(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned and not cleaned.startswith("http"):
        return f"https://{cleaned}"
    return cleaned


def parse_invite_link(url: str) -> str:
    cleaned = _clean_url(url)
    parsed = urlparse(cleaned)
    path = parsed.path.rstrip("/")
    if not parsed.netloc.endswith("t.me"):
        raise ValueError("Invalid link format: expected t.me domain")

    if path.startswith("/+"):
        return f"https://t.me{path}"

    if path.startswith("/joinchat/"):
        return f"https://t.me{path}"

    raise ValueError("Invalid link format: not an invite link")


def parse_public_message_link(url: str) -> tuple[str | int, int]:
    cleaned = _clean_url(url)
    parsed = urlparse(cleaned)
    parts = [p for p in parsed.path.split("/") if p]
    if not parsed.netloc.endswith("t.me") or len(parts) < 2:
        raise ValueError("Invalid link format: expected public message link")

    if parts[0] == "c" and len(parts) >= 3:
        chat_id = int(f"-100{parts[1]}")
        return chat_id, int(parts[2])

    chat_username = parts[0]
    message_id = int(parts[1])
    return chat_username, message_id


def parse_private_message_link(url: str) -> tuple[int, int]:
    cleaned = _clean_url(url)
    parsed = urlparse(cleaned)
    parts = [p for p in parsed.path.split("/") if p]
    if not parsed.netloc.endswith("t.me") or len(parts) < 3 or parts[0] != "c":
        raise ValueError("Invalid link format: expected private message link")

    chat_id = int(f"-100{parts[1]}")
    return chat_id, int(parts[2])


def categorize_exception(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, FloodWait):
        return "FloodWait", f"Flood wait {getattr(exc, 'value', '')}"

    if isinstance(exc, (UserDeactivated, UserDeactivatedBan, SessionDeactivated, AuthKeyUnregistered)):
        return "Client banned / deactivated", str(exc)

    if isinstance(exc, MessageIdInvalid):
        return "Message not found / deleted", str(exc)

    if isinstance(exc, ValueError):
        return "Invalid link format", str(exc)

    if isinstance(exc, (ChannelPrivate, ChatAdminRequired, ChatWriteForbidden, UserBannedInChannel)):
        return "Valid link but access denied", str(exc)

    if isinstance(exc, UsernameNotOccupied):
        return "Valid link but access denied", "Chat not found"

    if isinstance(exc, (BadRequest, RPCError)):
        return "Valid link but access denied", str(exc)

    return "Valid link but access denied", str(exc)


def _map_chat_type(chat_type: str | None) -> str:
    if not chat_type:
        return "Unknown"
    if chat_type.lower() in {"channel"}:
        return "Channel"
    if chat_type.lower() in {"group", "supergroup"}:
        return "Group"
    return chat_type.title()


async def send_target_menu(message: Message) -> None:
    await message.reply_text(
        "Select target type (public or private).",
        reply_markup=TARGET_MENU,
    )


async def send_session_prompt(message: Message) -> None:
    me = await app.get_me()
    await message.reply_text(
        "Session verification required."
        f"\nUser session: @{me.username or me.first_name} (ID: {me.id})."
        "\nConfirm this is the authorized account. Reply with 'verify' to proceed or 'login' if you need to relogin.",
        reply_markup=TARGET_MENU,
    )


async def report_validation_result(message: Message, *, target_type: str, chat_type: str, chat_identifier: str,
                                   message_id: int, join_status: str, errors: list[Tuple[str, str]], validated: bool) -> None:
    success_join = 1 if "joined successfully" in join_status or "already" in join_status else 0
    failed_join = 0 if success_join else 1
    error_lines = [f"• {category}: {detail}" for category, detail in errors] or ["• None"]

    summary = (
        "Target validation\n"
        f"- Target type: {target_type.title()}\n"
        f"- Chat type: {chat_type}\n"
        f"- Chat identifier: {chat_identifier}\n"
        f"- Message ID: {message_id}\n"
        f"- Join status: {join_status}\n"
        f"- Sessions joined: {success_join}\n"
        f"- Sessions failed: {failed_join}\n"
        f"- Errors:\n" + "\n".join(error_lines)
    )

    await message.reply_text(summary)

    if validated:
        try:
            await send_report(app, chat_identifier, message_id, reason=5, reason_text="Automated moderation report")
            await message.reply_text(
                "Reporting system engaged. Moderation/abuse report submitted using configured logic.")
        except Exception as exc:  # pragma: no cover - defensive
            category, detail = categorize_exception(exc)
            await message.reply_text(f"Reporting failed. {category}: {detail}")


@app.on_message(filters.command("start"))
async def start_handler(_: Client, message: Message) -> None:
    state = user_states.setdefault(message.from_user.id, UserState())
    state.stage = "session_verification"
    state.reset_target()
    await send_session_prompt(message)


@app.on_callback_query(filters.regex("^(private|public)$"))
async def menu_callback_handler(_: Client, callback_query: CallbackQuery) -> None:
    user = callback_query.from_user
    state = user_states.setdefault(user.id, UserState())

    if state.stage == "session_verification":
        await callback_query.answer("Verify the session first.", show_alert=True)
        return

    choice = callback_query.data
    state.target_type = choice
    state.invite_link = None
    state.last_target = None
    state.errors.clear()
    if choice == "private":
        state.stage = "waiting_invite"
        await callback_query.message.reply_text(
            "STEP 2 — Target Type: Private selected. Send the private invite link (https://t.me/+HASH or https://t.me/joinchat/HASH)."
        )
    else:
        state.stage = "waiting_public_link"
        await callback_query.message.reply_text(
            "STEP 2 — Target Type: Public selected. Send the public Telegram message link (https://t.me/username/123 or https://t.me/c/123456789/456)."
        )

    await callback_query.answer()


async def handle_session_verification(message: Message, state: UserState) -> None:
    normalized = (message.text or "").strip().lower()
    if normalized == "verify":
        state.stage = "target_selection"
        await message.reply_text("Session verified. Proceed to target selection.")
        await send_target_menu(message)
        return

    if normalized == "login":
        await message.reply_text(
            "Update the session string and restart the client to relogin. Reply 'verify' after relogin.")
        return

    await message.reply_text("Awaiting verification. Reply with 'verify' to continue or 'login' to relogin.")


async def attempt_join(chat_ref, *, via_invite: Optional[str]) -> tuple[str, list[Tuple[str, str]]]:
    errors: list[Tuple[str, str]] = []
    try:
        if via_invite:
            await app.join_chat(via_invite)
        else:
            await app.join_chat(chat_ref)
        return "joined successfully", errors
    except Exception as exc:  # pragma: no cover - network dependent
        category, detail = categorize_exception(exc)
        errors.append((category, detail))
        return f"failed ({detail})", errors


async def validate_public_target(message: Message, state: UserState) -> None:
    try:
        chat_ref, message_id = parse_public_message_link(message.text)
    except Exception as exc:
        category, detail = categorize_exception(exc)
        await report_validation_result(
            message,
            target_type="Public",
            chat_type="Unknown",
            chat_identifier=message.text or "",
            message_id=0,
            join_status="failed",
            errors=[(category, detail)],
            validated=False,
        )
        return

    errors: list[Tuple[str, str]] = []
    join_status, join_errors = await attempt_join(chat_ref, via_invite=None)
    errors.extend(join_errors)

    chat_identifier = chat_ref if isinstance(chat_ref, str) else f"/c/{str(chat_ref)[4:]}"
    chat_type = "Unknown"
    try:
        chat = await app.get_chat(chat_ref)
        chat_type = _map_chat_type(getattr(chat, "type", None))
    except Exception as exc:  # pragma: no cover - network dependent
        category, detail = categorize_exception(exc)
        errors.append((category, detail))

    validated = False
    try:
        await app.get_messages(chat_ref, message_id)
        validated = len(errors) == 0
    except Exception as exc:  # pragma: no cover - network dependent
        category, detail = categorize_exception(exc)
        errors.append((category, detail))

    await report_validation_result(
        message,
        target_type="Public",
        chat_type=chat_type,
        chat_identifier=chat_identifier,
        message_id=message_id,
        join_status=join_status,
        errors=errors,
        validated=validated,
    )
    state.reset_target()
    state.stage = "target_selection"
    await send_target_menu(message)


async def validate_private_target(message: Message, state: UserState) -> None:
    if state.stage == "waiting_invite":
        try:
            invite_link = parse_invite_link(message.text)
        except Exception as exc:
            category, detail = categorize_exception(exc)
            await message.reply_text(f"Invite link error — {category}: {detail}")
            return

        state.invite_link = invite_link
        state.stage = "waiting_private_link"
        await message.reply_text(
            "Invite link recorded. Send the private message link (https://t.me/c/123456789/456)."
        )
        return

    if state.stage != "waiting_private_link":
        await message.reply_text("Select target type first.")
        return

    try:
        chat_id, message_id = parse_private_message_link(message.text)
    except Exception as exc:
        category, detail = categorize_exception(exc)
        await report_validation_result(
            message,
            target_type="Private",
            chat_type="Unknown",
            chat_identifier=message.text or "",
            message_id=0,
            join_status="failed",
            errors=[(category, detail)],
            validated=False,
        )
        return

    errors: list[Tuple[str, str]] = []
    join_status, join_errors = await attempt_join(chat_id, via_invite=state.invite_link)
    errors.extend(join_errors)

    chat_identifier = f"/c/{str(chat_id)[4:]}"
    chat_type = "Unknown"
    try:
        chat = await app.get_chat(chat_id)
        chat_type = _map_chat_type(getattr(chat, "type", None))
    except Exception as exc:  # pragma: no cover - network dependent
        category, detail = categorize_exception(exc)
        errors.append((category, detail))

    validated = False
    try:
        await app.get_messages(chat_id, message_id)
        validated = len(errors) == 0
    except Exception as exc:  # pragma: no cover - network dependent
        category, detail = categorize_exception(exc)
        errors.append((category, detail))

    await report_validation_result(
        message,
        target_type="Private",
        chat_type=chat_type,
        chat_identifier=chat_identifier,
        message_id=message_id,
        join_status=join_status,
        errors=errors,
        validated=validated,
    )
    state.reset_target()
    state.stage = "target_selection"
    await send_target_menu(message)


@app.on_message(filters.text & ~filters.command("start"))
async def message_handler(_: Client, message: Message) -> None:
    state = user_states.setdefault(message.from_user.id, UserState())

    if state.stage == "session_verification":
        await handle_session_verification(message, state)
        return

    if state.target_type == "private":
        await validate_private_target(message, state)
        return

    if state.target_type == "public":
        await validate_public_target(message, state)
        return

    await message.reply_text("Use /start to initiate the flow.", reply_markup=TARGET_MENU)


if __name__ == "__main__":
    app.run()
