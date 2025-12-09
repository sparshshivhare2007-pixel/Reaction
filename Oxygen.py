"""Implementation of the Secure Engagement Protocol (SEP).

This module encodes the configuration and UI/UX behaviors described
in `SECURE_ENGAGEMENT_PROTOCOL.md`. It offers small helpers for
reaction limiting and single-session enforcement so that the rules can
be exercised in code as well as referenced by UI layers.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional

# ---------------------------------------------------------------------------
# UI copy (Part 3: Text Summary for Direct Integration)
# ---------------------------------------------------------------------------
REACTION_LIMIT_TITLE = "Max Reaction Limit Reached"
REACTION_LIMIT_BODY = "You have reached the maximum limit of 5 reactions for this content."
SESSION_ALERT_TITLE = "Session Terminated"
SESSION_ALERT_BODY = (
    "You have logged in on another device. Your session on this device has been "
    "automatically closed to enforce the maximum concurrent session limit."
)
SESSION_ALERT_BUTTON = "Got It"
WELCOME_BACK_TOAST = "Welcome back!"


# ---------------------------------------------------------------------------
# Configuration enforcement (Part 1: System Configuration)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SEPConfig:
    """Immutable view of the SEP configuration.

    Environment variables may be supplied, but any deviations from the
    mandated values will raise an error to preserve the hard limits.
    """

    max_reactions_per_resource: int = 5
    max_concurrent_sessions: int = 1
    mass_reaction_prevention: bool = True

    @classmethod
    def load_from_env(cls, environ: Optional[Dict[str, str]] = None) -> "SEPConfig":
        env = environ or os.environ
        expected = {
            "SEP_MAX_REACTIONS_PER_RESOURCE": "5",
            "SEP_MAX_CONCURRENT_SESSIONS": "1",
            "SEP_MASS_REACTION_PREVENTION": "TRUE",
        }

        for key, expected_value in expected.items():
            actual_value = env.get(key, expected_value)
            if str(actual_value).upper() != expected_value:
                raise ValueError(
                    f"{key} must remain locked at {expected_value}; received {actual_value!r}."
                )

        return cls()


# ---------------------------------------------------------------------------
# Reaction limiting helper (Part 2: Reaction Limit Enforcement UI)
# ---------------------------------------------------------------------------
@dataclass
class ReactionEvent:
    success: bool
    message_title: Optional[str] = None
    message_body: Optional[str] = None

    @property
    def is_limited(self) -> bool:
        return not self.success


@dataclass
class ReactionController:
    config: SEPConfig
    _counts: Dict[str, Dict[str, int]] = field(default_factory=dict)

    def add_reaction(self, user_id: str, resource_id: str) -> ReactionEvent:
        """Attempt to register a reaction for a user on a resource.

        When the per-resource cap is reached, the reaction is blocked and
        the UI copy for the toast/snack bar is returned so the caller can
        present it directly.
        """

        resource_counts = self._counts.setdefault(resource_id, {})
        current = resource_counts.get(user_id, 0)

        if current >= self.config.max_reactions_per_resource:
            return ReactionEvent(
                success=False,
                message_title=REACTION_LIMIT_TITLE,
                message_body=REACTION_LIMIT_BODY,
            )

        resource_counts[user_id] = current + 1
        return ReactionEvent(success=True)


# ---------------------------------------------------------------------------
# Session enforcement helper (Part 2: Concurrent Session Control UI)
# ---------------------------------------------------------------------------
@dataclass
class SessionEvent:
    user_id: str
    session_id: str
    invalidated_previous: bool
    new_device_message: str = WELCOME_BACK_TOAST
    previous_device_title: Optional[str] = None
    previous_device_body: Optional[str] = None
    previous_device_button: Optional[str] = None


@dataclass
class SessionController:
    config: SEPConfig
    _active_sessions: Dict[str, str] = field(default_factory=dict)

    def login(self, user_id: str, device_id: str) -> SessionEvent:
        """Log in a user, enforcing the single-session policy.

        The existing session (if any) is invalidated and the modal copy
        for the prior device is supplied for immediate display.
        """

        previous_session = self._active_sessions.get(user_id)
        new_session_id = f"{user_id}-{device_id}-{uuid.uuid4()}"
        self._active_sessions[user_id] = new_session_id

        invalidated = previous_session is not None
        return SessionEvent(
            user_id=user_id,
            session_id=new_session_id,
            invalidated_previous=invalidated,
            previous_device_title=SESSION_ALERT_TITLE if invalidated else None,
            previous_device_body=SESSION_ALERT_BODY if invalidated else None,
            previous_device_button=SESSION_ALERT_BUTTON if invalidated else None,
        )


# ---------------------------------------------------------------------------
# Demonstration
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    config = SEPConfig.load_from_env()
    reactions = ReactionController(config)
    sessions = SessionController(config)

    print("--- Reaction limiting demo ---")
    for i in range(7):
        event = reactions.add_reaction("alice", "photo-123")
        if event.success:
            print(f"Reaction {i + 1}: accepted")
        else:
            print(f"Reaction {i + 1}: blocked -> {event.message_title}: {event.message_body}")

    print("\n--- Session control demo ---")
    first_login = sessions.login("bob", "device-A")
    print(f"New login: {first_login.user_id} -> {first_login.session_id}")

    second_login = sessions.login("bob", "device-B")
    print(f"New login: {second_login.user_id} -> {second_login.session_id} ({second_login.new_device_message})")
    if second_login.invalidated_previous:
        print(
            f"Previous device modal: {second_login.previous_device_title} | "
            f"{second_login.previous_device_body} [{second_login.previous_device_button}]"
        )
