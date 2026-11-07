""" Folda-Tunez by Phaedra Parsons"""
""" The homebrew discord music bot"""
"""Bot entry point, events, and slash-command registration."""

import asyncio
import ctypes.util
import importlib
import logging
import os
import shutil
import subprocess

import discord
from discord import app_commands
from discord.ext import commands

from admin_cli import AdminCLI
from config import BOT_PREFIX, FFMPEG_PATH, TOKEN, VOICE_TIMEOUT
from console import ConsoleManager, ConsoleLogHandler
from contexts import InteractionContext
from guild_state import cleanup_all_downloads, guild_states
from loggers import bot_logger, cli_logger, yt_logger
from music import Music
from runtime import last_join_channels, stay_247


# ==================== Audio: load libopus ====================
def _load_opus() -> bool:
    """discord.py does not auto-load libopus on Linux. Load it explicitly."""
    if discord.opus.is_loaded():
        bot_logger.info("libopus already loaded")
        return True

    candidates = [
        ctypes.util.find_library("opus"),
        "libopus.so.0",
        "libopus.so",
        "/lib64/libopus.so.0",
        "/usr/lib/x86_64-linux-gnu/libopus.so.0",
        "/usr/lib/aarch64-linux-gnu/libopus.so.0",
        "/usr/lib/libopus.so.0",
        "/usr/local/lib/libopus.so.0",
    ]
    for path in filter(None, candidates):
        try:
            discord.opus.load_opus(path)
            if discord.opus.is_loaded():
                bot_logger.info(f"Loaded libopus from '{path}'")
                return True
        except Exception:
            continue

    bot_logger.critical(
        "Could not load libopus - voice playback will be SILENT. "
        "Install libopus0 and verify with: ldconfig -p | grep opus"
    )
    return False


def _check_voice_stack() -> bool:
    """Log a clear error for each missing piece of the voice pipeline.

    Discord now requires DAVE (E2EE) on voice connections; without the
    'davey' package the bot joins the channel but no audio ever arrives.
    """
    ok = True
    for mod, pkg in (("nacl", "PyNaCl"), ("davey", "davey")):
        try:
            importlib.import_module(mod)
        except ImportError:
            ok = False
            bot_logger.critical(
                f"Python package '{pkg}' is missing - voice will connect but stay silent. "
                f"Fix: ./dependencies.sh (inside the project, it installs requirements.txt)"
            )

    # davey 0.2.0 changed the DAVE API; discord.py 2.7.x doesn't speak it, so
    # the bot connects and plays but nothing is audible
    try:
        from importlib.metadata import version
        dv = version("davey")
        parts = tuple(int(p) for p in dv.split(".")[:2] if p.isdigit())
        if parts >= (0, 2):
            ok = False
            bot_logger.critical(
                f"davey {dv} is incompatible with discord.py {discord.__version__}: voice will be "
                "SILENT. Fix: ./dependencies.sh --recreate (installs davey<0.2 from requirements.txt)"
            )
    except Exception:
        pass

    ffmpeg_path = shutil.which(FFMPEG_PATH) or FFMPEG_PATH
    try:
        out = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=15, check=True,
        ).stdout
        if "libopus" not in out:
            ok = False
            bot_logger.critical(
                f"ffmpeg at '{ffmpeg_path}' has no libopus encoder - playback will be silent. "
                "Install a full ffmpeg build."
            )
    except (OSError, subprocess.SubprocessError) as e:
        ok = False
        bot_logger.critical(f"Could not run ffmpeg at '{ffmpeg_path}': {e}")

    if ok:
        bot_logger.info(f"Voice stack OK (discord.py {discord.__version__}, ffmpeg libopus present)")
    return ok


# ==================== Console ====================
console = ConsoleManager()


def _setup_console_logging():
    """Route python logging through ConsoleLogHandler; remove raw StreamHandlers."""
    console_handler = ConsoleLogHandler(console)

    for logger in (bot_logger, cli_logger, yt_logger):
        # Keep FileHandlers, remove only plain StreamHandlers (console output)
        logger.handlers = [
            h for h in logger.handlers
            if isinstance(h, logging.FileHandler)
            or not isinstance(h, logging.StreamHandler)
        ]
        logger.addHandler(console_handler)

    # Also route discord.py loggers through the console
    for name in (
        'discord', 'discord.client', 'discord.gateway',
        'discord.voice_state', 'discord.voice_client', 'discord.player',
    ):
        lg = logging.getLogger(name)
        lg.handlers = [h for h in lg.handlers if isinstance(h, logging.FileHandler)]
        lg.addHandler(console_handler)

    # FOLDA_DEBUG_VOICE=1 -> discord.py voice debug lines into bot.log.
    # gateway loggers are left alone: their DEBUG output includes tokens/keys.
    if os.getenv('FOLDA_DEBUG_VOICE'):
        for name in ('discord.voice_state', 'discord.voice_client', 'discord.player'):
            lg = logging.getLogger(name)
            lg.setLevel(logging.DEBUG)
            for h in bot_logger.handlers:
                if isinstance(h, logging.FileHandler):
                    lg.addHandler(h)
        bot_logger.info("FOLDA_DEBUG_VOICE set: voice debug logging enabled in bot.log")


