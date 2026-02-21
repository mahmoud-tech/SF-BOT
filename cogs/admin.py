"""
cogs/admin.py — Admin-only commands (prefix + slash).

Prefix commands : !sync  !set_image  !remove_image  !list_image_channels  !debug_channels
Slash commands  : /add_score  /set_score  /reset_streak
"""

import logging

import core.database as db
import discord
from core.config import config
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("SF-BOT.admin")


# ── Shared check ─────────────────────────────────────────────────────────────


def not_image_channel(interaction: discord.Interaction) -> bool:
    return interaction.channel_id not in config.IMAGE_CHANNEL_IDS


# ── Cog ───────────────────────────────────────────────────────────────────────


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── Prefix: !sync ─────────────────────────────────────────────────────────

    @commands.command()
    @commands.has_guild_permissions(administrator=True)
    async def sync(self, ctx: commands.Context) -> None:
        """Sync slash commands to this guild immediately."""
        self.bot.tree.copy_global_to(guild=ctx.guild)
        synced = await self.bot.tree.sync(guild=ctx.guild)
        await ctx.send(f"✅ Synced **{len(synced)}** slash command(s).")
        log.info("Manual sync: %d command(s) → %s", len(synced), ctx.guild.name)

    # ── Prefix: !set_image ────────────────────────────────────────────────────

    @commands.command()
    @commands.has_guild_permissions(administrator=True)
    async def set_image(self, ctx: commands.Context) -> None:
        """Register this channel as an image (streak) channel."""
        cid = ctx.channel.id
        if cid not in config.IMAGE_CHANNEL_IDS:
            config.IMAGE_CHANNEL_IDS.append(cid)
            await ctx.send(f"✅ {ctx.channel.mention} is now an image channel.")
            log.info("Added image channel: %d", cid)
        else:
            await ctx.send(
                f"ℹ️ {ctx.channel.mention} is already an image channel."
            )

    # ── Prefix: !remove_image ─────────────────────────────────────────────────

    @commands.command()
    @commands.has_guild_permissions(administrator=True)
    async def remove_image(self, ctx: commands.Context) -> None:
        """Remove this channel from image channels."""
        cid = ctx.channel.id
        if cid in config.IMAGE_CHANNEL_IDS:
            config.IMAGE_CHANNEL_IDS.remove(cid)
            await ctx.send(
                f"✅ {ctx.channel.mention} removed from image channels."
            )
            log.info("Removed image channel: %d", cid)
        else:
            await ctx.send(f"❌ {ctx.channel.mention} is not an image channel.")

    # ── Prefix: !list_image_channels ──────────────────────────────────────────

    @commands.command()
    @commands.has_guild_permissions(administrator=True)
    async def list_image_channels(self, ctx: commands.Context) -> None:
        """List all registered image channels."""
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
            embed.description = "No image channels set. Use `!set_image` in a channel to add one."
        await ctx.send(embed=embed)

    # ── Prefix: !debug_channels ───────────────────────────────────────────────

    @commands.command()
    @commands.has_guild_permissions(administrator=True)
    async def debug_channels(self, ctx: commands.Context) -> None:
        """Debug: show current channel info and all registered image channels."""
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
        channel_lines = []
        for cid in config.IMAGE_CHANNEL_IDS:
            ch = self.bot.get_channel(cid)
            status = "✅" if ch else "❌"
            channel_lines.append(
                f"{status} `{cid}`"
                + (f" — {ch.mention}" if ch else " (not found)")
            )
        embed.add_field(
            name="All Image Channels",
            value="\n".join(channel_lines) or "None registered.",
            inline=False,
        )
        await ctx.send(embed=embed)

    # ── Slash: /add_score ─────────────────────────────────────────────────────

    @app_commands.command(
        name="add_score", description="Add points to a user (Admin only)"
    )
    @app_commands.describe(user="Target user", points="Points to add")
    @app_commands.check(not_image_channel)
    async def add_score_cmd(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        points: int,
    ) -> None:
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "❌ Admins only.", ephemeral=True
            )
        new_score = db.add_score(user.id, user.display_name, points)
        await interaction.response.send_message(
            f"✅ Added **{points} pts** to {user.mention}. New score: **{new_score}** 🏆",
            ephemeral=True,
        )

    # ── Slash: /set_score ─────────────────────────────────────────────────────

    @app_commands.command(
        name="set_score", description="Set a user's score (Admin only)"
    )
    @app_commands.describe(user="Target user", points="New score value")
    @app_commands.check(not_image_channel)
    async def set_score_cmd(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        points: int,
    ) -> None:
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "❌ Admins only.", ephemeral=True
            )
        db.set_score(user.id, user.display_name, points)
        await interaction.response.send_message(
            f"✅ Set {user.mention}'s score to **{points} pts** 🏆",
            ephemeral=True,
        )

    # ── Slash: /reset_streak ──────────────────────────────────────────────────

    @app_commands.command(
        name="reset_streak", description="Reset a user's streak (Admin only)"
    )
    @app_commands.describe(user="Target user")
    @app_commands.check(not_image_channel)
    async def reset_streak_cmd(
        self, interaction: discord.Interaction, user: discord.Member
    ) -> None:
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "❌ Admins only.", ephemeral=True
            )
        db.reset_streak(user.id)
        await interaction.response.send_message(
            f"✅ Reset {user.mention}'s streak to 0 days.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))
