from __future__ import annotations

import asyncio
from typing import Dict, Optional
from urllib.parse import urlparse

from pyrogram import Client, filters
from pyrogram.errors import RPCError
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery

import config


app = Client("my_session", api_id=config.API_ID, api_hash=config.API_HASH)


MENU = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("Private Channel / Private Group", callback_data="private")],
        [InlineKeyboardButton("Public Channel / Public Group", callback_data="public")],
        [InlineKeyboardButton("Story URL", callback_data="story")],
    ]
)


class UserState:
    def __init__(self) -> None:
        self.flow: Optional[str] = None
        self.stage: Optional[str] = None
        self.invite_link: Optional[str] = None


user_states: Dict[int, UserState] = {}


def parse_telegram_url(url: str) -> dict:
    """Parse a Telegram URL into structured components.

    The structure mirrors the parser in ``main.py`` so both bots agree on
    which keys are present for each link type. This prevents runtime
    mismatches when handling user-provided links.
    """

    cleaned = url.strip()
    if not cleaned:
        raise ValueError("Empty URL")

    parsed = urlparse(cleaned if cleaned.startswith("http") else f"https://{cleaned}")
    path_parts = [p for p in parsed.path.split("/") if p]

    if not parsed.netloc.endswith("t.me") or not path_parts:
        raise ValueError("Invalid Telegram URL")

    if path_parts[0].startswith("+"):
        return {"type": "invite", "invite_link": f"https://t.me/{path_parts[0]}"}

    if path_parts[0] == "c" and len(path_parts) >= 3:
        return {
            "type": "private_message",
            "chat_id": int(f"-100{path_parts[1]}"),
            "message_id": int(path_parts[2]),
        }

    if len(path_parts) >= 3 and path_parts[1] in {"s", "story"}:
        return {
            "type": "story",
            "username": path_parts[0],
            "story_id": path_parts[2],
        }

    if len(path_parts) >= 2:
        return {
            "type": "public_message",
            "username": path_parts[0],
            "message_id": int(path_parts[1]),
        }

    if len(path_parts) == 1:
        return {"type": "username", "username": path_parts[0]}

    raise ValueError("Unrecognized Telegram URL format")


async def send_menu(message: Message) -> None:
    await message.reply_text(
        "Select an option:",
        reply_markup=MENU,
    )


@app.on_message(filters.command("start"))
async def start_handler(_: Client, message: Message) -> None:
    user_states[message.from_user.id] = UserState()
    await send_menu(message)


@app.on_callback_query(filters.regex("^(private|public|story)$"))
async def menu_callback_handler(_: Client, callback_query: CallbackQuery) -> None:
    user = callback_query.from_user
    state = user_states.setdefault(user.id, UserState())
    choice = callback_query.data

    if choice == "private":
        state.flow = "private"
        state.stage = "waiting_invite"
        state.invite_link = None
        await callback_query.message.reply_text(
            "Send the private invite link (e.g., https://t.me/+xxxxxxxxxxxxxx)",
            reply_markup=MENU,
        )
    elif choice == "public":
        state.flow = "public"
        state.stage = "waiting_public_message"
        state.invite_link = None
        await callback_query.message.reply_text(
            "Send the public message link (e.g., https://t.me/channelusername/1234)",
            reply_markup=MENU,
        )
    else:
        state.flow = "story"
        state.stage = "waiting_story"
        state.invite_link = None
        await callback_query.message.reply_text(
            "Send the story URL.",
            reply_markup=MENU,
        )

    await callback_query.answer()


async def handle_private_flow(client: Client, message: Message, state: UserState) -> None:
    try:
        parsed = parse_telegram_url(message.text)
    except Exception:
        await message.reply_text("Invalid Telegram URL. Please send a valid link.")
        return

    if state.stage == "waiting_invite":
        if parsed.get("type") != "invite":
            await message.reply_text("Please send a valid private invite link (https://t.me/+code)")
            return
        state.invite_link = parsed.get("invite_link")
        state.stage = "waiting_private_message"
        await message.reply_text("Now send the private message link (https://t.me/c/123456789/45)")
        return

    if state.stage == "waiting_private_message":
        if parsed.get("type") != "private_message":
            await message.reply_text("Please send a valid private message link (https://t.me/c/123456789/45)")
            return

        chat_id = parsed["chat_id"]
        message_id = parsed["message_id"]

        try:
            if state.invite_link:
                await client.join_chat(state.invite_link)
        except RPCError as e:
            await message.reply_text(f"Failed to join chat: {e}")
            return

        try:
            await client.get_chat(chat_id)
        except RPCError as e:
            await message.reply_text(f"Cannot access chat: {e}")
            return

        try:
            msg = await client.get_messages(chat_id, message_id)
            await message.reply_text(
                f"Fetched message from private chat. Message ID: {msg.id}")
        except RPCError as e:
            await message.reply_text(f"Failed to fetch message: {e}")
            return

        state.stage = None
        await send_menu(message)


async def handle_public_flow(client: Client, message: Message, state: UserState) -> None:
    try:
        parsed = parse_telegram_url(message.text)
    except Exception:
        await message.reply_text("Invalid Telegram URL. Please send a valid public message link.")
        return

    if parsed.get("type") != "public_message":
        await message.reply_text("Send a valid public message link (https://t.me/username/1234)")
        return

    username = parsed["username"]
    message_id = parsed["message_id"]

    try:
        chat = await client.get_chat(username)
    except RPCError as e:
        await message.reply_text(f"Cannot access chat: {e}")
        return

    try:
        msg = await client.get_messages(chat.id, message_id)
        await message.reply_text(f"Fetched public message from @{username}: {msg.id}")
    except RPCError as e:
        await message.reply_text(f"Failed to fetch message: {e}")
        return

    state.stage = None
    await send_menu(message)


async def handle_story_flow(client: Client, message: Message, state: UserState) -> None:
    try:
        parsed = parse_telegram_url(message.text)
    except Exception:
        await message.reply_text("Invalid Telegram URL. Please send a valid story link.")
        return

    if parsed.get("type") != "story":
        await message.reply_text("Send a valid story link (https://t.me/username/s/1234)")
        return

    username = parsed["username"]
    story_id = parsed["story_id"]

    try:
        stories = await client.get_stories(username, story_ids=[int(story_id)])
        if stories:
            await message.reply_text(
                f"Fetched story {story_id} from @{username}. Ready for processing.")
        else:
            await message.reply_text("Story not found.")
    except RPCError as e:
        await message.reply_text(f"Failed to fetch story: {e}")
        return

    state.stage = None
    await send_menu(message)


@app.on_message(filters.text & ~filters.command("start"))
async def message_handler(client: Client, message: Message) -> None:
    state = user_states.setdefault(message.from_user.id, UserState())

    if state.flow == "private":
        await handle_private_flow(client, message, state)
    elif state.flow == "public":
        await handle_public_flow(client, message, state)
    elif state.flow == "story":
        await handle_story_flow(client, message, state)
    else:
        await message.reply_text("Use /start to choose an option.", reply_markup=MENU)


if __name__ == "__main__":
    app.run()
