"""
core/ui.py — Every embed builder and formatting helper.

Cogs never build embeds directly — they call a function here.
"""

import datetime
import sqlite3
from typing import Optional

import discord

# ── Formatting helpers ────────────────────────────────────────────────────────


def streak_emoji(days: int) -> str:
    if days >= 100:
        return "🔥🔥🔥🔥"
    if days >= 30:
        return "🔥🔥🔥"
    if days >= 7:
        return "🔥🔥"
    return "🔥"


def medal(rank: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"{rank}.")


def posted_today(last_post_date: Optional[str]) -> bool:
    if not last_post_date:
        return False
    return datetime.date.fromisoformat(last_post_date) == datetime.date.today()


def days_to_beat_best(streak_days: int, best_streak: int) -> str:
    if streak_days == 0:
        return "—"
    remaining = best_streak - streak_days + 1
    if remaining <= 0:
        return "✅ Current best!"
    return f"{remaining} day(s) away (best: {best_streak})"


# ── /streak (self) ────────────────────────────────────────────────────────────


def build_streak_embed(
    member: discord.Member,
    streak_days: int,
    best_streak: int,
    last_post_date: Optional[str],
    score: int,
) -> discord.Embed:
    embed = discord.Embed(title="🔥 Your Streak", color=0xFF6B6B)
    embed.set_thumbnail(url=member.display_avatar.url)

    embed.add_field(
        name="Current Streak",
        value=f"{streak_days} days {streak_emoji(streak_days)}",
        inline=True,
    )
    embed.add_field(
        name="Best Streak", value=f"{best_streak} days 🏅", inline=True
    )
    embed.add_field(name="Total Score", value=f"{score} pts 🏆", inline=True)
    embed.add_field(
        name="Last Check-In", value=last_post_date or "Never", inline=True
    )
    embed.add_field(
        name="Beat Your Best",
        value=days_to_beat_best(streak_days, best_streak),
        inline=True,
    )

    status = (
        "✅ Checked in today!"
        if posted_today(last_post_date)
        else "⏰ Post today to keep your streak!"
    )
    embed.add_field(name="Today", value=status, inline=False)

    if streak_days >= 100:
        embed.set_footer(text="🔥 LEGEND. Absolutely unstoppable.")
    elif streak_days >= 30:
        embed.set_footer(text="🔥 Incredible dedication. Keep going!")
    elif streak_days >= 7:
        embed.set_footer(text="🌟 Great consistency — keep building!")
    else:
        embed.set_footer(text="💪 Every day counts. Keep showing up.")

    return embed


# ── /user-stats (other user) ──────────────────────────────────────────────────


def build_user_stats_embed(
    member: discord.Member,
    streak_days: int,
    best_streak: int,
    last_post_date: Optional[str],
    score: int,
    weekly_score: int,
    monthly_score: int,
) -> discord.Embed:
    embed = discord.Embed(
        title=f"📊 {member.display_name}'s Stats", color=0x7289DA
    )
    embed.set_thumbnail(url=member.display_avatar.url)

    embed.add_field(
        name="Current Streak",
        value=f"{streak_days} days {streak_emoji(streak_days)}",
        inline=True,
    )
    embed.add_field(
        name="Best Streak", value=f"{best_streak} days 🏅", inline=True
    )
    embed.add_field(name="Total Score", value=f"{score} pts 🏆", inline=True)
    embed.add_field(name="This Week", value=f"{weekly_score} pts", inline=True)
    embed.add_field(
        name="This Month", value=f"{monthly_score} pts", inline=True
    )
    embed.add_field(
        name="Last Check-In", value=last_post_date or "Never", inline=True
    )
    embed.add_field(
        name="Beat Their Best",
        value=days_to_beat_best(streak_days, best_streak),
        inline=False,
    )

    return embed


# ── Leaderboard embeds ────────────────────────────────────────────────────────


def build_leaderboard_alltime(rows: list[sqlite3.Row]) -> discord.Embed:
    embed = discord.Embed(
        title="🏆 All-Time Leaderboard",
        description="Top 10 by total score",
        color=0xFFD700,
    )
    if not rows:
        embed.description = "No scores yet — be the first to post!"
        return embed
    for i, row in enumerate(rows, 1):
        embed.add_field(
            name=f"{medal(i)} {row['username']}",
            value=f"**{row['score']} pts** | {row['streak_days']} day streak | best: {row['best_streak']}d",
            inline=False,
        )
    return embed


def build_leaderboard_streak(rows: list[sqlite3.Row]) -> discord.Embed:
    embed = discord.Embed(
        title="🔥 Streak Leaderboard",
        description="Top 10 by current streak",
        color=0xFF6B6B,
    )
    if not rows:
        embed.description = "No active streaks — start one by posting!"
        return embed
    for i, row in enumerate(rows, 1):
        embed.add_field(
            name=f"{medal(i)} {row['username']}",
            value=f"**{row['streak_days']} days** {streak_emoji(row['streak_days'])} | best: {row['best_streak']}d | {row['score']} pts",
            inline=False,
        )
    return embed


def build_leaderboard_weekly(rows: list[sqlite3.Row]) -> discord.Embed:
    week_start = datetime.date.today() - datetime.timedelta(
        days=datetime.date.today().weekday()
    )
    week_end = week_start + datetime.timedelta(days=6)
    label = f"{week_start.strftime('%b %d')} – {week_end.strftime('%b %d')}"
    embed = discord.Embed(
        title=f"📅 Weekly Leaderboard",
        description=f"Top 10 by points earned this week ({label})",
        color=0x5865F2,
    )
    if not rows:
        embed.description = f"No posts this week yet! ({label})"
        return embed
    for i, row in enumerate(rows, 1):
        embed.add_field(
            name=f"{medal(i)} {row['username']}",
            value=f"**{row['weekly_score']} pts** | {row['streak_days']} day streak",
            inline=False,
        )
    return embed


def build_leaderboard_monthly(rows: list[sqlite3.Row]) -> discord.Embed:
    month_label = datetime.date.today().strftime("%B %Y")
    embed = discord.Embed(
        title=f"📅 Monthly Leaderboard",
        description=f"Top 10 by points earned in {month_label}",
        color=0x57F287,
    )
    if not rows:
        embed.description = f"No posts in {month_label} yet!"
        return embed
    for i, row in enumerate(rows, 1):
        embed.add_field(
            name=f"{medal(i)} {row['username']}",
            value=f"**{row['monthly_score']} pts** | {row['streak_days']} day streak",
            inline=False,
        )
    return embed


# ── /server-stats ─────────────────────────────────────────────────────────────


def build_server_stats(stats: dict) -> discord.Embed:
    embed = discord.Embed(title="📊 Server Stats", color=0x2ECC71)
    embed.add_field(
        name="Total Check-Ins",
        value=f"{stats['total_checkins']:,}",
        inline=True,
    )
    embed.add_field(
        name="Active Streakers",
        value=str(stats["active_streakers"]),
        inline=True,
    )
    embed.add_field(
        name="Highest Streak",
        value=f"{stats['highest_streak']} days",
        inline=True,
    )
    embed.add_field(
        name="Today's Consistency",
        value=f"{stats['consistency_pct']}%",
        inline=True,
    )
    return embed


# ── Notification messages ─────────────────────────────────────────────────────


def streak_loss_message(username: str, lost_streak: int) -> str:
    return f"💀 **{username}** lost their **{lost_streak}-day streak**. Better luck tomorrow!"


def new_number_one_message(mention: str, streak_days: int) -> str:
    return f"👑 {mention} is now **#1 on the streak leaderboard** with **{streak_days} days**! 🔥"
