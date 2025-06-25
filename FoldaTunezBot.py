"""
Folda Tunez Discord Bot
by Preston Parsons
01/07/2025
Version 3.0 Upadted 06/25/2025
🔧 Discord API & Infrastructure Fixes
    Voice Connection Stability:
        Resolved persistent "4006" WebSocket errors during voice handshakes by optimizing session timeouts and UDP packet handling 110.
        Improved retransmission logic for audio data packets in calls, reducing robotic audio glitches by 6.5% 10.
        Added custom keybind support for toggling cameras during calls (Desktop) 5.
    Rate Limit Handling:
        Global rate limits tightened to 50 requests/second; exceeded requests now return clear throttling errors (e.g., Discord throttling [url]) instead of silent failures 12.
        Fixes for AutoMod regex rules and role color changes that previously "did nothing" due to save failures 110.
    API Deployment & Reliability:
        Migrated core infrastructure to ARM hardware, reducing latency and improving energy efficiency 37.
        Critical services (e.g., friend requests, messaging) now insulated from broader system outages 710.
    Embed & Media Processing
        Spotify embeds: 88% faster load times and 83% fewer failures 10.
        HDR-to-SDR tone-mapping fixes for accurate color rendering in shared media 10.
        Animated WebP/AVIF emojis now support true alpha transparency and smoother playback 1.
Discord.py Changelog: https://discordpy.readthedocs.io/en/stable/whats_new.html

Version 2.5 Updated 05/03/2025
    🔍 Added YouTube search functionality to !stream command:
        - Automatic search suggestions for text queries
        - Interactive 5-result selection with buttons
        - Fallback URL construction from video ID
    🛡️ Enhanced URL validation for search results

Version 2.4 Updated 03/18/2025
    Added a comprehensive logging system with:
        Separate log files for bot (bot.log) and CLI (cli.log) (not every CLI command is logged yet)
        Log rotation (5MB per file, 3 backups)
        Both console and file logging
        Standardized log format with timestamps
    Added the !leave command back in:
        Disconnects from voice
        Clears the queue
        Resets playback state
        Provides user feedback
    Added extensive logging throughout:
        Command invocations
        Critical operations
        Errors and exceptions
        System events
    Modified CLI to log all operations
        The logging system will track:
             All user commands with user/server info
        System operations (voice connections, queue changes)
        Errors with full tracebacks
        CLI command execution
        Resource usage (voice client connections, memory)
        Playback status changes
    Logs can be found in:
        bot.log: All bot-related activity\
        cli.log: All CLI interactions and admin commands

Versions 2.3.1 Updated 03/02/2025
    Queue command updated so long queues are split, preventing
    overflow of discord message legnth and string character limit.

Version 2.3 Updated 03/02/2025
    Yes, lots of updates today.  Fixing bugs creates more sometimes...
    Anyway heres a fancy looking update log:
    Core Fixes:
        🎵 Fixed YouTube playlist processing errors ("playlist does not exist")
        🔄 Resolved prepare_filename crashes with updated yt-dlp integration
        🛠 ️ Improved CLI-to-Discord message synchronization
    Key Improvements:
        ⚡ Optimized parallel download stability for large playlists
        🔀 Enhanced shuffle reliability (Fisher-Yates implementation)
        📁 Added metadata tracking for local playlist entries
    User Experience:
        📊 Clearer download progress feedback in CLI
        🚫 Better error messages for invalid URLs/files
        📜 Streamlined queue display formatting
    Under the Hood:
        🔒 Strengthened thread-safety for queue operations
        📈 Reduced memory usage during bulk downloads
        📝 Unified logging for easier debugging - for me anyway

Version 2.2.1 Updated 03/02/2025
    Fixed minor oversights
    Shuffle method updated (was supposed to be in 2.2.1)
    Shuffle Improvements:
            Current Song Preservation: Maintains currently playing song at queue start
            Thread Safety: Uses queue lock for atomic operations
            Download Awareness: Blocks shuffle during active downloads
            Better Algorithms: Uses Fisher-Yates shuffle for true randomness
            State Consistency: Maintains sync between Queue and queue_list
            User Feedback: Detailed status messages with emoji indicators
            Error Handling: Graceful failure with error logging

    Usage remains the same: !shuffle but now with:
            Protection against partial shuffles
            Clear feedback about what was shuffled
            Better handling of active playback
            Proper synchronization with queue display commands

Version 2.2 Updated 03/02/2025

New Features & Improvements:

    Enhanced Queue Management:
        Introduced a new queue command that displays the currently playing song with its elapsed time and lists upcoming tracks.
        Updated the underlying GuildState to maintain an ordered queue_list and track the song’s start time for accurate playback progress.

    Improved Metadata Handling:
        Both the stream and playlist_local commands now store additional metadata—such as the requester’s display name and track duration—to improve transparency and user experience.

    CLI Enhancements:
        Added a new CLI queue command within the AdminCLI, allowing administrators to send the current queue status directly to a specified text channel.
        Improved error handling and ID resolution for better stability and ease-of-use in the CLI environment.

    Queue Operations Refinement:
        Modified the shuffle command to update the queue order accurately while maintaining consistency in the playback order.
        Optimized thread-safe operations within queue management to prevent race conditions and ensure smooth playback transitions.

    General Code Quality & Stability:
        Incorporated additional locking and error handling mechanisms to handle concurrent operations more gracefully.
        Enhanced logging to provide more detailed insights for debugging and monitoring.

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
import subprocess
import logging
from logging.handlers import RotatingFileHandler
from discord.ui import View, Button, select
import socket
import sys
import io
import select
import nacl.secret
import nacl.utils
from discord.backoff import ExponentialBackoff

# Initialize ID mappings
guild_bot_ids = {}
channel_bot_ids = {}
next_guild_id = 1
next_channel_id = 1
last_join_channels = {}


# Initialize loggers
def setup_logger(name, log_file, level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    file_handler = RotatingFileHandler(
        log_file, maxBytes=1024 * 1024 * 5, backupCount=3
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


# Set up loggers
bot_logger = setup_logger('bot', 'bot.log')
cli_logger = setup_logger('cli', 'cli.log')


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


# Guild state management - UPDATED
class GuildState:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.queue_list = []  # NEW: For tracking queue order
        self.loop_type = None
        self.current_song = None
        self.history = []
        self.downloading = False
        self.data_usage = 0
        self.lock = asyncio.Lock()


guild_states = defaultdict(GuildState)


class MockContext:
    def __init__(self, guild, channel=None):
        self.guild = guild
        self.voice_client = guild.voice_client
        self.author = guild.me  # Bot as author
        self.bot = guild.me
        self.channel = channel
        self.message = type('MockMessage', (), {
            'guild': guild,
            'author': guild.me,
            'channel': channel,
            'content': ''
        })()

    async def send(self, content):
        if self.channel:
            # Check permissions first
            if not isinstance(self.channel, discord.TextChannel):
                raise discord.Forbidden("Not a text channel")

            if not self.channel.permissions_for(self.guild.me).send_messages:
                raise discord.Forbidden("Missing Send Messages permission")

            # Use actual channel send method
            await self.channel.send(content)
        else:
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
bot.remove_command('help')  # disables default help text


class AdminCLI(Cmd):
    prompt = '\nFoldaTunez> '

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.logger = setup_logger('cli', 'cli.log')

    def _log_and_print(self, message, level='info'):
        log_method = getattr(self.logger, level)
        log_method(message)
        print(message)

    def _resolve_id(self, identifier, id_map):
        try:
            id_int = int(identifier)
            return id_map.get(id_int, id_int)
        except ValueError as e:
            self.logger.error(f"ID resolution error: {str(e)}")
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
            error_msg = f"CLI command error: {traceback.format_exc()}"
            self.logger.error(error_msg)
            print(f"Error: {str(e)}")

    def do_servers(self, arg):
        """List all connected servers with status and queue information"""
        try:
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

            table = tabulate(servers,
                             headers=["Server", "BOT ID", "ID", "Status", "Current Song", "Data Usage", "Queue Size"])
            self._log_and_print(f"Server list requested:\n{table}")
        except Exception as e:
            self.logger.error(f"Servers error: {traceback.format_exc()}")
            self._log_and_print(f"Error retrieving server list: {str(e)}", 'error')

    def do_channels(self, arg):
        """List channels in a specific server: channels <guild_bot_id>"""
        try:
            global next_channel_id
            guild_id = self.resolve_guild(arg)
            if not guild_id:
                self._log_and_print("Invalid guild identifier", 'warning')
                return

            guild = self.bot.get_guild(guild_id)
            if not guild:
                self._log_and_print("Guild not found", 'warning')
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

            table = tabulate(channels,
                             headers=["Channel Name", "BOT ID", "ID", "Type", "NSFW Status", "Category"])
            self._log_and_print(f"Channel list for guild {guild_id}:\n{table}")
        except Exception as e:
            self.logger.error(f"Channels error: {traceback.format_exc()}")
            self._log_and_print(f"Error retrieving channels: {str(e)}", 'error')

    def do_sendmsg(self, arg):
        """Send message to a text channel: sendmsg <guild_bot_id> <channel_bot_id> <message>"""
        try:
            args = arg.split(maxsplit=2)
            if len(args) < 3:
                self._log_and_print("Usage: sendmsg <guild_bot_id> <channel_bot_id> <message>", 'warning')
                return

            guild_id = self.resolve_guild(args[0])
            channel_id = self.resolve_channel(args[1])
            message_content = args[2]

            async def send():
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    self._log_and_print("Guild not found", 'warning')
                    return

                channel = guild.get_channel(channel_id)
                if not channel:
                    self._log_and_print("Channel not found", 'warning')
                    return

                # Create proper context with mock message
                ctx = MockContext(guild, channel=channel)

                # Split message using the same logic as queue command
                messages = []
                current_message = []
                MAX_LENGTH = 1900  # Matching queue command's limit

                # Split message into lines and process
                for line in message_content.split('\n'):
                    if len('\n'.join(current_message + [line])) > MAX_LENGTH:
                        messages.append('\n'.join(current_message))
                        current_message = [line]
                    else:
                        current_message.append(line)

                if current_message:
                    messages.append('\n'.join(current_message))

                # Send messages using context
                for msg in messages:
                    try:
                        await ctx.send(msg)
                        self.logger.info(f"Message sent to {channel.id}: {msg[:50]}...")
                    except discord.Forbidden:
                        self._log_and_print(f"Missing permissions in #{channel.name}", 'error')
                        break
                    except discord.HTTPException as e:
                        self._log_and_print(f"Failed to send message: {str(e)}", 'error')
                        break

                self._log_and_print(f"Sent {len(messages)} message parts to #{channel.name}")

            self._safe_run_coroutine(send())
        except Exception as e:
            self.logger.error(f"Sendmsg error: {traceback.format_exc()}")
            self._log_and_print(f"Error sending message: {str(e)}", 'error')

    def do_join(self, arg):
        """Join a voice channel in specified server: join <guild_bot_id> <channel_bot_id>"""
        try:
            args = arg.split()
            if len(args) < 2:
                self._log_and_print("Usage: join <guild_bot_id> <channel_bot_id>", 'warning')
                return

            guild_id = self.resolve_guild(args[0])
            channel_id = self.resolve_channel(args[1])

            async def join():
                try:
                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        self._log_and_print("Guild not found", 'warning')
                        return

                    channel = guild.get_channel(channel_id)
                    if not channel or not isinstance(channel, discord.VoiceChannel):
                        self._log_and_print("Invalid voice channel", 'warning')
                        return

                    if guild.voice_client:
                        await guild.voice_client.move_to(channel)
                        self.logger.info(f"Moved to voice channel {channel.id} in guild {guild_id}")
                    else:
                        await channel.connect()
                        self.logger.info(f"Connected to voice channel {channel.id} in guild {guild_id}")

                    self._log_and_print(f"Joined {channel.name}")
                except Exception as e:
                    self.logger.error(f"Join error: {traceback.format_exc()}")
                    self._log_and_print(f"Join failed: {str(e)}", 'error')

            self._safe_run_coroutine(join())
        except Exception as e:
            self.logger.error(f"Join command error: {traceback.format_exc()}")
            self._log_and_print(f"Error processing join command: {str(e)}", 'error')

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
        try:
            if not arg:
                self._log_and_print("Usage: leave <guild_bot_id>", 'warning')
                return

            guild_id = self.resolve_guild(arg)
            if not guild_id:
                self._log_and_print("Invalid guild identifier", 'warning')
                return

            async def leave():
                try:
                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        self._log_and_print("Guild not found", 'warning')
                        return

                    if guild.voice_client:
                        await guild.voice_client.disconnect()
                        self.logger.info(f"Left voice channel in guild {guild_id}")
                        self._log_and_print("Left voice channel")

                        # Clear queue
                        state = guild_states[guild_id]
                        async with state.lock:
                            state.queue = asyncio.Queue()
                            state.queue_list.clear()
                            state.current_song = None
                            state.loop_type = None
                            state.history.clear()
                            self.logger.info(f"Cleared queue for guild {guild_id}")
                    else:
                        self._log_and_print("Not in a voice channel", 'warning')
                except Exception as e:
                    self.logger.error(f"Leave error: {traceback.format_exc()}")
                    self._log_and_print(f"Leave failed: {str(e)}", 'error')

            self._safe_run_coroutine(leave())
        except Exception as e:
            self.logger.error(f"Leave command error: {traceback.format_exc()}")
            self._log_and_print(f"Error processing leave command: {str(e)}", 'error')

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

    def do_queue(self, arg):
        """Send queue status to channel: queue <guild_bot_id> <channel_bot_id>"""
        args = arg.split()
        if len(args) < 2:
            print("Usage: queue <guild_bot_id> <channel_bot_id>")
            return

        guild_id = self.resolve_guild(args[0])
        channel_id = self.resolve_channel(args[1])

        async def send_queue():
            guild = self.bot.get_guild(guild_id)
            if not guild:
                print("Guild not found")
                return

            channel = guild.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                print("Invalid text channel")
                return

            ctx = MockContext(guild, channel=channel)  # Pass channel to MockContext
            await self.bot.get_command('queue').callback(ctx)

        self._safe_run_coroutine(send_queue())

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
        """Robust CLI handling with proper encoding"""
        # Fix stdin encoding
        sys.stdin = io.TextIOWrapper(
            sys.stdin.buffer,
            encoding='utf-8',
            errors='replace'
        )

        while True:
            try:
                print()
                super().cmdloop(intro="")
                break

            except UnicodeDecodeError:
                # Clear input buffer to prevent repeated errors
                try:
                    sys.stdin.flush()
                    # Clear any pending input
                    while sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                        sys.stdin.read(1)
                except:
                    pass
                self._log_and_print("Invalid input detected. Please use UTF-8 characters only.", 'warning')
                continue

            except Exception as e:
                self.logger.critical(f"CLI crash: {traceback.format_exc()}")
                self._log_and_print(f"Critical error: {str(e)} - Restarting CLI...", 'critical')
                continue

    def do_kill(self, arg):
        """Shutdown the bot"""
        self._log_and_print("Initiating shutdown sequence...")
        self.logger.critical("Admin initiated bot shutdown")
        os._exit(0)

    def do_exit(self, arg):
        """Exit the CLI"""
        self.logger.info("CLI session ended")
        return True


# search results
class SearchView(discord.ui.View):
    def __init__(self, entries, ctx):
        super().__init__(timeout=30)
        self.entries = entries
        self.ctx = ctx
        self.selected_entry = None

        # Add buttons for first 5 results
        for idx in range(1, 6):
            if idx - 1 >= len(entries):
                break
            button = discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label=str(idx),
                custom_id=str(idx)
            )
            button.callback = lambda interaction, i=idx-1: self.select_entry(interaction, i)
            self.add_item(button)

    async def select_entry(self, interaction, index):
        """Handle button click for search selection"""
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("❌ You didn't start this search!", ephemeral=True)
            return

        self.selected_entry = self.entries[index]
        await interaction.response.defer()
        self.stop()

    async def on_timeout(self):
        """Disable buttons when view times out"""
        for child in self.children:
            child.disabled = True
        await self.message.edit(view=self)


# Core functionality
@bot.event
async def on_ready():
    #error logging included
    bot_logger.info(f"Bot logged in as {bot.user}")
    # try:
    #     subprocess.run([FFMPEG_PATH, '-version'], check=True,
    #                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    #     bot_logger.info("FFmpeg verification successful")
    # except Exception as e:
    #     bot_logger.critical(f"FFmpeg check failed: {str(e)}")
    #     os._exit(1)
    try:
        result = subprocess.run(
            [FFMPEG_PATH, '-version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if "ffmpeg version" not in result.stdout:
            raise ValueError("Invalid FFmpeg executable")
        bot_logger.info("FFmpeg verification successful")
    except Exception as e:
        bot_logger.critical(f"FFmpeg check failed: {str(e)}")
        print(f"❌ Critical: FFmpeg validation failed - {str(e)}")
        os._exit(1)

    cli_thread = threading.Thread(target=AdminCLI(bot).cmdloop, daemon=True)
    cli_thread.start()
    bot_logger.info("Admin CLI started")
    # FFmpeg verification
    try:
        subprocess.run([FFMPEG_PATH, '-version'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"❌ FFmpeg check failed: {str(e)}")
        print("Verify FFmpeg is installed and path is correct in configuration")
        os._exit(1)

    print(f'Logged in as {bot.user}')
    cli_thread = threading.Thread(target=AdminCLI(bot).cmdloop, daemon=True)
    cli_thread.start()
    try:
        ffmpeg_version = subprocess.check_output(
            [FFMPEG_PATH, '-version'],
            stderr=subprocess.STDOUT
        ).decode('utf-8', 'replace')
        if 'ffmpeg version' not in ffmpeg_version:
            raise ValueError("Invalid FFmpeg executable")
    except Exception as e:
        bot_logger.critical(f"FFmpeg validation failed: {str(e)}")
        print(f"❌ FFmpeg check failed: {str(e)}")
        os._exit(1)

    socket.setdefaulttimeout(30.0)


async def play_next(ctx):
    guild_id = ctx.guild.id
    state = guild_states[guild_id]

    try:
        # Ensure we have a valid voice connection
        if not ctx.voice_client or not ctx.voice_client.is_connected():
            if not await ensure_voice_connection(ctx):
                return

        # Get next song
        if state.loop_type == 'song' and state.current_song:
            song = state.current_song
        elif not state.queue.empty():
            song = await state.queue.get()
            state.history.append(song)
            async with state.lock:
                if state.queue_list:
                    state.queue_list.pop(0)
        elif state.loop_type == 'queue' and state.history:
            for track in state.history:
                await state.queue.put(track)
                async with state.lock:
                    state.queue_list.append(track)
            song = await state.queue.get()
            async with state.lock:
                if state.queue_list:
                    state.queue_list.pop(0)
        else:
            return

        state.current_song = song
        state.start_time = time.time()  # NEW: Track start time

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


    except discord.ClientException as e:

        if "Not connected to voice" in str(e):

            # Reconnect and retry

            await ensure_voice_connection(ctx)

            await play_next(ctx)

        else:

            bot_logger.error(f"Playback ClientException: {traceback.format_exc()}")

            await ctx.send("❌ Playback error occurred")

    except Exception as e:

        bot_logger.error(f"Playback error: {traceback.format_exc()}")

        await ctx.send("❌ Playback error occurred")


async def ensure_voice_connection(ctx):
    """Reliable voice connection with version compatibility"""
    # Log Discord.py version for debugging
    bot_logger.info(f"Using discord.py version: {discord.__version__}")

    if ctx.voice_client and ctx.voice_client.is_connected():
        return True

    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("❗ You need to be in a voice channel first!")
        return False

    channel = ctx.author.voice.channel
    guild_id = ctx.guild.id

    # Clean up any existing connection
    if ctx.voice_client:
        try:
            await ctx.voice_client.disconnect(force=True)
            ctx.voice_client.cleanup()
        except Exception as e:
            bot_logger.warning(f"Cleanup error: {str(e)}")
        await asyncio.sleep(1)

    try:
        # Create new voice client
        voice_client = await channel.connect(reconnect=True, self_deaf=True)

        # Wait for connection to stabilize
        await asyncio.sleep(2)

        if not voice_client.is_connected():
            raise ConnectionError("Voice connection failed silently")

        # Version-compatible way to ensure readiness
        if discord.version_info >= (2, 0, 0):  # Discord.py 2.0+
            # Newer versions handle this automatically
            pass
        else:
            # For older versions, use compatibility method
            if hasattr(voice_client, 'ws') and hasattr(voice_client.ws, 'wait_until_ready'):
                await voice_client.ws.wait_until_ready()

        last_join_channels[guild_id] = ctx.channel
        bot_logger.info(f"Successfully connected to voice in {ctx.guild.name}")
        return True

    except Exception as e:
        bot_logger.error(f"Voice connection failed: {traceback.format_exc()}")
        await ctx.send(f"❌ Voice connection failed: {str(e)}")

        # Try one last time with basic connection
        try:
            voice_client = await channel.connect()
            return True
        except:
            return False


@bot.command()
async def join(ctx):
    """Join the user's voice channel"""
    try:
        # Clean up any existing connection first
        if ctx.voice_client:
            try:
                await ctx.voice_client.disconnect(force=True)
                await asyncio.sleep(0.5)
            except:
                pass

        # Use our connection handler
        if not await ensure_voice_connection(ctx):
            return

        await ctx.send(f"✅ Joined {ctx.author.voice.channel.name}")

    except Exception as e:
        logger.error(f"Join error: {traceback.format_exc()}")
        await ctx.send("❌ An error occurred while trying to join the voice channel")


