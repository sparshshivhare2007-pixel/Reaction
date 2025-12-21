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

BOT_TOKEN: Final[str] = "8449133505:AAFS4CP6gKpsveQefRp1LPilfkVL6FEYiuA"

API_ID: Final[int] = 26658182        # ← Enter your API ID (integer)
API_HASH: Final[str] = "d3cdbdb3b81014c71ec60ed03d2b4d8f"

MONGO_URI: Final[str] = "mongodb+srv://annieregain:firstowner8v@anniere.ht2en.mongodb.net/?retryWrites=true&w=majority&appName=AnnieRE"

# Comma-separated Telegram user IDs that are allowed to issue admin commands
# (e.g., /restart). Example: ADMIN_IDS="123,456".
ADMIN_IDS: Final[set[int]] = {int(value) for value in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if value.isdigit()}

# -----------------------------------------------------------
#  (Optional) Author Verification — keep or remove as needed
# -----------------------------------------------------------

AUTHOR_NAME: Final[str] = "oxeign"
AUTHOR_HASH: Final[str] = "c5c8cd48384b065a0e46d27016b4e3ea5c9a52bd12d87cd681bd426c480cce3a"
