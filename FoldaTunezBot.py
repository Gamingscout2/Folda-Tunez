"""
Folda Tunez Discord Bot
by Preston Parsons
01/07/2025

Version 2.1 Updated 02/21/2025
    New Features and Improvements:

        CLI Help Documentation:

            Added comprehensive help documentation for previously undocumented CLI commands:

                stream: Stream audio from a URL in a specified server.
                servers: List all connected servers with status and queue information.
                channels: List channels in a specific server.
                join: Join a voice channel in a specified server.
                sendmsg: Send a message to a text channel.

            Improved usability and discoverability of CLI commands with detailed descriptions.

        CLI Command Enhancements:

            Improved error handling and user feedback for CLI commands.
            Added proper ID resolution for guild and channel identifiers in CLI commands.
            Enhanced the stream command to handle URL validation and provide better feedback during the download process.

        Code Quality Improvements:

            Refactored CLI command methods to ensure consistency and readability.
            Added docstrings to all CLI command methods for better maintainability.
            Improved logging for CLI operations to aid in debugging and monitoring.

        User Experience:

            Added a newline before the CLI prompt for better readability.
            Enhanced the servers command output with additional details, including current song, data usage, and queue size.
            Improved the channels command output with channel type, NSFW status, and category information.

    Bug Fixes:

        Fixed an issue where the stream command would not properly validate URLs before processing.
        Resolved a bug in the join command where it would fail to join a voice channel if the bot was already connected to another channel in the same guild.
        Addressed a minor issue in the sendmsg command where it would not properly handle messages with spaces.

    Performance Improvements:

        Optimized the stream command to handle parallel downloads more efficiently.
        Improved the responsiveness of CLI commands by ensuring proper thread-safe operations.

    Documentation Updates:

        Added detailed help documentation for all CLI commands.
        Updated the main script's docstring to reflect the new changes in Version 2.1.
        Improved inline comments for better code understanding.

Version 2.0 updated 02/20/2025
    New Admin Features:
        Interactive CLI with server monitoring
        Remote queue management
        Data usage tracking (!usage command)
        Emergency shutdown capability

    Performance Improvements:
        Parallel download processing
        Thread-safe queue operations
        Auto-reconnection logic
        Optimized audio streaming
        First song in playlist plays as soon as it is done downloading,
        while the rest of the playlist continues to download

Version 1.7 updated 02/09/2025
Changes:
    Re-built shuffling algorithm
    Queueing from !play and !stream fixed, allowing
    local play and streamed files to be in the same queue
    looping updated

Version 1.6 updated 01/30/2025
Changes:
    Per-Server queueing improved
    YouTube playback updated to working state

    Audio Extraction Updates:

        Added extract_audio and postprocessors to ydl_opts to ensure audio is extracted directly.
        Prefers mp3 format with a quality of 192kbps.

    Error Handling:

        Improved error handling for YouTube URL processing.

    Playlist Support:

        Handles playlists more efficiently by extracting all entries.

    Logging:

        Added logging to help debug issues.


Version 1.5.1 updated 01/08/2025
Changes:
    Support for per-server (guild) queue and playback,
    fixing the issue where playback was shared globally
    across multiple servers

    Stop function fixed

    Skip function fixed, if a loop is enabled it will retain the queue

    Looping updated to allow looping of the current track
    Three Loop States:
        None: No looping.
        'queue': Loop the entire queue.
        'song': Loop the currently playing song.
    Queue Refill for Looping:
        If the queue is empty and the loop type is 'queue', the bot refills the queue with previously played songs.
    Replay Current Song for 'song' Looping:
        The current_song is stored in guild_states to replay the current track if looping the song.
    Cycle Through States:
        The !loop command cycles through the three states.

Version 1.5 updated 01/07/2025
Features:
    Join a voice channel
    Play audio from a path on your local machine
    Stream audio from link (only DRM free links will work, no spotify as of 1.5)
    Full queue support and YouTube playlist support, including:
        Skip current track
        Pause/Resume Playback
        Loop entire queue
        Loop current song coming in next update

Subject to the license terms found at: https://sirobivan.org/pcl1-1.html
Copyright 2025 Parsons Computing
"""
import traceback
import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import os
import asyncio
import random
import platform
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from queue import Queue
import time
from cmd import Cmd
from tabulate import tabulate

