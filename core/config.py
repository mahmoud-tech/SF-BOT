import os
from dataclasses import dataclass, field
from tkinter import TRUE

from dotenv import load_dotenv

load_dotenv()

#
# ----------------------------------------------------------------------
# FEATURE FLAGS --- Set any to False to fully disable that feature
# ----------------------------------------------------------------------


@dataclass
class Features:
    # Leaderboards
    LEADERBOARD_ALLTIME: bool = True
    LEADERBOARD_MONTHLY: bool = True
    LEADERBOARD_WEEKLY: bool = True

    # Notifications
    NOTIFY_STREAK_LOSS: bool = True
    NOTIFY_NEW_NUMBER_ONE: bool = True

    # Streak milestone
    STREAK_MILESTONES: bool = True

    # Server Stats
    SERVER_STATS: bool = True

    # User Commands
    USER_STATS: bool = True

    # Admin Score Tools
    ADMIN_SET_SCORE: bool = True
    ADMIN_ADD_SCORE: bool = True
    ADMIN_RESET_SCORE: bool = True
    ADMIN_RESET_STREAK: bool = TRUE


# ----------------------------------------------------------------------
# Main Config
# ----------------------------------------------------------------------
def _optional_int(key: str) -> int | None:
    val = os.getenv(key, "")
    return int(val) if val.strip().isdigit() else None


@dataclass
class Config:
    # --- Discord
    DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
    PREFIX: str = os.getenv("PREFIX", "!")

    # --- Image Channels
    # ( Channels where images are tracked, Add more IDs here or user !set_image at runtime)
    IMAGE_CHANNEL_IDS: list[int] = field(
        default_factory=lambda: [
            1433779537786961982,  # ← your image channel
            # 987654321098765432,  ← add more here
        ]
    )

    # --- Notify
    NOTIFY_STREAK_LOSS_CHANNEL_ID: int | None = field(
        default_factory=lambda: _optional_int("NOTIFY_STREAK_LOSS_CHANNEL_ID")
    )
    NOTIFY_NUMBER_ONE_CHANNEL_ID: int | None = field(
        default_factory=lambda: _optional_int("NOTIFY_NUMBER_ONE_CHANNEL_ID")
    )

    # --- Scoring
    POINTS_PER_POST: int = int(os.getenv("POINTS_PER_POST", 1))

    # --- Streak Milestone
    MILESTONES: dict[int, str] = field(
        default_factory=lambda: {
            7: "🔥 **7-day streak** — Not bad",
            14: "🔥 **14-day streak** — Two weeks strong!",
            30: "🔥 **30-day streak** — You're unstoppable.",
            60: "🔥 **60-day streak** — Two months. Incredible.",
            100: "🔥 **100-day streak** — LEGEND.",
            365: "🔥 **365-day streak** — Get a fucking life",
        }
    )

    # --- Database
    DB_PATH: str = os.getenv("DP_PATH", "data/streaks.db")

    # --- Image Downlaod
    IMAGE_DOWNLOAD_TIMEOUT: int = int(os.getenv("IMAGE_DOWNLOAD_TIMEOUT", 30))

    # --- Feature Flags
    features: Features = field(default_factory=Features)


# Single shared instance --- ( Important )
# Ignore This Comment
config = Config()
