# StudyFlow Streak Tracking Bot

## Folder Structure

```
sf-bot/
├── main.py                  ← Entry point. Run this. (الملف الأساسي الى تشغل منه البوت)
├── requirements.txt         ← Packages Needed
├── .env.example             ← Copy to .env and fill in your values (rename it to .env)
│
├── core/
│   ├── config.py            ← ALL settings + feature flags live here (تقدر تقفل وتشغل كوماندز من هنا من غير ما تغير في الكود)
│   ├── database.py          ← All database logic (SQLite) 
│   └── ui.py                ← All embed builders and formatting ( اي embed حطه هنا اريحلك)
│
├── cogs/
│   ├── streaks.py           ← Image processing + user slash commands
│   └── admin.py             ← Admin-only commands
│
└── data/
    └── streaks.db           ← Auto-created on first run (Database)
```

**Rule of thumb when adding features:**
- New setting or flag → `core/config.py`
- New DB query → `core/database.py`
- New embed/format → `core/ui.py`
- New user command → `cogs/streaks.py`
- New admin command → `cogs/admin.py`

---

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env          # fill in your token + channel IDs
python main.py
```

---

## Feature Flags

Open `core/config.py` and flip any flag in the `Features` class to `False` to disable it server-wide:

```python
@dataclass
class Features:
    LEADERBOARD_ALLTIME:   bool = True 
    LEADERBOARD_MONTHLY:   bool = True 
    LEADERBOARD_WEEKLY:    bool = True
    NOTIFY_STREAK_LOSS:    bool = True 
    NOTIFY_NEW_NUMBER_ONE: bool = True
    STREAK_MILESTONES:     bool = True 
    SERVER_STATS:          bool = True
    USER_STATS:            bool = True  
    ADMIN_SET_SCORE:       bool = True
    ADMIN_ADD_SCORE:       bool = True
    ADMIN_RESET_SCORE:     bool = True
    ADMIN_RESET_STREAK:    bool = True
    ADMIN_SET_STREAK: bool = True 
```

---

## Notification Channels

Each notification type has its own channel — configure them independently in `.env`:

| Variable | What posts there |
|---|---|
| `NOTIFY_STREAK_LOSS_CHANNEL_ID` | 💀 "@User lost their 47-day streak." |
| `NOTIFY_NUMBER_ONE_CHANNEL_ID` | 👑 "@User is now #1 on the leaderboard!" |

You can set them to the same channel or different ones. Leave either blank to disable it.
Totaly Optional
---

## Milestone Messages

Edit the `MILESTONES` dict in `core/config.py` — add or remove any days freely:

```python
MILESTONES: dict[int, str] = {
    7:   "🔥 **7-day streak** — Nice consistency!",
    30:  "🔥 **30-day streak** — You're unstoppable.",
    100: "🔥 **100-day streak** — LEGEND.",
}
```
Total Optionally too
---

## Commands

### User Commands (slash)

| Command | Description |
|---|---|
| `/streak` | Your streak, best streak ever, days to beat your best, last check-in |
| `/user-stats @user` | Another user's full stats (streak, best, score, weekly, monthly) |
| `/leaderboard` | All-time top 10 by total score |
| `/leaderboard-streak` | Top 10 by current streak length |
| `/leaderboard-weekly` | Top 10 by points earned this week (Mon–Sun, resets per user) |
| `/leaderboard-monthly` | Top 10 by points earned this month (resets per user on 1st) |
| `/server-stats` | Total check-ins, active streakers, highest streak, consistency % |

### Admin Commands (slash)

| Command | Description |
|---|---|
| `/set-score @user N` | Set a user's total score to N |
| `/add-score @user N` | Add N points (use negative to subtract) |
| `/reset-score @user` | Reset a user's score to 0 |
| `/reset-streak @user` | Reset a user's streak to 0 |

### Admin Commands (prefix)

| Command | Description |
|---|---|
| `!sync` | Force-sync slash commands to this guild |
| `!set_image` | Register the current channel as an image channel |
| `!remove_image` | Remove the current channel from image channels |
| `!list_image_channels` | List all registered image channels |
| `!debug_channels` | Debug channel registration |

---

## How Weekly / Monthly Leaderboards Work

Scores reset **per user**, not for the whole server at once.

When a user posts their first image in a new week or month, their weekly/monthly score resets to 0 and starts fresh. This means:
- No cron job or scheduled reset needed
- Historical all-time scores are never touched
- The leaderboard always reflects genuine activity in the current period

---

## How Streaks Work

1. User posts an image in a registered image channel.
2. Bot downloads the image, deletes the original, re-posts it with a caption.
3. **+1 points** awarded (once per calendar day — no double-posting).
4. Consecutive daily posts increment the streak; missing a day resets it to 1.

## Testing 
since you're using railway
i tested the proejct before sumbitting
all you need to an environment variable in railway
DISCORD_TOKEN -> your bot token goes here.