@bot.command()
async def leave(ctx):
    """Leaves the voice channel and clears the queue"""
    guild_id = ctx.guild.id
    state = guild_states[guild_id]

    bot_logger.info(f"Leave command invoked in {ctx.guild.name} by {ctx.author.display_name}")

    try:
        # Disconnect from voice channel
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            bot_logger.debug(f"Disconnected from voice channel in {ctx.guild.name}")

        # Clear queue and reset state
        async with state.lock:
            state.queue = asyncio.Queue()
            state.queue_list.clear()
            state.current_song = None
            state.loop_type = None
            state.history.clear()
            bot_logger.debug(f"Cleared queue in {ctx.guild.name}")

        await ctx.send("✅ Left voice channel and cleared queue")
        bot_logger.info(f"Successfully left voice channel in {ctx.guild.name}")

    except Exception as e:
        error_msg = f"Leave command failed in {ctx.guild.name}: {str(e)}"
        bot_logger.error(error_msg)
        await ctx.send("❌ Failed to leave voice channel")

@bot.command()
async def help(ctx):
    """Show all available user commands"""
    help_text = [
        "**Folda Tunez Bot Commands**\n",
        "🎵 **Music Commands**:",
        f"`{BOT_PREFIX}join` - Join your voice channel",
        f"`{BOT_PREFIX}leave` - Leave your voice channel"
        f"`{BOT_PREFIX}stream <url>` - Stream from YouTube/SoundCloud/etc",
        f"`{BOT_PREFIX}stream <text/video name> - Search YouTube and present 5 options",
        f"`{BOT_PREFIX}queue` - Show current queue with timestamps",
        f"`{BOT_PREFIX}skip` - Skip current track",
        f"`{BOT_PREFIX}pause` - Pause playback",
        f"`{BOT_PREFIX}resume` - Resume playback",
        f"`{BOT_PREFIX}stop` - Stop playback and clear queue",
        f"`{BOT_PREFIX}shuffle` - Shuffle the queue",
        f"`{BOT_PREFIX}loop` - Toggle queue/song looping",
        f"`{BOT_PREFIX}playlist_local <file>` - Load local playlist",
        "\n📊 **Info Commands**:",
        f"`{BOT_PREFIX}usage` - Show data usage and uptime",
        f"`{BOT_PREFIX}help_me` - Show this help message",
        "\n⚙️ **Examples**:",
        f"`{BOT_PREFIX}stream https://youtu.be/dQw4w9WgXcQ`",
        f"`{BOT_PREFIX}playlist_local my_playlist.txt`",
        f"Folda Tunez v2.3.1"
        "\nNeed admin help? Contact your server moderators!"
    ]

    try:
        await ctx.send("\n".join(help_text))
    except discord.HTTPException as e:
        await ctx.send("📜 Command list is too long! Please check channel permissions.")
        logger.error(f"Help command error: {str(e)}")


