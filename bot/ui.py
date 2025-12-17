from __future__ import annotations

import textwrap
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.constants import MENU_LIVE_STATUS, REASON_LABELS

# Mobile-friendly: 70–78 looks best in Telegram monospace blocks
CARD_WIDTH = 74


# -----------------------------
# Card rendering (clean + pro)
# -----------------------------
def render_card(
    title: str,
    body: list[str] | tuple[str, ...],
    footer: list[str] | tuple[str, ...] | None = None,
    *,
    hint: str = "Help: 🔄 Restart or /restart",
) -> str:
    title = (title or "").strip()
    body_lines = list(body)
    footer_lines = list(footer or [])

    if hint and hint not in footer_lines:
        footer_lines.append(hint)

    inner = CARD_WIDTH - 4  # │ <inner> │

    def wrap_lines(lines: list[str]) -> list[str]:
        out: list[str] = []
        for line in lines:
            line = "" if line is None else str(line)
            if not line.strip():
                out.append("")
                continue
            out.extend(
                textwrap.wrap(
                    line,
                    width=inner,
                    break_long_words=False,
                    break_on_hyphens=False,
                )
            )
        return out

    def row(s: str) -> str:
        s = (s or "")[:inner]
        return f"│ {s}{' ' * (inner - len(s))} │"

    # Title bar (centered)
    # ┌──── Title ────┐
    title_block = f" {title} " if title else " "
    dash_space = (CARD_WIDTH - 2) - len(title_block)
    left = max(1, dash_space // 2)
    right = max(1, dash_space - left)
    top = f"┌{'─' * left}{title_block}{'─' * right}┐"

    divider = f"├{'─' * (CARD_WIDTH - 2)}┤"
    bottom = f"└{'─' * (CARD_WIDTH - 2)}┘"

    b = wrap_lines(body_lines)
    f = wrap_lines(footer_lines)

    lines: list[str] = [top]
    lines.extend(row(x) for x in b)
    lines.append(divider)
    lines.extend(row(x) for x in f)
    lines.append(bottom)
    return "\n".join(lines)


# -----------------------------
# Keyboard helpers
# -----------------------------
def _restart_row() -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton("🔄 Restart", callback_data="restart")]


def with_restart(markup: InlineKeyboardMarkup | None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if markup is not None:
        rows = [list(r) for r in markup.inline_keyboard]
    rows.append(_restart_row())
    return InlineKeyboardMarkup(rows)


# -----------------------------
# Main menu (best layout)
# -----------------------------
def main_menu_keyboard(
    saved_sessions: int = 0,
    active_sessions: int = 0,
    live_status: str = MENU_LIVE_STATUS,
) -> InlineKeyboardMarkup:
    # Short labels = cleaner UI on mobile
    rows = [
        [InlineKeyboardButton("▶ Start Report", callback_data="action:start")],
        [
            InlineKeyboardButton("➕ Add Sessions", callback_data="action:add"),
            InlineKeyboardButton("💾 Saved", callback_data="action:sessions"),
        ],
        [
            InlineKeyboardButton(f"🟢 {live_status}", callback_data="status:live"),
            InlineKeyboardButton(f"🎯 {active_sessions}", callback_data="status:active"),
            InlineKeyboardButton(f"📦 {saved_sessions}", callback_data="status:saved"),
        ],
    ]
    rows.append(_restart_row())
    return InlineKeyboardMarkup(rows)


# -----------------------------
# Target kind (clean naming)
# -----------------------------
def target_kind_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("🔒 Private Channel / Group", callback_data="kind:private")],
        [InlineKeyboardButton("🌐 Public Channel / Group", callback_data="kind:public")],
        [InlineKeyboardButton("📎 Story URL (Profile)", callback_data="kind:story")],
        _restart_row(),
    ]
    return InlineKeyboardMarkup(rows)


# -----------------------------
# Reasons (balanced grid)
# Keeps your callback_data mapping intact
# -----------------------------
def reason_keyboard() -> InlineKeyboardMarkup:
    # Your original ordering preserved (0,3,2,1,6,4,5)
    ordered = [0, 3, 2, 1, 6, 4, 5]
    buttons = [
        InlineKeyboardButton(REASON_LABELS[i], callback_data=f"reason:{i}")
        for i in ordered
    ]

    rows = [
        buttons[0:2],
        buttons[2:4],
        buttons[4:6],
        buttons[6:7],
        _restart_row(),
    ]
    return InlineKeyboardMarkup(rows)


# -----------------------------
# Session mode (pro wording)
# -----------------------------
def session_mode_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("Use Saved Sessions", callback_data="session_mode:reuse")],
        [InlineKeyboardButton("Add New Sessions", callback_data="session_mode:new")],
        _restart_row(),
    ]
    return InlineKeyboardMarkup(rows)


# -----------------------------
# Greeting (professional copy)
# -----------------------------
def render_greeting() -> str:
    return render_card(
        "Nightfall Reporter",
        [
            "Welcome.",
            "Start with saved sessions, or add new sessions anytime.",
            "Use the status chips to track readiness and loaded/saved sessions.",
            "Choose an action below to continue.",
        ],
        footer=[],
    )


__all__ = [
    "main_menu_keyboard",
    "target_kind_keyboard",
    "reason_keyboard",
    "session_mode_keyboard",
    "render_greeting",
    "render_card",
    "with_restart",
]
