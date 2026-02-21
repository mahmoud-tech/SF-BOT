"""
cogs/streaks.py — Image processing + all user-facing slash commands.

All db.* calls are now async (run in thread pool via asyncio.to_thread).
Nightly notifications are sent concurrently via asyncio.gather().
"""

import asyncio
import datetime
import io
import logging
from typing import Optional

import aiohttp
import core.database as db
import discord
from core.config import config
from core.ui import (
    build_leaderboard_alltime,
    build_leaderboard_monthly,
    build_leaderboard_streak,
    build_leaderboard_weekly,
    build_server_stats,
    build_streak_embed,
    build_user_stats_embed,
    new_number_one_message,
    streak_loss_message,
)
from discord import app_commands
from discord.ext import commands, tasks

log = logging.getLogger("SF-BOT.streaks")


# ── Check ─────────────────────────────────────────────────────────────────────


def not_image_channel(interaction: discord.Interaction) -> bool:
    return interaction.channel_id not in config.IMAGE_CHANNEL_IDS


# ── Image download ────────────────────────────────────────────────────────────


async def download_image(
    session: aiohttp.ClientSession, url: str
) -> Optional[bytes]:
    try:
        timeout = aiohttp.ClientTimeout(total=config.IMAGE_DOWNLOAD_TIMEOUT)
        async with session.get(url, timeout=timeout) as resp:
            if resp.status == 200:
                return await resp.read()
            log.warning("Image download failed — HTTP %s", resp.status)
    except Exception as exc:
        log.error("Image download error: %s", exc)
    return None


# ── Cog ───────────────────────────────────────────────────────────────────────


class StreaksCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._http: Optional[aiohttp.ClientSession] = None
        self._prev_number_one: Optional[int] = None

    async def cog_load(self) -> None:
        self._http = aiohttp.ClientSession()
        self.nightly_task.start()
        log.info("StreaksCog loaded.")

    async def cog_unload(self) -> None:
        self.nightly_task.cancel()
        if self._http:
            await self._http.close()

    # ── Notification helper ───────────────────────────────────────────────────

    async def _send_to_channel(
        self, channel_id: Optional[int], message: str
    ) -> None:
        if not channel_id:
            return
        ch = self.bot.get_channel(channel_id)
        if ch:
            await ch.send(message)
        else:
            log.warning("Notification channel %s not found.", channel_id)

    # ── on_message — image processing ─────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if message.channel.id not in config.IMAGE_CHANNEL_IDS:
            return

        images = [
            a
            for a in message.attachments
            if a.content_type and a.content_type.startswith("image/")
        ]
        if not images:
            return

        # Download and DB write run concurrently — both are non-blocking
        (
            image_data,
            (streak_days, new_score, already_posted, milestone),
        ) = await asyncio.gather(
            download_image(self._http, images[0].url),
            db.record_post(message.author.id, message.author.display_name),
        )

        if not image_data:
            return

        await message.delete()

        icon = "🔥" if streak_days >= 3 else "⭐" if streak_days >= 2 else "📸"

        if already_posted:
            # Already checked in today — repost image but no score/streak change
            caption = f"📸 {message.author.mention} already checked in today! Streak: **{streak_days} day(s)** {icon} | Score: **{new_score}** 🏆"
        else:
            caption = (
                f"📸 {message.author.mention}'s streak: **{streak_days} day(s)** {icon} "
                f"| Score: **{new_score}** 🏆"
            )

        file = discord.File(io.BytesIO(image_data), filename="streak_image.png")
        await message.channel.send(content=caption, file=file)

        if not already_posted:
            # Milestone
            if config.features.STREAK_MILESTONES and milestone:
                await message.channel.send(
                    f"{message.author.mention} {config.MILESTONES[milestone]}"
                )

            # #1 check
            if config.features.NOTIFY_NEW_NUMBER_ONE:
                top = await db.get_top_streak_user()
                if top and top["user_id"] == message.author.id:
                    if self._prev_number_one != message.author.id:
                        self._prev_number_one = message.author.id
                        await self._send_to_channel(
                            config.NOTIFY_NUMBER_ONE_CHANNEL_ID,
                            new_number_one_message(
                                message.author.mention, streak_days
                            ),
                        )

        log.info(
            "Post: %s → streak=%d score=%d already_posted=%s",
            message.author.display_name,
            streak_days,
            new_score,
            already_posted,
        )

    # ── Nightly task ──────────────────────────────────────────────────────────

    @tasks.loop(hours=24)
    async def nightly_task(self) -> None:
        victims = await db.expire_old_streaks()
        log.info("Nightly expiry: reset %d streak(s).", len(victims))

        # Send all notifications concurrently instead of one-by-one
        if config.features.NOTIFY_STREAK_LOSS and victims:
            await asyncio.gather(
                *[
                    self._send_to_channel(
                        config.NOTIFY_STREAK_LOSS_CHANNEL_ID,
                        streak_loss_message(username, lost_streak),
                    )
                    for _, username, lost_streak in victims
                ]
            )

    @nightly_task.before_loop
    async def before_nightly(self) -> None:
        await self.bot.wait_until_ready()
        now = datetime.datetime.now()
        midnight = (now + datetime.timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        await asyncio.sleep((midnight - now).total_seconds())

    # ── /streak ───────────────────────────────────────────────────────────────

    @app_commands.command(
        name="streak", description="Check your current streak and stats"
    )
    @app_commands.check(not_image_channel)
    async def streak_cmd(self, interaction: discord.Interaction) -> None:
        row = await db.get_user(interaction.user.id)
        if not row:
            embed = discord.Embed(
                title="🔥 Your Streak",
                description="You haven't posted yet! Post an image to start your streak.",
                color=0xFFA500,
            )
        else:
            embed = build_streak_embed(
                member=interaction.user,
                streak_days=row["streak_days"],
                best_streak=row["best_streak"],
                last_post_date=row["last_post_date"],
                score=row["score"],
            )
        await interaction.response.send_message(embed=embed)

    # ── /user-stats @user ─────────────────────────────────────────────────────

    @app_commands.command(
        name="user-stats", description="Check another user's streak and stats"
    )
    @app_commands.describe(user="The user to look up")
    @app_commands.check(not_image_channel)
    async def user_stats_cmd(
        self, interaction: discord.Interaction, user: discord.Member
    ) -> None:
        if not config.features.USER_STATS:
            return await interaction.response.send_message(
                "This feature is disabled.", ephemeral=True
            )
        row = await db.get_user(user.id)
        if not row:
            embed = discord.Embed(
                title=f"📊 {user.display_name}'s Stats",
                description="This user hasn't posted any images yet!",
                color=0xFFA500,
            )
        else:
            embed = build_user_stats_embed(
                member=user,
                streak_days=row["streak_days"],
                best_streak=row["best_streak"],
                last_post_date=row["last_post_date"],
                score=row["score"],
                weekly_score=row["weekly_score"],
                monthly_score=row["monthly_score"],
            )
        await interaction.response.send_message(embed=embed)

    # ── /leaderboard ──────────────────────────────────────────────────────────

    @app_commands.command(
        name="leaderboard", description="All-time top 10 by score"
    )
    @app_commands.check(not_image_channel)
    async def leaderboard_cmd(self, interaction: discord.Interaction) -> None:
        if not config.features.LEADERBOARD_ALLTIME:
            return await interaction.response.send_message(
                "This feature is disabled.", ephemeral=True
            )
        await interaction.response.send_message(
            embed=build_leaderboard_alltime(await db.get_leaderboard_alltime())
        )

    # ── /leaderboard-streak ───────────────────────────────────────────────────

    @app_commands.command(
        name="leaderboard-streak", description="Top 10 by current streak length"
    )
    @app_commands.check(not_image_channel)
    async def leaderboard_streak_cmd(
        self, interaction: discord.Interaction
    ) -> None:
        await interaction.response.send_message(
            embed=build_leaderboard_streak(await db.get_leaderboard_streak())
        )

    # ── /leaderboard-weekly ───────────────────────────────────────────────────

    @app_commands.command(
        name="leaderboard-weekly", description="Top 10 by score this week"
    )
    @app_commands.check(not_image_channel)
    async def leaderboard_weekly_cmd(
        self, interaction: discord.Interaction
    ) -> None:
        if not config.features.LEADERBOARD_WEEKLY:
            return await interaction.response.send_message(
                "This feature is disabled.", ephemeral=True
            )
        await interaction.response.send_message(
            embed=build_leaderboard_weekly(await db.get_leaderboard_weekly())
        )

    # ── /leaderboard-monthly ──────────────────────────────────────────────────

    @app_commands.command(
        name="leaderboard-monthly", description="Top 10 by score this month"
    )
    @app_commands.check(not_image_channel)
    async def leaderboard_monthly_cmd(
        self, interaction: discord.Interaction
    ) -> None:
        if not config.features.LEADERBOARD_MONTHLY:
            return await interaction.response.send_message(
                "This feature is disabled.", ephemeral=True
            )
        await interaction.response.send_message(
            embed=build_leaderboard_monthly(await db.get_leaderboard_monthly())
        )

    # ── /server-stats ─────────────────────────────────────────────────────────

    @app_commands.command(
        name="server-stats", description="Server-wide streak statistics"
    )
    @app_commands.check(not_image_channel)
    async def server_stats_cmd(self, interaction: discord.Interaction) -> None:
        if not config.features.SERVER_STATS:
            return await interaction.response.send_message(
                "This feature is disabled.", ephemeral=True
            )
        await interaction.response.send_message(
            embed=build_server_stats(await db.get_server_stats())
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StreaksCog(bot))