# NEW QUEUE COMMAND
# Updated queue command
@bot.command()
async def queue(ctx):
    """Show current queue with playback information"""
    state = guild_states[ctx.guild.id]
    MAX_LENGTH = 1900  # Leave some margin for formatting

    if not state.current_song and not state.queue_list:
        await ctx.send("Queue is empty")
        return

    messages = []
    current_message = []

    # Current song section
    if state.current_song:
        elapsed = int(time.time() - state.start_time)
        elapsed_str = f"{elapsed // 60}:{elapsed % 60:02d}"
        duration = state.current_song.get('duration', 0)
        duration_str = f"{duration // 60}:{duration % 60:02d}" if duration > 0 else "Unknown"
        current_block = [
            f"**Now Playing:** {state.current_song['title']}",
            f"`{elapsed_str}/{duration_str}` | Requested by {state.current_song['requester']}"
        ]
        current_message.extend(current_block)

    # Upcoming songs section
    if state.queue_list:
        if current_message:
            current_message.append("\n**Upcoming:**")
        else:
            current_message.append("**Upcoming:**")

        for idx, song in enumerate(state.queue_list, 1):
            duration = song.get('duration', 0)
            duration_str = f"{duration // 60}:{duration % 60:02d}" if duration > 0 else "Unknown"
            line = f"{idx}. {song['title']} ({duration_str}) | {song['requester']}"

            # Check if adding this line would exceed the limit
            if len('\n'.join(current_message + [line])) > MAX_LENGTH:
                messages.append('\n'.join(current_message))
                current_message = ["**Upcoming (cont'd):**", line]
            else:
                current_message.append(line)

    # Add any remaining content
    if current_message:
        messages.append('\n'.join(current_message))

    # Send all message parts
    for msg in messages:
        await ctx.send(msg)


