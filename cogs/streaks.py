"""
cogs/streaks.py — Image processing + user-facing slash commands.

Slash commands: /streak  /score  /leaderboard  /streak_leaderboard  /user_stats
"""

import asyncio
import io
import logging
from typing import Optional

import aiohttp
import core.database as db
import discord
from core.config import config
from core.ui import (
    build_leaderboard_embed,
    build_score_embed,
    build_streak_embed,
    build_user_stats_embed,
    streak_emoji,
)
from discord import app_commands
from discord.ext import commands, tasks

log = logging.getLogger("SF-BOT.streaks")


# ── Check: block commands inside image channels ───────────────────────────────


def not_image_channel(interaction: discord.Interaction) -> bool:
    return interaction.channel_id not in config.IMAGE_CHANNEL_IDS


# ── Helpers ───────────────────────────────────────────────────────────────────


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

    async def cog_load(self) -> None:
        self._http = aiohttp.ClientSession()
        self.expire_streaks.start()
        log.info("StreaksCog loaded.")

    async def cog_unload(self) -> None:
        self.expire_streaks.cancel()
        if self._http:
            await self._http.close()

    # ── Image processing ──────────────────────────────────────────────────────

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

        # Download before deleting so the URL stays valid
        image_data = await download_image(self._http, images[0].url)
        if not image_data:
            return

        await message.delete()

        streak_days, new_score = db.record_post(
            message.author.id, message.author.display_name
        )
        caption_icon = (
            "🔥" if streak_days >= 3 else "⭐" if streak_days >= 2 else "📸"
        )
        caption = (
            f"📸 {message.author.mention}'s streak: **{streak_days} day(s)** {caption_icon} "
            f"| Score: **{new_score}** 🏆"
        )
        file = discord.File(io.BytesIO(image_data), filename="streak_image.png")
        await message.channel.send(content=caption, file=file)
        log.info(
            "Processed image: %s → streak=%d score=%d",
            message.author.display_name,
            streak_days,
            new_score,
        )

    # ── Nightly streak expiry ─────────────────────────────────────────────────

    @tasks.loop(hours=24)
    async def expire_streaks(self) -> None:
        count = db.expire_old_streaks()
        log.info("Nightly expiry: reset %d streak(s).", count)

    @expire_streaks.before_loop
    async def before_expire(self) -> None:
        await self.bot.wait_until_ready()
        # Wait until the next midnight before starting
        now = __import__("datetime").datetime.now()
        midnight = (now + __import__("datetime").timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        await asyncio.sleep((midnight - now).total_seconds())

    # ── /streak ───────────────────────────────────────────────────────────────

    @app_commands.command(
        name="streak", description="Check your current streak"
    )
    @app_commands.check(not_image_channel)
    async def streak_cmd(self, interaction: discord.Interaction) -> None:
        row = db.get_user(interaction.user.id)
        if not row:
            embed = discord.Embed(
                title="🔥 Your Streak",
                description="You haven't started yet! Post an image to begin.",
                color=0xFFA500,
            )
        else:
            embed = build_streak_embed(
                row["streak_days"], row["last_post_date"], row["score"]
            )
        await interaction.response.send_message(embed=embed)

    # ── /score ────────────────────────────────────────────────────────────────

    @app_commands.command(
        name="score", description="Check your score and stats"
    )
    @app_commands.check(not_image_channel)
    async def score_cmd(self, interaction: discord.Interaction) -> None:
        row = db.get_user(interaction.user.id)
        if not row:
            embed = discord.Embed(
                title="🏆 Your Stats",
                description="No stats yet — post an image to start earning points!",
                color=0xFFA500,
            )
        else:
            embed = build_score_embed(
                row["streak_days"], row["last_post_date"], row["score"]
            )
        await interaction.response.send_message(embed=embed)

    # ── /leaderboard ──────────────────────────────────────────────────────────

    @app_commands.command(
        name="leaderboard", description="Top 10 users by score"
    )
    @app_commands.check(not_image_channel)
    async def leaderboard_cmd(self, interaction: discord.Interaction) -> None:
        leaders = db.get_leaderboard("score")
        embed = build_leaderboard_embed(
            title="🏆 Score Leaderboard",
            description="Top 10 by total score",
            color=0xFFD700,
            leaders=leaders,
            value_fn=lambda r: (
                f"**{r['score']} pts** | {r['streak_days']} day streak"
            ),
        )
        await interaction.response.send_message(embed=embed)

    # ── /streak_leaderboard ───────────────────────────────────────────────────

    @app_commands.command(
        name="streak_leaderboard", description="Top 10 users by streak length"
    )
    @app_commands.check(not_image_channel)
    async def streak_leaderboard_cmd(
        self, interaction: discord.Interaction
    ) -> None:
        leaders = db.get_leaderboard("streak_days")
        embed = build_leaderboard_embed(
            title="🔥 Streak Leaderboard",
            description="Top 10 by current streak",
            color=0xFF6B6B,
            leaders=leaders,
            value_fn=lambda r: (
                f"**{r['streak_days']} days** {streak_emoji(r['streak_days'])} | {r['score']} pts"
            ),
        )
        await interaction.response.send_message(embed=embed)

    # ── /user_stats ───────────────────────────────────────────────────────────

    @app_commands.command(
        name="user_stats", description="Check another user's stats"
    )
    @app_commands.describe(user="The user to look up")
    @app_commands.check(not_image_channel)
    async def user_stats_cmd(
        self, interaction: discord.Interaction, user: discord.Member
    ) -> None:
        row = db.get_user(user.id)
        if row:
            embed = build_user_stats_embed(
                user, row["streak_days"], row["last_post_date"], row["score"]
            )
        else:
            embed = discord.Embed(
                title=f"📊 {user.display_name}'s Stats",
                description="This user hasn't posted any images yet!",
                color=0xFFA500,
            )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StreaksCog(bot))