# Initialize ID mappings
guild_bot_ids = {}
channel_bot_ids = {}
next_guild_id = 1
next_channel_id = 1

# Configuration
FFMPEG_PATH = "C:/ffmpeg/bin/ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
BOT_PREFIX = "!"
MAX_THREADS = 4
SUPPORTED_AUDIO_EXTENSIONS = {'.mp3', '.m4a', '.mp4', '.wav', '.flac', '.ogg', '.aac'}
DATA_USAGE = defaultdict(lambda: {'total_bytes': 0, 'start_time': time.time()})

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Thread pool executor
download_executor = ThreadPoolExecutor(max_workers=MAX_THREADS)


# Guild state management
class GuildState:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.loop_type = None  # 'queue', 'song', or None
        self.current_song = None
        self.history = []
        self.downloading = False
        self.data_usage = 0
        self.lock = asyncio.Lock()


guild_states = defaultdict(GuildState)


class MockContext:
    def __init__(self, guild):
        self.guild = guild
        self.voice_client = guild.voice_client
        self.author = guild.me
        self.bot = guild.me
        self.message = type('MockMessage', (), {
            'guild': guild,
            'author': guild.me,
            'channel': None
        })()

    async def send(self, content):
        print(f"[Bot] {content}")


class TrackedFFmpegPCMAudio(discord.FFmpegPCMAudio):
    def __init__(self, source, guild_id, **kwargs):
        super().__init__(
            source,
            executable=FFMPEG_PATH,
            options="-loglevel warning -analyzeduration 0 -bufsize 2048k",
            **kwargs
        )
        self.guild_id = guild_id

    def read(self):
        data = super().read()
        if data:
            DATA_USAGE[self.guild_id]['total_bytes'] += len(data)
        return data


intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)