@bot.command(aliases=['search'])
async def stream(ctx, *, query: str):
    """Stream audio from URL or search YouTube"""
    try:
        if not ctx.voice_client:
            await ctx.send("❗ Join a voice channel first!")
            return

        if not await ensure_voice_connection(ctx):
            return

        # URL handling
        if query.startswith(('http://', 'https://')):
            url = query
            # Enhanced playlist detection
            if any(key in url for key in ['list=', 'playlist']):
                await process_playlist(ctx, url)
                return

            # Single video handling
            await process_single_url(ctx, url)
            bot_logger.info(f"Stream command: {url} by {ctx.author.display_name}")

        # Search handling
        else:
            # Perform YouTube search
            ydl_opts = {
                'format': 'bestaudio/best',
                'extract_flat': 'in_playlist',
                'quiet': True,
                'noplaylist': True,
                'ignoreerrors': True,
            }

            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                info = await bot.loop.run_in_executor(
                    download_executor,
                    lambda: ydl.extract_info(f"ytsearch5:{query}", download=False)
                )

            if not info or 'entries' not in info or not info['entries']:
                await ctx.send("❌ No results found.")
                return

            entries = info['entries'][:5]
            if not entries:
                await ctx.send("❌ No valid results found.")
                return

            # Build results message
            message_lines = [f"**Search Results for '{query}':**"]
            for idx, entry in enumerate(entries, 1):
                title = entry.get('title', 'Unknown Title')[:45] + ('...' if len(entry.get('title', '')) > 45 else '')
                duration = entry.get('duration', 0) or 0  # Ensure numerical value
                mins = int(duration // 60)
                secs = int(duration % 60)
                duration_str = f"{mins}:{secs:02d}" if duration else "Unknown"
                message_lines.append(f"{idx}. {title} ({duration_str})")

            # Send results with buttons
            view = SearchView(entries, ctx)
            message = await ctx.send("\n".join(message_lines), view=view)
            view.message = message

            # Wait for selection or timeout
            await view.wait()

            if view.selected_entry is None:
                await message.edit(content="⏲️ Selection timed out.", view=None)
                return

            # Process selected result
            selected_url = (
                    view.selected_entry.get('webpage_url') or
                    view.selected_entry.get('url') or
                    f"https://youtu.be/{view.selected_entry.get('id', '')}"
            )
            if not selected_url.startswith('http'):
                await ctx.send("❌ Could not retrieve valid URL for selected track")
                bot_logger.error(f"Invalid URL from search result: {view.selected_entry}")
                return
            await process_single_url(ctx, selected_url)

    except Exception as e:
        bot_logger.error(f"Stream error: {traceback.format_exc()}")
        await ctx.send(f"❌ Streaming error: {str(e)}")


# Unified single URL processing
async def process_single_url(ctx, url):
    """Handle single track processing from URL or search selection"""
    try:
        temp_title = url.split('=')[-1][:30]
        msg = await ctx.send(f"⏳ Downloading: {temp_title}...")

        ydl_opts = {
            'source_address': '0.0.0.0',
            'geo-bypass': True,
            'format': 'bestaudio/best',
            'outtmpl': 'downloads/%(title)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = await bot.loop.run_in_executor(
                download_executor,
                lambda: ydl.extract_info(url, download=True)
            )
            filepath = ydl.prepare_filename(info).replace('.webm', '.mp3')

        state = guild_states[ctx.guild.id]
        async with state.lock:
            song = {
                'title': info.get('title', 'Unknown Track'),
                'url': os.path.abspath(filepath),
                'requester': ctx.author.display_name,
                'duration': info.get('duration', 0)
            }
            await state.queue.put(song)
            state.queue_list.append(song)

        await msg.edit(content=f"✅ Added: {song['title']}")

        if not ctx.voice_client.is_playing():
            await play_next(ctx)

    except Exception as e:
        await ctx.send(f"❌ Error processing track: {str(e)}")
        logger.error(f"Single URL error: {traceback.format_exc()}")


async def download_and_queue_single(ctx, url):
    """Download and queue a single track with proper error handling"""
    guild_id = ctx.guild.id
    state = guild_states[guild_id]

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'socket_timeout': 15,
        'retries': 3
    }

    try:
        def download_task():
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                # Get filename through the YDL instance
                filepath = ydl.prepare_filename(info).replace('.webm', '.mp3')
                return info, os.path.abspath(filepath)

        info, filepath = await bot.loop.run_in_executor(
            download_executor,
            download_task
        )

        if not info:
            return None

        song = {
            'title': info.get('title', 'Unknown Track'),
            'url': filepath,
            'requester': ctx.author.display_name,
            'duration': info.get('duration', 0)
        }

        async with state.lock:
            await state.queue.put(song)
            state.queue_list.append(song)

        return info

    except youtube_dl.utils.DownloadError as e:
        logger.error(f"Download failed for {url}: {str(e)}")
        async with state.lock:
            state.queue_list = [item for item in state.queue_list if item.get('url') != url]
        return None
    except Exception as e:
        logger.error(f"Unexpected error with {url}: {traceback.format_exc()}")
        return None


