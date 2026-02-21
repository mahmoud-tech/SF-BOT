"""
cogs/admin.py — Admin-only commands.

Prefix  : !sync  !set_image  !remove_image  !list_image_channels  !debug_channels
Slash   : /set-score  /add-score  /reset-score  /reset-streak
"""

import logging

import core.database as db
import discord
from core.config import config
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("SF-BOT.admin")


def not_image_channel(interaction: discord.Interaction) -> bool:
    return interaction.channel_id not in config.IMAGE_CHANNEL_IDS


def is_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.administrator  # type: ignore[union-attr]


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── !sync ─────────────────────────────────────────────────────────────────

    @commands.command()
    @commands.has_guild_permissions(administrator=True)
    async def sync(self, ctx: commands.Context) -> None:
        """Sync slash commands to this guild immediately."""
        self.bot.tree.copy_global_to(guild=ctx.guild)
        synced = await self.bot.tree.sync(guild=ctx.guild)
        await ctx.send(f"✅ Synced **{len(synced)}** slash command(s).")
        log.info("Manual sync: %d command(s) → %s", len(synced), ctx.guild.name)

    # ── !set_image ────────────────────────────────────────────────────────────

    @commands.command()
    @commands.has_guild_permissions(administrator=True)
    async def set_image(self, ctx: commands.Context) -> None:
        """Register this channel as an image/streak channel."""
        cid = ctx.channel.id
        if cid not in config.IMAGE_CHANNEL_IDS:
            config.IMAGE_CHANNEL_IDS.append(cid)
            await ctx.send(f"✅ {ctx.channel.mention} is now an image channel.")
            log.info("Added image channel: %d", cid)
        else:
            await ctx.send(
                f"ℹ️ {ctx.channel.mention} is already an image channel."
            )

    # ── !remove_image ─────────────────────────────────────────────────────────

    @commands.command()
    @commands.has_guild_permissions(administrator=True)
    async def remove_image(self, ctx: commands.Context) -> None:
        """Remove this channel from image channels."""
        cid = ctx.channel.id
        if cid in config.IMAGE_CHANNEL_IDS:
            config.IMAGE_CHANNEL_IDS.remove(cid)
            await ctx.send(f"✅ {ctx.channel.mention} removed.")
            log.info("Removed image channel: %d", cid)
        else:
            await ctx.send(f"❌ {ctx.channel.mention} is not an image channel.")

    # ── !list_image_channels ──────────────────────────────────────────────────

    @commands.command()
    @commands.has_guild_permissions(administrator=True)
    async def list_image_channels(self, ctx: commands.Context) -> None:
        embed = discord.Embed(title="📸 Image Channels", color=0x7289DA)
        if config.IMAGE_CHANNEL_IDS:
            lines = []
            for cid in config.IMAGE_CHANNEL_IDS:
                ch = self.bot.get_channel(cid)
                lines.append(
                    f"{ch.mention} (`{cid}`)" if ch else f"❓ Unknown (`{cid}`)"
                )
            embed.description = "\n".join(lines)
        else:
            embed.description = (
                "No image channels set. Use `!set_image` to add one."
            )
        await ctx.send(embed=embed)

    # ── !debug_channels ───────────────────────────────────────────────────────

    @commands.command()
    @commands.has_guild_permissions(administrator=True)
    async def debug_channels(self, ctx: commands.Context) -> None:
        embed = discord.Embed(title="📊 Channel Debug", color=0x7289DA)
        embed.add_field(
            name="Current Channel",
            value=f"{ctx.channel.mention}\nID: `{ctx.channel.id}`",
            inline=False,
        )
        embed.add_field(
            name="Is Image Channel?",
            value="✅ YES"
            if ctx.channel.id in config.IMAGE_CHANNEL_IDS
            else "❌ NO",
            inline=False,
        )
        lines = []
        for cid in config.IMAGE_CHANNEL_IDS:
            ch = self.bot.get_channel(cid)
            lines.append(
                f"{'✅' if ch else '❌'} `{cid}`"
                + (f" — {ch.mention}" if ch else " (not found)")
            )
        embed.add_field(
            name="All Image Channels",
            value="\n".join(lines) or "None registered.",
            inline=False,
        )
        await ctx.send(embed=embed)

    # ── /set-score ────────────────────────────────────────────────────────────

    @app_commands.command(
        name="set-score",
        description="Set a user's score to a specific value (Admin)",
    )
    @app_commands.describe(user="Target user", points="New score value")
    @app_commands.check(not_image_channel)
    async def set_score_cmd(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        points: int,
    ) -> None:
        if not config.features.ADMIN_SET_SCORE:
            return await interaction.response.send_message(
                "This feature is disabled.", ephemeral=True
            )
        if not is_admin(interaction):
            return await interaction.response.send_message(
                "❌ Admins only.", ephemeral=True
            )
        await db.admin_set_score(user.id, user.display_name, points)
        await interaction.response.send_message(
            f"✅ Set {user.mention}'s score to **{points} pts** 🏆",
            ephemeral=True,
        )
        log.info(
            "Admin set score: %s → %d pts (by %s)",
            user.display_name,
            points,
            interaction.user,
        )

    # ── /add-score ────────────────────────────────────────────────────────────

    @app_commands.command(
        name="add-score", description="Add points to a user (Admin)"
    )
    @app_commands.describe(
        user="Target user", points="Points to add (use negative to subtract)"
    )
    @app_commands.check(not_image_channel)
    async def add_score_cmd(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        points: int,
    ) -> None:
        if not config.features.ADMIN_ADD_SCORE:
            return await interaction.response.send_message(
                "This feature is disabled.", ephemeral=True
            )
        if not is_admin(interaction):
            return await interaction.response.send_message(
                "❌ Admins only.", ephemeral=True
            )
        new_score = await db.admin_add_score(user.id, user.display_name, points)
        action = "Added" if points >= 0 else "Removed"
        await interaction.response.send_message(
            f"✅ {action} **{abs(points)} pts** {'to' if points >= 0 else 'from'} {user.mention}. "
            f"New score: **{new_score} pts** 🏆",
            ephemeral=True,
        )
        log.info(
            "Admin add score: %s %+d pts → %d total (by %s)",
            user.display_name,
            points,
            new_score,
            interaction.user,
        )

    # ── /reset-score ──────────────────────────────────────────────────────────

    @app_commands.command(
        name="reset-score", description="Reset a user's score to 0 (Admin)"
    )
    @app_commands.describe(user="Target user")
    @app_commands.check(not_image_channel)
    async def reset_score_cmd(
        self, interaction: discord.Interaction, user: discord.Member
    ) -> None:
        if not config.features.ADMIN_RESET_SCORE:
            return await interaction.response.send_message(
                "This feature is disabled.", ephemeral=True
            )
        if not is_admin(interaction):
            return await interaction.response.send_message(
                "❌ Admins only.", ephemeral=True
            )
        await db.admin_reset_score(user.id)
        await interaction.response.send_message(
            f"✅ Reset {user.mention}'s score to **0 pts**.", ephemeral=True
        )
        log.info(
            "Admin reset score: %s (by %s)", user.display_name, interaction.user
        )

    # ── /reset-streak ─────────────────────────────────────────────────────────

    @app_commands.command(
        name="reset-streak", description="Reset a user's streak to 0 (Admin)"
    )
    @app_commands.describe(user="Target user")
    @app_commands.check(not_image_channel)
    async def reset_streak_cmd(
        self, interaction: discord.Interaction, user: discord.Member
    ) -> None:
        if not config.features.ADMIN_RESET_STREAK:
            return await interaction.response.send_message(
                "This feature is disabled.", ephemeral=True
            )
        if not is_admin(interaction):
            return await interaction.response.send_message(
                "❌ Admins only.", ephemeral=True
            )
        await db.admin_reset_streak(user.id)
        await interaction.response.send_message(
            f"✅ Reset {user.mention}'s streak to **0 days**.", ephemeral=True
        )
        log.info(
            "Admin reset streak: %s (by %s)",
            user.display_name,
            interaction.user,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))
