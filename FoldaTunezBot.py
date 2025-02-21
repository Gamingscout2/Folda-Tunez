"""
Folda Tunez Discord Bot
by Preston Parsons
01/07/2025

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


guild_bot_ids = {}  # Maps BOT ID to guild ID
channel_bot_ids = {}  # Maps BOT ID to channel ID
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

# Thread pool executor for parallel downloads
download_executor = ThreadPoolExecutor(max_workers=MAX_THREADS)

# Guild state management
class GuildState:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.loop_type = None
        self.current_song = None
        self.history = []
        self.downloading = False
        self.data_usage = 0
        self.lock = asyncio.Lock()

guild_states = defaultdict(GuildState)

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)

# Admin CLI Implementation
class AdminCLI(Cmd):
    prompt = '\nFoldaTunez> '

    def __init__(self, bot):
        super().__init__()
        self.bot = bot


    def resolve_guild(self, identifier):
        """
        Accepts either a BOT ID or a full guild ID.
        Returns the full guild ID if found, else None.
        """
        try:
            id_int = int(identifier)
        except ValueError:
            return None
        # If the number is a BOT ID (i.e. a key in guild_bot_ids), return its mapped guild ID.
        if id_int in guild_bot_ids:
            return guild_bot_ids[id_int]
        # Otherwise, if the number is already a guild ID (i.e. one of the values), return it.
        if id_int in guild_bot_ids.values():
            return id_int
        return None


    def do_servers(self, arg):
        """List connected servers and their status"""
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


    def do_queue(self, arg):
        """Modify server queues: queue <server_id> <add/remove> <url/path>"""
        args = arg.split()
        if len(args) < 3:
            print("Usage: queue <server_id> <add/remove> <url/path>")
            return

        guild_id = int(args[0])
        action = args[1]
        content = ' '.join(args[2:])

        async def modify_queue():
            state = guild_states[guild_id]
            async with state.lock:
                if action == 'add':
                    if content.startswith('http'):
                        await self.bot.get_command('stream').callback(None, guild_id=guild_id, url=content)
                    else:
                        await self.bot.get_command('play').callback(None, guild_id=guild_id, path=content)
                    print(f"Added {content} to queue")
                elif action == 'remove':
                    items = []
                    while not state.queue.empty():
                        item = await state.queue.get()
                        if item['url'] != content:
                            items.append(item)
                    for item in items:
                        await state.queue.put(item)
                    print(f"Removed {content} from queue")
        asyncio.run_coroutine_threadsafe(modify_queue(), bot.loop).result()

    def do_help(self, arg):
            """Show all CLI commands"""
            help_text = """
    Admin CLI Commands:
    servers       - List all connected servers
    channels <guild_id> - List channels in a specific guild
    sendmsg <guild_id> <channel_id> <message> - Send message to a channel
    queue <server_id> <add/remove> <url/path> - Modify server queues
    kill          - Emergency shutdown
    usage         - Show global usage stats
    exit          - Exit the CLI
    
    Manage a Guild Session:
    join <guild_id> <channel_id>
    leave <guild_id>
    play <guild_id> <path>
    stream <guild_id> <url>
    skip <guild_id>
    stop <guild_id>
    pause <guild_id>
    resume <guild_id>
    shuffle <guild_id>
    loop <guild_id>
    playlist_local <guild_id> <filename>
    usage <guild_id>
    """
            print(help_text)

    def do_channels(self, arg):
        """List channels in a specific guild: channels <guild_bot_id>"""
        global next_channel_id
        if not arg.isdigit():
            print("Please provide a valid guild BOT ID")
            return

        guild_bot_id = int(arg)
        if guild_bot_id not in guild_bot_ids:
            print("Guild BOT ID not found")
            return

        guild_id = guild_bot_ids[guild_bot_id]
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
            channel_info = [
                channel.name,
                bot_id,
                channel.id,
                "Voice" if isinstance(channel, discord.VoiceChannel) else "Text",
                "NSFW" if getattr(channel, 'is_nsfw', lambda: False)() else "SFW",
                channel.category.name if channel.category else "No Category"
            ]
            channels.append(channel_info)

        print(tabulate(
            channels,
            headers=["Channel Name", "BOT ID", "ID", "Type", "NSFW Status", "Category"]
        ))


    def do_sendmsg(self, arg):
            """Send message to a channel: sendmsg <guild_id> <channel_id> <message>"""
            args = arg.split(maxsplit=2)
            if len(args) < 3:
                print("Usage: sendmsg <guild_id> <channel_id> <message>")
                return

            guild_id, channel_id, message = args

            async def send_message():
                guild = self.bot.get_guild(int(guild_id))
                if not guild:
                    print("Guild not found")
                    return

                channel = guild.get_channel(int(channel_id))
                if not channel:
                    print("Channel not found")
                    return

                if isinstance(channel, discord.TextChannel):
                    await channel.send(message)
                    print(f"Message sent to {channel.name}")
                else:
                    print("Not a text channel")

            asyncio.run_coroutine_threadsafe(send_message(), bot.loop).result()


    # def do_usage(self, arg):
    #     """Show global usage statistics"""
    #     total_bytes = sum(data['total_bytes'] for data in DATA_USAGE.values())
    #     total_mb = total_bytes / 1024 / 1024
    #     print(f"Total Data Usage: {total_mb:.2f} MB")
    #     print(f"Total Servers: {len(DATA_USAGE)}")
    #     print(f"Total Uptime: {time.time() - min(data['start_time'] for data in DATA_USAGE.values()):.2f} seconds")

    def do_join(self, arg):
        """Join a voice channel: join <guild_id_or_bot_id> <channel_bot_id>"""
        args = arg.split()
        if len(args) < 2:
            print("Usage: join <guild_id_or_bot_id> <channel_bot_id>")
            return

        guild_identifier = args[0]
        channel_identifier = args[1]

        guild_id = self.resolve_guild(guild_identifier)
        if guild_id is None:
            print("Invalid guild identifier")
            return

        try:
            channel_bot_id = int(channel_identifier)
        except ValueError:
            print("Channel BOT ID must be a number")
            return

        if channel_bot_id not in channel_bot_ids:
            print("Invalid channel BOT ID")
            return

        channel_id = channel_bot_ids[channel_bot_id]

        async def join_voice():
            guild = self.bot.get_guild(guild_id)
            if not guild:
                print("Guild not found")
                return

            channel = guild.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.VoiceChannel):
                print("Invalid voice channel")
                return

            await channel.connect()
            print(f"Joined {channel.name}")

        self._safe_run_coroutine(join_voice())


    def do_leave(self, arg):
        """Leave voice channel: leave <guild_id>"""
        if not arg:
            print("Usage: leave <guild_id>")
            return

        async def leave_voice():
            guild = self.bot.get_guild(int(arg))
            if not guild:
                print("Guild not found")
                return

            if guild.voice_client:
                await guild.voice_client.disconnect()
                print("Left voice channel")
            else:
                print("Not in a voice channel")

        self._safe_run_coroutine(leave_voice())

    def do_play(self, arg):
        """Play audio: play <guild_id_or_bot_id> <path>"""
        args = arg.split(maxsplit=1)
        if len(args) < 2:
            print("Usage: play <guild_id_or_bot_id> <path>")
            return

        guild_identifier, path = args
        guild_id = self.resolve_guild(guild_identifier)
        if guild_id is None:
            print("Invalid guild identifier")
            return

        self._safe_run_coroutine(
            self.bot.get_command('play').callback(None, guild_id=guild_id, path=path)
        )

    def do_stream(self, arg):
        """Stream audio: stream <guild_id_or_bot_id> <url>"""
        args = arg.split(maxsplit=1)
        if len(args) < 2:
            print("Usage: stream <guild_id_or_bot_id> <url>")
            return

        guild_identifier, url = args
        guild_id = self.resolve_guild(guild_identifier)
        if guild_id is None:
            print("Invalid guild identifier")
            return

        self._safe_run_coroutine(
            self.bot.get_command('stream').callback(None, guild_id=guild_id, url=url)
        )

    def do_skip(self, arg):
        """Skip current track: skip <guild_id>"""
        if not arg:
            print("Usage: skip <guild_id>")
            return

        self._safe_run_coroutine(
            self.bot.get_command('skip').callback(None, guild_id=int(arg))
        )

    def do_stop(self, arg):
        """Stop playback: stop <guild_id>"""
        if not arg:
            print("Usage: stop <guild_id>")
            return

        self._safe_run_coroutine(
            self.bot.get_command('stop').callback(None, guild_id=int(arg))
        )

    def do_pause(self, arg):
        """Pause playback: pause <guild_id>"""
        if not arg:
            print("Usage: pause <guild_id>")
            return

        self._safe_run_coroutine(
            self.bot.get_command('pause').callback(None, guild_id=int(arg))
        )

    def do_resume(self, arg):
        """Resume playback: resume <guild_id>"""
        if not arg:
            print("Usage: resume <guild_id>")
            return

        self._safe_run_coroutine(
            self.bot.get_command('resume').callback(None, guild_id=int(arg))
        )

    def do_shuffle(self, arg):
        """Shuffle queue: shuffle <guild_id>"""
        if not arg:
            print("Usage: shuffle <guild_id>")
            return

        self._safe_run_coroutine(
            self.bot.get_command('shuffle').callback(None, guild_id=int(arg))
        )

    def do_loop(self, arg):
        """Toggle loop mode: loop <guild_id>"""
        if not arg:
            print("Usage: loop <guild_id>")
            return

        self._safe_run_coroutine(
            self.bot.get_command('loop').callback(None, guild_id=int(arg))
        )

    def do_playlist_local(self, arg):
        """Load local playlist: playlist_local <guild_id> <filename>"""
        args = arg.split(maxsplit=1)
        if len(args) < 2:
            print("Usage: playlist_local <guild_id> <filename>")
            return

        guild_id, filename = args
        self._safe_run_coroutine(
            self.bot.get_command('playlist_local').callback(None, guild_id=int(guild_id), filename=filename)
        )

    def do_usage(self, arg):
        """Show usage stats: usage <guild_id>"""
        if not arg:
            print("Usage: usage <guild_id>")
            return

        self._safe_run_coroutine(
            self.bot.get_command('usage').callback(None, guild_id=int(arg))
        )


    def _safe_run_coroutine(self, coro):
        """Safely run a coroutine and handle errors"""
        try:
            future = asyncio.run_coroutine_threadsafe(coro, bot.loop)
            future.result(timeout=10)  # Wait for completion
        except Exception as e:
            print(f"Error: {str(e)}")
            logger.error(f"CLI command error: {e}")


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


# Tracked FFmpeg PCM Audio for data usage
class TrackedFFmpegPCMAudio(discord.FFmpegPCMAudio):
    def __init__(self, source, guild_id, **kwargs):
        super().__init__(source, **kwargs)
        self.guild_id = guild_id

    def read(self):
        data = super().read()
        if data:
            DATA_USAGE[self.guild_id]['total_bytes'] += len(data)
        return data


# Core bot functionality
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    cli_thread = threading.Thread(target=AdminCLI(bot).cmdloop, daemon=True)
    cli_thread.start()

@bot.command()
async def help_me(ctx):
    help_text = """
