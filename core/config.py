"""
core/config.py — Every setting and feature flag lives here.

To toggle a feature : flip its flag in the Features class below.
To change a value   : edit the default here OR set an env variable of the same name.
"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


# ══════════════════════════════════════════════════════════════════════════════
#  FEATURE FLAGS  —  set any to False to fully disable that feature
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class Features:
    # Leaderboards
    LEADERBOARD_ALLTIME: bool = True  # /leaderboard
    LEADERBOARD_MONTHLY: bool = (
        True  # /leaderboard-monthly  (separate score column, resets on 1st)
    )
    LEADERBOARD_WEEKLY: bool = (
        True  # /leaderboard-weekly   (separate score column, resets on Monday)
    )

    # Notifications — each can be independently toggled.
    # Requires the matching channel ID to be set below (NOTIFY_STREAK_LOSS_CHANNEL_ID etc.)
    NOTIFY_STREAK_LOSS: bool = True  # @user Lost their streak
    NOTIFY_NEW_NUMBER_ONE: bool = True  # @user is now #1 on the leaderboard!

    # Milestones
    STREAK_MILESTONES: bool = (
        True  # celebrate 7 / 30 / 100-day streaks in image channel
    )

    # Stats
    SERVER_STATS: bool = True  # /server-stats command

    # User commands
    USER_STATS: bool = True  # /user-stats @user

    # Admin score tools
    ADMIN_SET_SCORE: bool = True  # /set-score
    ADMIN_ADD_SCORE: bool = True  # /add-score
    ADMIN_RESET_SCORE: bool = True  # /reset-score
    ADMIN_RESET_STREAK: bool = True  # /reset-streak
    ADMIN_SET_STREAK: bool = True  # /set-streak


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN CONFIG
# ══════════════════════════════════════════════════════════════════════════════
def _optional_int(key: str) -> int | None:
    val = os.getenv(key, "")
    return int(val) if val.strip().isdigit() else None


@dataclass
class Config:
    # ── Discord ───────────────────────────────────────────────────────────────
    DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
    PREFIX: str = os.getenv("PREFIX", "!")

    # ── Image channels ────────────────────────────────────────────────────────
    # Channels where images are tracked. Add more IDs here or use !set_image at runtime.
    IMAGE_CHANNEL_IDS: list[int] = field(
        default_factory=lambda: [
            1433779537786961982,  # ← your image channel
            # 987654321098765432,  ← add more here
        ]
    )

    # ── Notification channels ─────────────────────────────────────────────────
    # Set each to a channel ID, or leave as None to disable that notification.
    # You can point both to the same channel or use separate ones — your choice.
    #
    # NOTIFY_STREAK_LOSS_CHANNEL_ID    → where 💀 "X lost their streak" posts go
    # NOTIFY_NUMBER_ONE_CHANNEL_ID     → where 👑 "X is now #1" posts go
    NOTIFY_STREAK_LOSS_CHANNEL_ID: int | None = field(
        default_factory=lambda: _optional_int("NOTIFY_STREAK_LOSS_CHANNEL_ID")
    )
    NOTIFY_NUMBER_ONE_CHANNEL_ID: int | None = field(
        default_factory=lambda: _optional_int("NOTIFY_NUMBER_ONE_CHANNEL_ID")
    )

    # ── Scoring ───────────────────────────────────────────────────────────────
    POINTS_PER_POST: int = int(os.getenv("POINTS_PER_POST", 3))

    # ── Streak milestones ─────────────────────────────────────────────────────
    # Format: {streak_days: "celebration message"}
    # Add or remove any milestones here — no other code changes needed.
    MILESTONES: dict[int, str] = field(
        default_factory=lambda: {
            7: "🔥 **7-day streak** — Nice consistency!",
            14: "🔥 **14-day streak** — Two weeks strong!",
            30: "🔥 **30-day streak** — You're unstoppable.",
            60: "🔥 **60-day streak** — Two months. Incredible.",
            100: "🔥 **100-day streak** — LEGEND.",
            365: "🔥 **365-day streak** — A FULL YEAR. Are you even human?!",
        }
    )

    # ── Database ──────────────────────────────────────────────────────────────
    DB_PATH: str = os.getenv("DB_PATH", "data/streaks.db")

    # ── Image download ────────────────────────────────────────────────────────
    IMAGE_DOWNLOAD_TIMEOUT: int = int(os.getenv("IMAGE_DOWNLOAD_TIMEOUT", 30))

    # ── Feature flags ─────────────────────────────────────────────────────────
    features: Features = field(default_factory=Features)


# Single shared instance — import this everywhere
config = Config()
