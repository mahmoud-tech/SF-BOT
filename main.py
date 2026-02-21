import asyncio
import logging

import discord
from core.config import config
from core.database import init_db
from discord.ext import commands

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("StudyFlow Streak")

# --- Intents
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=config.PREFIX, intents=intents)

COGS = [
    "cogs.streaks",
    "cogs.admin",
]


@bot.event
async def on_ready() -> None:
    log.info(
        "Logged in as %s (ID: %s) | %d guild(s)",
        bot.user,
        bot.user.id,
        len(bot.guilds),
    )
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching, name="streaks 🔥 | /streak"
        )
    )
    for guild in bot.guilds:
        try:
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            log.info("Synced %d command(s) → %s", len(synced), guild.name)
        except Exception as exc:
            log.error("Sync failed for %s: %s", guild.name, exc)


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: discord.app_commands.AppCommandError,
) -> None:
    if isinstance(error, discord.app_commands.CheckFailure):
        await interaction.response.send_message(
            "❌ Commands are not allowed in image channels. Please use another channel.",
            ephemeral=True,
        )
    else:
        log.error("Slash command error: %s", error)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "❌ Something went wrong.", ephemeral=True
            )


async def main() -> None:
    if not config.DISCORD_TOKEN:
        log.critical("DISCORD_TOKEN is not set. Exiting.")
        raise SystemExit(1)

    init_db()

    async with bot:
        for cog in COGS:
            await bot.load_extension(cog)
            log.info("Loaded cog: %s", cog)
        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