**Bot Commands List**:
**!join** - Join voice channel
**!leave** - Leave voice channel
**!play <path>** - Play local audio
**!stream <url>** - Stream from URL
**!skip** - Skip current track
**!stop** - Stop playback
**!loop** - Toggle loop modes
**!pause** - Pause playback
**!resume** - Resume playback
**!shuffle** - Shuffle queue
**!playlist_local <file>** - Load local playlist
**!usage** - Show data usage
**Folda Tunez v2.0**"""
    await ctx.send(help_text)


async def play_next(ctx):
    guild_id = ctx.guild.id
    state = guild_states[guild_id]

    if not ctx.voice_client:
        logger.error("No voice client found in play_next")
        return

    try:
        if state.loop_type == 'song' and state.current_song:
            song = state.current_song
        elif not state.queue.empty():
            song = await state.queue.get()
        elif state.loop_type == 'queue' and state.history:
            for track in state.history:
                await state.queue.put(track)
            song = await state.queue.get()
        else:
            await ctx.send("Playback finished!")
            return

        if not song:
            logger.error("No song found in play_next")
            return

        state.current_song = song
        state.history.append(song)

        source = TrackedFFmpegPCMAudio(
            song['url'],
            guild_id=guild_id,
            executable=FFMPEG_PATH,
            options="-loglevel error -buffer_size 16M"
        )

        ctx.voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))
        await ctx.send(f"Now playing: {song['title']}")

    except Exception as e:
        logger.error(f"Playback error in play_next: {e}")
        await ctx.send("Error occurred during playback")

@bot.command()
async def join(ctx):
    if ctx.author.voice:
        await ctx.author.voice.channel.connect()
        await ctx.send(f"Joined {ctx.author.voice.channel}!")
    else:
        await ctx.send("You need to be in a voice channel!")

@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Disconnected from voice channel.")
    else:
        await ctx.send("Not connected to any voice channel!")

@bot.command()
async def play(ctx, *, path: str):
    guild_id = ctx.guild.id
    state = guild_states[guild_id]

    if not os.path.exists(path):
        await ctx.send(f"Path not found: {path}")
        return

    if os.path.isfile(path):
        if os.path.splitext(path)[1].lower() in SUPPORTED_AUDIO_EXTENSIONS:
            song = {'title': os.path.basename(path), 'url': path}
            await state.queue.put(song)
            await ctx.send(f"Added {song['title']} to queue")
        else:
            await ctx.send(f"Unsupported file format: {path}")
        return

    added_count = 0
    for root, _, files in os.walk(path):
        for file in files:
            file_path = os.path.join(root, file)
            if os.path.splitext(file)[1].lower() in SUPPORTED_AUDIO_EXTENSIONS:
                song = {'title': os.path.basename(file_path), 'url': file_path}
                await state.queue.put(song)
                added_count += 1

    if added_count > 0:
        await ctx.send(f"Added {added_count} songs to queue")
        if not ctx.voice_client.is_playing():
            await play_next(ctx)
    else:
        await ctx.send("No supported audio files found")


@bot.command()
async def stream(ctx, url: str, guild_id: int = None):
    if guild_id:
        guild = bot.get_guild(guild_id)
        if not guild:
            if ctx:
                await ctx.send("Guild not found")
            else:
                print("Guild not found")
            return

        # Define an async version of print so that ctx.send can be awaited.
        async def async_print(message):
            print(message)

        class MockContext:
            def __init__(self, guild):
                self.guild = guild
                self.voice_client = guild.voice_client
                self.send = async_print  # Use the async function

        ctx = MockContext(guild)

    guild_id = ctx.guild.id
    state = guild_states[guild_id]

    if not ctx.voice_client:
        await ctx.send("Bot is not in a voice channel. Use !join first.")
        return

    if state.downloading:
        await ctx.send("Already downloading. Please wait.")
        return

    state.downloading = True
    loop = asyncio.get_event_loop()

    try:
        # First pass to get playlist structure
        playlist_ydl_opts = {
            'format': 'bestaudio/best',
            'extract_flat': 'in_playlist',
            'quiet': True,
        }

        with youtube_dl.YoutubeDL(playlist_ydl_opts) as ydl:
            info = await loop.run_in_executor(
                download_executor,
                lambda: ydl.extract_info(url, download=False)
            )

        if not info:
            await ctx.send("Failed to fetch playlist information")
            return

        if 'entries' not in info:
            # Single video handling
            await download_and_queue_single(ctx, url)
            return

        entries = info['entries']
        if not entries:
            await ctx.send("Playlist is empty")
            return

        # Download first track immediately
        first_url = entries[0]['url']
        first_info = await download_and_queue_single(ctx, first_url)
        if not first_info:
            await ctx.send("Failed to download the first track")
            return

        await ctx.send(f"**Added playlist:** {info['title']}")

        # Start playback if not already playing
        if ctx.voice_client and not ctx.voice_client.is_playing():
            await play_next(ctx)

        # Parallel download for remaining tracks
        remaining_urls = [entry['url'] for entry in entries[1:]]
        if remaining_urls:
            await ctx.send(f"⏳ Downloading {len(remaining_urls)} tracks in the background...")

            for track_url in remaining_urls:
                asyncio.create_task(
                    download_and_queue_background(ctx, track_url)
                )

    except Exception as e:
        logger.error(f"Stream error: {e}")
        await ctx.send(f"Error: {str(e)}")
    finally:
        state.downloading = False



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
        f"**Uptime:** {uptime//3600:.0f}h {(uptime%3600)//60:.0f}m"
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