class AdminCLI(Cmd):
    prompt = '\nFoldaTunez> '

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    def _resolve_id(self, identifier, id_map):
        try:
            id_int = int(identifier)
            return id_map.get(id_int, id_int)
        except ValueError:
            return None

    def resolve_guild(self, identifier):
        return self._resolve_id(identifier, guild_bot_ids)

    def resolve_channel(self, identifier):
        return self._resolve_id(identifier, channel_bot_ids)

    def _safe_run_coroutine(self, coro):
        try:
            future = asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
            future.result(timeout=10)
        except Exception as e:
            print(f"Error: {str(e)}")
            logger.error(f"CLI command error: {traceback.format_exc()}")

    # Updated CLI commands with proper ID resolution
    def do_servers(self, arg):
        """List all connected servers with status and queue information"""
        global next_guild_id
        servers = []
        for guild in self.bot.guilds:
            if guild.id not in guild_bot_ids.values():
                guild_bot_ids[next_guild_id] = guild.id
                next_guild_id += 1
            state = guild_states[guild.id]
            vc = guild.voice_client
            bot_id = [k for k, v in guild_bot_ids.items() if v == guild.id][0]
            servers.append([
                guild.name,
                bot_id,
                guild.id,
                "Connected" if vc else "Disconnected",
                state.current_song['title'][:20] + '...' if state.current_song else 'None',
                f"{state.data_usage / 1024 / 1024:.2f} MB",
                state.queue.qsize()
            ])
        print(tabulate(servers,
                       headers=["Server", "BOT ID", "ID", "Status", "Current Song", "Data Usage", "Queue Size"]))

    def do_channels(self, arg):
        """List channels in a specific server: channels <guild_bot_id>"""
        global next_channel_id
        guild_id = self.resolve_guild(arg)
        if not guild_id:
            print("Invalid guild identifier")
            return

        guild = self.bot.get_guild(guild_id)
        if not guild:
            print("Guild not found")
            return

        channels = []
        for channel in guild.channels:
            if channel.id not in channel_bot_ids.values():
                channel_bot_ids[next_channel_id] = channel.id
                next_channel_id += 1
            bot_id = [k for k, v in channel_bot_ids.items() if v == channel.id][0]
            channels.append([
                channel.name,
                bot_id,
                channel.id,
                "Voice" if isinstance(channel, discord.VoiceChannel) else "Text",
                "NSFW" if getattr(channel, 'is_nsfw', False) else "SFW",
                channel.category.name if channel.category else "No Category"
            ])
        print(tabulate(channels,
                       headers=["Channel Name", "BOT ID", "ID", "Type", "NSFW Status", "Category"]))

    def do_sendmsg(self, arg):
        """Send message to a text channel: sendmsg <guild_bot_id> <channel_bot_id> <message>"""
        args = arg.split(maxsplit=2)
        if len(args) < 3:
            print("Usage: sendmsg <guild_bot_id> <channel_bot_id> <message>")
            return

        guild_id = self.resolve_guild(args[0])
        channel_id = self.resolve_channel(args[1])
        message = args[2]

        async def send():
            guild = self.bot.get_guild(guild_id)
            if not guild:
                print("Guild not found")
                return

            channel = guild.get_channel(channel_id)
            if not channel:
                print("Channel not found")
                return

            # Ensure the channel is a text channel
            if not isinstance(channel, discord.TextChannel):
                print("Error: The specified channel is not a text channel")
                return

            # Check if the bot has permissions to send messages in the channel
            if not channel.permissions_for(guild.me).send_messages:
                print("Error: Bot does not have permission to send messages in this channel")
                return

            try:
                await channel.send(message)
                print(f"Message sent to {channel.name}")
            except discord.Forbidden:
                print("Error: Bot does not have permission to send messages in this channel")
            except discord.HTTPException as e:
                print(f"Error sending message: {e}")

        self._safe_run_coroutine(send())

    def do_join(self, arg):
        """Join a voice channel in specified server: join <guild_bot_id> <channel_bot_id>"""
        args = arg.split()
        if len(args) < 2:
            print("Usage: join <guild_bot_id> <channel_bot_id>")
            return

        guild_id = self.resolve_guild(args[0])
        channel_id = self.resolve_channel(args[1])

        async def join():
            guild = self.bot.get_guild(guild_id)
            if not guild:
                print("Guild not found")
                return

            channel = guild.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.VoiceChannel):
                print("Invalid voice channel")
                return

            if guild.voice_client:
                await guild.voice_client.move_to(channel)
            else:
                await channel.connect()
            print(f"Joined {channel.name}")

        self._safe_run_coroutine(join())

    def do_stream(self, arg):
        """Stream audio from URL in specified server: stream <guild_bot_id> <url>"""
        args = arg.split(maxsplit=1)
        if len(args) < 2:
            print("Usage: stream <guild_bot_id> <url>")
            return

        guild_id = self.resolve_guild(args[0])
        url = args[1]

        async def stream_audio():
            guild = self.bot.get_guild(guild_id)
            if not guild:
                print("Guild not found")
                return

            ctx = MockContext(guild)
            await self.bot.get_command('stream').callback(ctx, url=url)

        self._safe_run_coroutine(stream_audio())

    def do_leave(self, arg):
        """Leave voice channel: leave <guild_bot_id>"""
        if not arg:
            print("Usage: leave <guild_bot_id>")
            return

        guild_id = self.resolve_guild(arg)
        if not guild_id:
            print("Invalid guild identifier")
            return

        async def leave():
            guild = self.bot.get_guild(guild_id)
            if not guild:
                print("Guild not found")
                return

            if guild.voice_client:
                await guild.voice_client.disconnect()
                print("Left voice channel")
            else:
                print("Not in a voice channel")

        self._safe_run_coroutine(leave())

    def do_skip(self, arg):
        """Skip current track: skip <guild_bot_id>"""
        if not arg:
            print("Usage: skip <guild_bot_id>")
            return

        guild_id = self.resolve_guild(arg)
        if not guild_id:
            print("Invalid guild identifier")
            return

        async def skip():
            guild = self.bot.get_guild(guild_id)
            ctx = MockContext(guild)
            await self.bot.get_command('skip').callback(ctx)

        self._safe_run_coroutine(skip())

    def do_stop(self, arg):
        """Stop playback: stop <guild_bot_id>"""
        if not arg:
            print("Usage: stop <guild_bot_id>")
            return

        guild_id = self.resolve_guild(arg)
        if not guild_id:
            print("Invalid guild identifier")
            return

        async def stop():
            guild = self.bot.get_guild(guild_id)
            ctx = MockContext(guild)
            await self.bot.get_command('stop').callback(ctx)

        self._safe_run_coroutine(stop())

    def do_pause(self, arg):
        """Pause playback: pause <guild_bot_id>"""
        if not arg:
            print("Usage: pause <guild_bot_id>")
            return

        guild_id = self.resolve_guild(arg)
        if not guild_id:
            print("Invalid guild identifier")
            return

        async def pause():
            guild = self.bot.get_guild(guild_id)
            ctx = MockContext(guild)
            await self.bot.get_command('pause').callback(ctx)

        self._safe_run_coroutine(pause())

    def do_resume(self, arg):
        """Resume playback: resume <guild_bot_id>"""
        if not arg:
            print("Usage: resume <guild_bot_id>")
            return

        guild_id = self.resolve_guild(arg)
        if not guild_id:
            print("Invalid guild identifier")
            return

        async def resume():
            guild = self.bot.get_guild(guild_id)
            ctx = MockContext(guild)
            await self.bot.get_command('resume').callback(ctx)

        self._safe_run_coroutine(resume())

    def do_shuffle(self, arg):
        """Shuffle queue: shuffle <guild_bot_id>"""
        if not arg:
            print("Usage: shuffle <guild_bot_id>")
            return

        guild_id = self.resolve_guild(arg)
        if not guild_id:
            print("Invalid guild identifier")
            return

        async def shuffle():
            guild = self.bot.get_guild(guild_id)
            ctx = MockContext(guild)
            await self.bot.get_command('shuffle').callback(ctx)

        self._safe_run_coroutine(shuffle())

    def do_loop(self, arg):
        """Toggle loop mode: loop <guild_bot_id>"""
        if not arg:
            print("Usage: loop <guild_bot_id>")
            return

        guild_id = self.resolve_guild(arg)
        if not guild_id:
            print("Invalid guild identifier")
            return

        async def loop():
            guild = self.bot.get_guild(guild_id)
            ctx = MockContext(guild)
            await self.bot.get_command('loop').callback(ctx)

        self._safe_run_coroutine(loop())

    def do_playlist_local(self, arg):
        """Load local playlist: playlist_local <guild_bot_id> <filename>"""
        args = arg.split(maxsplit=1)
        if len(args) < 2:
            print("Usage: playlist_local <guild_bot_id> <filename>")
            return

        guild_id = self.resolve_guild(args[0])
        filename = args[1]

        async def load_playlist():
            guild = self.bot.get_guild(guild_id)
            ctx = MockContext(guild)
            await self.bot.get_command('playlist_local').callback(ctx, filename=filename)

        self._safe_run_coroutine(load_playlist())

    def do_usage(self, arg):
        """Show usage stats: usage <guild_bot_id>"""
        if not arg:
            print("Usage: usage <guild_bot_id>")
            return

        guild_id = self.resolve_guild(arg)
        if not guild_id:
            print("Invalid guild identifier")
            return

        async def show_usage():
            guild = self.bot.get_guild(guild_id)
            ctx = MockContext(guild)
            await self.bot.get_command('usage').callback(ctx)

        self._safe_run_coroutine(show_usage())

    def cmdloop(self, intro=None):
        """Override cmdloop to handle errors gracefully and print a newline before the prompt."""
        while True:
            try:
                print()  # Add a newline before the prompt
                super().cmdloop(intro="")
                break
            except Exception as e:
                print(f"Error: {str(e)}")
                logger.error(f"CLI error: {e}")
                continue

    def do_kill(self, arg):
        """Shutdown the bot"""
        print("Shutting down...")
        os._exit(0)

    def do_exit(self, arg):
        """Exit the CLI"""
        return True

