"""Bot entry point, events, and slash-command registration."""
import asyncio
import subprocess

import discord
from discord import app_commands
from discord.ext import commands

from admin_cli import AdminCLI
from config import BOT_PREFIX, FFMPEG_PATH, TOKEN, VOICE_TIMEOUT
from contexts import InteractionContext
from guild_state import cleanup_all_downloads, guild_states
from loggers import bot_logger
from music import Music
from runtime import last_join_channels, stay_247


intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

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
    print(f"Folda Tunez v0.5.2 - Logged in as {bot.user}")
    bot.remove_command('help')
    await bot.add_cog(Music(bot))

    await _register_slash_commands()

    cli = AdminCLI(bot)
    bot.loop.create_task(cli.run_async())

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


if __name__ == "__main__":
    bot.run(TOKEN)