_setup_console_logging()


# ==================== Bot ====================
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents, case_insensitive=True)


async def _register_slash_commands():
    music = bot.get_cog('Music')
    if not music:
        return

    @bot.tree.command(name='play', description='Play from URL or search YouTube')
    @app_commands.describe(query='YouTube URL or search query')
    async def slash_play(interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        ctx = InteractionContext(interaction)
        await music.stream(ctx, query=query)

    @bot.tree.command(name='skip', description='Skip the current track')
    async def slash_skip(interaction: discord.Interaction):
        await interaction.response.defer()
        ctx = InteractionContext(interaction)
        await music.skip_cmd(ctx)

    @bot.tree.command(name='pause', description='Pause playback')
    async def slash_pause(interaction: discord.Interaction):
        await interaction.response.defer()
        ctx = InteractionContext(interaction)
        await music.pause_cmd(ctx)

    @bot.tree.command(name='resume', description='Resume playback')
    async def slash_resume(interaction: discord.Interaction):
        await interaction.response.defer()
        ctx = InteractionContext(interaction)
        await music.resume_cmd(ctx)

    @bot.tree.command(name='np', description='Show now playing')
    async def slash_np(interaction: discord.Interaction):
        await interaction.response.defer()
        ctx = InteractionContext(interaction)
        await music.np_cmd(ctx)

    @bot.tree.command(name='queue', description='Show the queue')
    async def slash_queue(interaction: discord.Interaction):
        await interaction.response.defer()
        ctx = InteractionContext(interaction)
        await music.queue_cmd(ctx)

    @bot.tree.command(name='filter', description='Set an audio filter')
    @app_commands.describe(name='Filter name (bassboost, nightcore, 8d, ...)')
    async def slash_filter(interaction: discord.Interaction, name: str = ""):
        await interaction.response.defer()
        ctx = InteractionContext(interaction)
        await music.filter_cmd(ctx, name=name)

    try:
        await bot.tree.sync()
        bot_logger.info("Slash commands synced")
    except Exception as e:
        bot_logger.error(f"Slash command sync failed: {e}")


@bot.event
async def on_ready():
    bot_logger.info(f"Logged in as {bot.user}")
    bot.remove_command('help')
    await bot.add_cog(Music(bot))
    await _register_slash_commands()

    # Status bar callback (bottom row of the console)
    def status_text() -> str:
        playing = sum(
            1 for g in bot.guilds
            if guild_states.get(g.id) and guild_states[g.id].is_playing
        )
        parts = [
            f"Guilds:{len(bot.guilds)}",
            f"Latency:{bot.latency * 1000:.0f}ms",
        ]
        if playing:
            parts.append(f"Playing:{playing}")
        if console.guild_filter:
            parts.append(f"FILTER:guild {console.guild_filter}")
        return " | ".join(parts)

    console.status_callback = status_text

    cli = AdminCLI(bot, console)
    asyncio.create_task(cli.run_async(), name="admin-cli")

    try:
        subprocess.run([FFMPEG_PATH, '-version'], capture_output=True, check=True)
    except Exception:
        bot_logger.critical("FFmpeg not found!")
        await bot.close()


@bot.event
async def on_voice_state_update(member, before, after):
    if member != bot.user:
        return
    gid = member.guild.id
    state = guild_states.get(gid)
    if before.channel and not after.channel:
        if state:
            await state.stop_playback_loop()
        if stay_247.get(gid, False):
            async def _rejoin():
                await asyncio.sleep(3)
                ch = last_join_channels.get(gid)
                if ch and member.guild.voice_client is None:
                    try:
                        await ch.connect(timeout=VOICE_TIMEOUT, reconnect=True)
                        bot_logger.info(f"24/7 reconnected in guild {gid}")
                    except Exception as e:
                        bot_logger.error(f"24/7 reconnect failed: {e}")
            asyncio.create_task(_rejoin())
        elif member.guild.voice_client:
            try:
                await member.guild.voice_client.disconnect(force=True)
            except Exception:
                pass


@bot.event
async def on_close():
    await cleanup_all_downloads()
    console.cleanup()


if __name__ == "__main__":
    _load_opus()
    _check_voice_stack()
    try:
        bot.run(TOKEN)
    except KeyboardInterrupt:
        console.cleanup()