# Core functionality
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    cli_thread = threading.Thread(target=AdminCLI(bot).cmdloop, daemon=True)
    cli_thread.start()


async def play_next(ctx):
    guild_id = ctx.guild.id
    state = guild_states[guild_id]

    try:
        if ctx.voice_client is None:
            return

        if ctx.voice_client.is_playing():
            return

        # Get next song
        if state.loop_type == 'song' and state.current_song:
            song = state.current_song
        elif not state.queue.empty():
            song = await state.queue.get()
            state.history.append(song)
        elif state.loop_type == 'queue' and state.history:
            for track in state.history:
                await state.queue.put(track)
            song = await state.queue.get()
        else:
            return

        state.current_song = song

        # Verify file exists
        if not os.path.exists(song['url']):
            await ctx.send(f"File missing: {song['title']}")
            return await play_next(ctx)

        # Create audio source
        source = TrackedFFmpegPCMAudio(song['url'], guild_id=guild_id)

        def after_playback(error):
            if error:
                logger.error(f"Playback error: {error}")
            asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)

        ctx.voice_client.play(source, after=after_playback)
        await ctx.send(f"Now playing: {song['title']}")

    except Exception as e:
        logger.error(f"Playback error: {traceback.format_exc()}")
        await ctx.send("Playback error occurred")


