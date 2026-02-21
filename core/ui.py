"""
core/ui.py — Reusable embed builders and formatting helpers.

Keep all visual/formatting logic here so cogs stay clean.
"""

import datetime

import discord

# ── Formatting ────────────────────────────────────────────────────────────────


def streak_emoji(days: int) -> str:
    if days >= 7:
        return "🔥🔥🔥"
    if days >= 3:
        return "🔥🔥"
    return "🔥"


def streak_status(days: int) -> str:
    if days >= 7:
        return "🔥 On Fire!"
    if days >= 3:
        return "🌟 Strong Streak"
    if days > 0:
        return "💪 Getting Started"
    return "📸 No active streak"


def streak_footer(days: int) -> str:
    if days >= 7:
        return "🔥 Amazing! You're on fire!"
    if days >= 3:
        return "🌟 Great job! Keep it up!"
    return "💪 Start strong — you got this!"


def posted_today(last_post_date: str | None) -> bool:
    if not last_post_date:
        return False
    return datetime.date.fromisoformat(last_post_date) == datetime.date.today()


# ── Embed builders ────────────────────────────────────────────────────────────


def build_streak_embed(
    streak_days: int, last_post_date: str | None, score: int
) -> discord.Embed:
    embed = discord.Embed(title="🔥 Your Streak", color=0xFF6B6B)
    embed.add_field(
        name="Current Streak",
        value=f"{streak_days} days {streak_emoji(streak_days)}",
        inline=True,
    )
    embed.add_field(name="Total Score", value=f"{score} pts 🏆", inline=True)
    embed.add_field(name="Last Post", value=last_post_date or "—", inline=True)

    if posted_today(last_post_date):
        status = "✅ You've posted today! Keep the streak alive!"
    else:
        status = "⏰ Don't forget to post today to keep your streak!"
    embed.add_field(name="Status", value=status, inline=False)
    embed.set_footer(text=streak_footer(streak_days))
    return embed


def build_score_embed(
    streak_days: int, last_post_date: str | None, score: int
) -> discord.Embed:
    embed = discord.Embed(title="🏆 Your Stats", color=0x7289DA)
    embed.add_field(name="Total Score", value=f"{score} pts 🏆", inline=True)
    embed.add_field(
        name="Current Streak", value=f"{streak_days} days 🔥", inline=True
    )
    embed.add_field(name="Last Post", value=last_post_date or "—", inline=True)

    next_milestone = ((score // 100) + 1) * 100
    embed.add_field(
        name="Next Milestone",
        value=f"{next_milestone} pts ({next_milestone - score} to go)",
        inline=True,
    )

    daily = (
        "✅ Daily post done! +3 pts earned!"
        if posted_today(last_post_date)
        else "📸 Post an image to earn +3 pts!"
    )
    embed.add_field(name="Daily Status", value=daily, inline=False)
    return embed


def build_user_stats_embed(
    user: discord.Member,
    streak_days: int,
    last_post_date: str | None,
    score: int,
) -> discord.Embed:
    embed = discord.Embed(
        title=f"📊 {user.display_name}'s Stats", color=0x7289DA
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="Total Score", value=f"{score} pts 🏆", inline=True)
    embed.add_field(
        name="Current Streak", value=f"{streak_days} days 🔥", inline=True
    )
    embed.add_field(name="Last Post", value=last_post_date or "—", inline=True)
    embed.add_field(
        name="Streak Status", value=streak_status(streak_days), inline=True
    )
    return embed


def build_leaderboard_embed(
    title: str, description: str, color: int, leaders, value_fn
) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    if leaders:
        for i, row in enumerate(leaders, 1):
            medal = (
                "🥇"
                if i == 1
                else "🥈"
                if i == 2
                else "🥉"
                if i == 3
                else f"{i}."
            )
            embed.add_field(
                name=f"{medal} {row['username']}",
                value=value_fn(row),
                inline=False,
            )
    else:
        embed.description = "Nothing yet — be the first to post!"
    return embed