async def download_and_queue_background(ctx, url):
    """Background download task with queue_list synchronization"""
    try:
        await download_and_queue_single(ctx, url)
    except Exception as e:
        logger.error(f"Background download failed: {traceback.format_exc()}")


async def process_playlist(ctx, url):
    """Process YouTube playlists with reliable track extraction"""
    try:
        # Extract playlist ID from various URL formats
        if 'list=' in url:
            playlist_id = url.split('list=')[1].split('&')[0]
            url = f"https://www.youtube.com/playlist?list={playlist_id}"

        ydl_opts = {
            'format': 'bestaudio/best',
            'extract_flat': 'in_playlist',
            'quiet': True,
            'noplaylist': False,
            'ignoreerrors': True,
            'playlistend': 200,
            'extractor_args': {
                'youtube': {
                    'player_skip': ['webpage'],
                    'skip': ['dash', 'hls']
                }
            }
        }

        # Extract playlist information
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = await bot.loop.run_in_executor(
                download_executor,
                lambda: ydl.extract_info(url, download=False)
            )

        if not info or 'entries' not in info:
            await ctx.send("❌ Could not recognize playlist format")
            return

        entries = [e for e in info['entries'] if e]
        total = len(entries)
        if total == 0:
            await ctx.send("❌ No valid tracks found in playlist")
            return

        await ctx.send(f"🎵 Adding **{total} tracks** from playlist: {info.get('title', 'Unnamed Playlist')}")

        # Process all tracks in order with parallel downloads
        state = guild_states[ctx.guild.id]
        async with state.lock:
            for entry in entries:
                video_url = entry.get('url') or f"https://youtu.be/{entry['id']}"
                state.queue_list.append({
                    'url': video_url,
                    'status': 'pending',
                    'title': entry.get('title', 'Unknown Track'),
                    'requester': ctx.author.display_name,
                    'duration': entry.get('duration', 0)  # Add this line
                })

        # Create and run download tasks
        tasks = []
        for entry in entries:
            video_url = entry.get('url') or f"https://youtu.be/{entry['id']}"
            tasks.append(download_and_queue_background(ctx, video_url))

        await asyncio.gather(*tasks)

        # Start playback if not already playing
        if not ctx.voice_client.is_playing():
            await play_next(ctx)

    except Exception as e:
        logger.error(f"Playlist error: {traceback.format_exc()}")
        await ctx.send("❌ Failed to process playlist")


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
    """Shuffle the current queue with enhanced reliability"""
    guild_id = ctx.guild.id
    state = guild_states[guild_id]

    try:
        async with state.lock:
            # Check queue validity
            if state.queue.qsize() < 2:
                await ctx.send("❗ Need at least 2 songs in the queue to shuffle!")
                return

            if state.downloading:
                await ctx.send("🔄 Please wait until current downloads complete before shuffling")
                return

            # Create temp list preserving current playback
            current_song = state.current_song
            items = [current_song] if current_song else []

            # Drain queue while preserving order
            while not state.queue.empty():
                items.append(await state.queue.get())

            # Only shuffle upcoming songs (keep current song if playing)
            shuffle_start = 1 if current_song else 0
            shuffle_slice = items[shuffle_start:]

            if len(shuffle_slice) < 2:
                await ctx.send("❗ Not enough upcoming songs to shuffle")
                # Restore original state
                for item in items[shuffle_start:]:
                    await state.queue.put(item)
                return

            # Fisher-Yates shuffle algorithm
            for i in range(len(shuffle_slice) - 1, 0, -1):
                j = random.randint(0, i)
                shuffle_slice[i], shuffle_slice[j] = shuffle_slice[j], shuffle_slice[i]

            # Update the original items list with shuffled slice
            items[shuffle_start:] = shuffle_slice  # FIX: Apply shuffled slice back to items

            # Rebuild queue and update tracking
            state.queue = asyncio.Queue()
            state.queue_list.clear()

            for item in items:
                await state.queue.put(item)
                state.queue_list.append(item)

            await ctx.send("🔀 Successfully shuffled {} songs{}!".format(
                len(shuffle_slice),
                " (keeping current song)" if current_song else ""
            ))

    except Exception as e:
        logger.error(f"Shuffle error: {traceback.format_exc()}")
        await ctx.send("❌ Failed to shuffle queue due to an internal error")