@bot.command()
async def stream(ctx, url: str):
    try:
        # Validate voice client
        if not ctx.voice_client:
            await ctx.send("❗ Join a voice channel first!")
            return

        # Validate URL
        if not url.startswith(('http://', 'https://')):
            await ctx.send("❗ Invalid URL format")
            return

        # Initial queue entry
        temp_title = url.split('=')[-1][:30]
        await ctx.send(f"⏳ Downloading: {temp_title}...")

        # Download configuration
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': 'downloads/%(title)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'noplaylist': True,
        }

        # Download track
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = await bot.loop.run_in_executor(
                download_executor,
                lambda: ydl.extract_info(url, download=True)
            )
            filepath = ydl.prepare_filename(info).replace('.webm', '.mp3')

        # Update queue
        state = guild_states[ctx.guild.id]
        async with state.lock:
            await state.queue.put({
                'title': info.get('title', 'Unknown Track'),
                'url': os.path.abspath(filepath)
            })

        await ctx.send(f"✅ Added: {info['title']}")

        # Start playback if idle
        if not ctx.voice_client.is_playing():
            await play_next(ctx)

    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")
        logger.error(f"Stream error: {traceback.format_exc()}")


async def download_and_queue_single(ctx, url):
    """Download and queue a single track"""
    guild_id = ctx.guild.id
    state = guild_states[guild_id]

    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': 'downloads/%(title)s.%(ext)s',
    }

    try:
        def download_task():
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=True)

        info = await asyncio.get_event_loop().run_in_executor(
            download_executor,
            download_task
        )

        if not info:
            logger.error(f"Failed to download: {url}")
            return None

        song = {'title': info['title'], 'url': info['requested_downloads'][0]['filepath']}
        async with state.lock:
            await state.queue.put(song)

        return info

    except Exception as e:
        logger.error(f"Download error for {url}: {e}")
        return None


