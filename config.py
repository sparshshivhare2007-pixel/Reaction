from __future__ import annotations

"""Configuration helpers for the Reaction Reporter Bot.

Fill the values below with your BOT TOKEN, API ID, API HASH, and MONGO URI
before deploying. This avoids mistakes with environment variables.
"""

import os
from typing import Final

# -----------------------------------------------------------
#  🔴 FILL THESE VALUES CAREFULLY BEFORE DEPLOYMENT
# -----------------------------------------------------------

BOT_TOKEN: Final[str] = "8227962612:AAHpVmUW89B2wrHo0gnPI0tvCA0ndz756iU"

API_ID: Final[int] = 26907246        # ← Enter your API ID (integer)
API_HASH: Final[str] = "1f75814e906cda223691847638b9fe94"

MONGO_URI: Final[str] = "mongodb+srv://annieregain:firstowner8v@anniere.ht2en.mongodb.net/?retryWrites=true&w=majority&appName=AnnieRE"

# Comma-separated Telegram user IDs that are allowed to issue admin commands
# (e.g., /restart). Example: ADMIN_IDS="123,456".
ADMIN_IDS: Final[set[int]] = {int(value) for value in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if value.isdigit()}

# -----------------------------------------------------------
#  (Optional) Author Verification — keep or remove as needed
# -----------------------------------------------------------

AUTHOR_NAME: Final[str] = "oxeign"
AUTHOR_HASH: Final[str] = "c5c8cd48384b065a0e46d27016b4e3ea5c9a52bd12d87cd681bd426c480cce3a"