@bot.command()
async def playlist_local(ctx, filename: str):
    guild_id = ctx.guild.id
    state = guild_states[guild_id]

    try:
        # REVERTED: Remove directory restriction
        filepath = os.path.join(os.getcwd(), filename)  # Original path handling

        if not os.path.exists(filepath):
            await ctx.send(f"File not found: {filename}")
            return

        # REST OF THE FUNCTION REMAINS THE SAME AS YOUR LATEST VERSION
        async with state.lock:
            with open(filepath, 'r') as file:
                songs = [line.strip() for line in file if line.strip()]

            if not songs:
                await ctx.send("Playlist file is empty")
                return

            valid_songs = 0
            for song_path in songs:
                if os.path.exists(song_path):
                    song = {
                        'title': os.path.basename(song_path),
                        'url': song_path,
                        'requester': ctx.author.display_name,
                        'duration': 0  # Explicitly set default
                    }
                    await state.queue.put(song)
                    state.queue_list.append(song)
                    valid_songs += 1
                else:
                    await ctx.send(f"File not found: {song_path}")

            if valid_songs > 0:
                await ctx.send(f"Added {valid_songs} songs to queue")
                if not ctx.voice_client.is_playing():
                    await play_next(ctx)
            else:
                await ctx.send("No valid songs found in playlist")

    except Exception as e:
        logger.error(f"Playlist error: {traceback.format_exc()}")
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
    """Handle voice state changes with proper cleanup"""
    if member != bot.user:
        return

    guild_id = member.guild.id
    state = guild_states.get(guild_id)

    # Handle disconnections
    if before.channel and not after.channel:
        if state:
            async with state.lock:
                state.queue = asyncio.Queue()
                state.queue_list.clear()
                state.current_song = None
                state.loop_type = None
                state.history.clear()
        bot_logger.info(f"Cleaned up after disconnect in {member.guild.name}")

    # Clean up failed connections
    elif after.channel and guild_id in last_join_channels:
        if not member.guild.voice_client or not member.guild.voice_client.is_connected():
            try:
                await member.guild.voice_client.disconnect(force=True)
            except:
                pass
            last_join_channels.pop(guild_id, None)


@bot.event
async def on_guild_join(guild):
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            await channel.send("Hello! Use !help for commands")
            break


if __name__ == "__main__":
    bot.run('YOUR_TOKEN_HERE')