async def download_and_queue_background(ctx, url):
    """Background download task for parallel processing"""
    try:
        info = await download_and_queue_single(ctx, url)
        logger.info(f"Background download complete: {info['title']}")
    except Exception as e:
        logger.error(f"Background download failed for {url}: {e}")

@bot.command()
async def skip(ctx):
    guild_id = ctx.guild.id
    state = guild_states[guild_id]

    if not ctx.voice_client or not ctx.voice_client.is_playing():
        await ctx.send("Nothing playing to skip")
        return

    if state.loop_type == 'queue' and state.current_song:
        await state.queue.put(state.current_song)

    ctx.voice_client.stop()
    await ctx.send("Skipping current track...")


@bot.command()
async def loop(ctx):
    guild_id = ctx.guild.id
    state = guild_states[guild_id]

    if state.loop_type is None:
        state.loop_type = 'queue'
        await ctx.send("Looping entire queue")
    elif state.loop_type == 'queue':
        state.loop_type = 'song'
        await ctx.send("Looping current song")
    else:
        state.loop_type = None
        await ctx.send("Looping disabled")


@bot.command()
async def stop(ctx):
    guild_id = ctx.guild.id
    state = guild_states[guild_id]

    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()

    while not state.queue.empty():
        await state.queue.get()

    state.loop_type = None
    state.current_song = None
    await ctx.send("Playback stopped and queue cleared")


@bot.command()
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("Playback paused")
    else:
        await ctx.send("Nothing playing to pause")


@bot.command()
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("Playback resumed")
    else:
        await ctx.send("Nothing paused to resume")


@bot.command()
async def shuffle(ctx):
    guild_id = ctx.guild.id
    state = guild_states[guild_id]

    items = []
    while not state.queue.empty():
        items.append(await state.queue.get())

    if len(items) < 2:
        await ctx.send("Not enough songs to shuffle")
        for item in items:
            await state.queue.put(item)
        return

    random.shuffle(items)
    for item in items:
        await state.queue.put(item)

    await ctx.send("Queue shuffled")


@bot.command()
async def playlist_local(ctx, filename: str):
    guild_id = ctx.guild.id
    state = guild_states[guild_id]

    filepath = os.path.join(os.getcwd(), filename)

    if not os.path.exists(filepath):
        await ctx.send(f"File not found: {filename}")
        return

    try:
        with open(filepath, 'r') as file:
            songs = [line.strip() for line in file if line.strip()]

        if not songs:
            await ctx.send("Playlist file is empty")
            return

        for song_path in songs:
            if os.path.exists(song_path):
                await state.queue.put({'title': os.path.basename(song_path), 'url': song_path})
            else:
                await ctx.send(f"File not found: {song_path}")

        await ctx.send(f"Added {len(songs)} songs to queue")

        if not ctx.voice_client.is_playing():
            await play_next(ctx)

    except Exception as e:
        await ctx.send(f"Error loading playlist: {str(e)}")


@bot.command()
async def usage(ctx):
    guild_id = ctx.guild.id
    total_mb = DATA_USAGE[guild_id]['total_bytes'] / 1024 / 1024
    uptime = time.time() - DATA_USAGE[guild_id]['start_time']
    await ctx.send(
        f"**Data Usage:** {total_mb:.2f} MB\n"
        f"**Uptime:** {uptime // 3600:.0f}h {(uptime % 3600) // 60:.0f}m"
    )


@bot.event
async def on_voice_state_update(member, before, after):
    if member == bot.user and before.channel is None and after.channel is not None:
        await after.channel.send("Use !help_me for commands")


@bot.event
async def on_guild_join(guild):
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            await channel.send("Hello! Use !help_me for commands")
            break


if __name__ == "__main__":
    bot.run('YOUR_TOKEN_HERE')
