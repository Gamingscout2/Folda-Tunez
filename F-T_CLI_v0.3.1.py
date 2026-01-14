"""
Folda Tunez Discord Bot
by Preston Parsons
01/07/2025
Version 0.3.1 Updated 11/17/2025 - Queue System & Playback Stability Fix

Fixed Issues:
    - Race conditions in playback loop causing "Already playing audio" errors
    - Queue system properly integrated with stream command
    - Loop functionality restored with proper state management
    - Playback stability with proper voice client state checking

Key Changes:
    - Added is_playing flag to prevent race conditions
    - Unified queue handling between stream and local playback
    - Enhanced playback loop with proper state synchronization
    - Fixed loop command state transitions
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
import datetime
import nacl.secret
import nacl.utils
from discord.backoff import ExponentialBackoff
import discord.voice_client


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
bot_logger = setup_logger('bot', 'logs/bot.log')
cli_logger = setup_logger('cli', 'logs/cli.log')


# Configuration
FFMPEG_PATH = "C:/ffmpeg/bin/ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
BOT_PREFIX = "!"
MAX_THREADS = 8  # Increased for better parallel processing
SUPPORTED_AUDIO_EXTENSIONS = {'.mp3', '.m4a', '.mp4', '.wav', '.flac', '.ogg', '.aac'}
DATA_USAGE = defaultdict(lambda: {'total_bytes': 0, 'start_time': time.time()})

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Thread pool executor
download_executor = ThreadPoolExecutor(max_workers=MAX_THREADS)


# Enhanced Guild state management with parallel processing support
class GuildState:
    def __init__(self, guild_id):
        self.guild_id = guild_id
        self.queue = asyncio.Queue()
        self.queue_list = []
        self.loop_type = None
        self.current_song = None
        self.history = []
        self.downloading = False
        self.data_usage = 0
        self.lock = asyncio.Lock()
        self.playback_task = None
        self.is_playing = False
        self.voice_client = None
        self.last_activity = time.time()
        self.start_time = None
        self.playback_active = False  # NEW: Prevent race conditions

    async def start_playback_loop(self, ctx):
        """Start dedicated playback loop for this guild"""
        if self.playback_task and not self.playback_task.done():
            return  # Already running

        self.playback_task = asyncio.create_task(self._playback_loop(ctx))
        bot_logger.info(f"Started playback loop for guild {self.guild_id}")

    async def stop_playback_loop(self):
        """Stop the playback loop for this guild"""
        if self.playback_task and not self.playback_task.done():
            self.playback_task.cancel()
            try:
                await self.playback_task
            except asyncio.CancelledError:
                pass
        self.is_playing = False
        self.playback_active = False
        bot_logger.info(f"Stopped playback loop for guild {self.guild_id}")

    async def _playback_loop(self, ctx):
        """Dedicated playback loop for this guild"""
        while True:
            try:
                if not self.playback_active and not self.is_playing:
                    await self._play_next_safe(ctx)
                await asyncio.sleep(1)  # Prevent tight looping
            except asyncio.CancelledError:
                break
            except Exception as e:
                bot_logger.error(f"Playback loop error in guild {self.guild_id}: {traceback.format_exc()}")
                await asyncio.sleep(5)  # Wait before retrying

    async def _play_next_safe(self, ctx):
        """Thread-safe next song playback with proper state management"""
        try:
            # Prevent multiple simultaneous playback attempts
            if self.playback_active or (ctx.voice_client and ctx.voice_client.is_playing()):
                return

            self.playback_active = True

            # Ensure we have a valid voice connection
            if not ctx.voice_client or not ctx.voice_client.is_connected():
                # Try to reconnect using the last known channel or author's channel
                channel = None
                if ctx.author and hasattr(ctx.author, "voice") and ctx.author.voice:
                    channel = ctx.author.voice.channel
                elif self.guild_id in last_join_channels:
                    channel = last_join_channels[self.guild_id]

                if channel and isinstance(channel, discord.VoiceChannel):
                    try:
                        await channel.connect(timeout=30.0, reconnect=True)
                        bot_logger.info(f"Reconnected to voice channel in guild {self.guild_id}")
                    except Exception as e:
                        bot_logger.error(f"Failed to reconnect to voice: {str(e)}")
                        self.is_playing = False
                        self.playback_active = False
                        return
                else:
                    bot_logger.warning(f"No voice channel available for reconnection in guild {self.guild_id}")
                    self.is_playing = False
                    self.playback_active = False
                    return

            # Get next song
            song = None
            if self.loop_type == 'song' and self.current_song:
                song = self.current_song
            elif not self.queue.empty():
                song = await self.queue.get()
                self.history.append(song)
                async with self.lock:
                    if self.queue_list:
                        self.queue_list.pop(0)
            elif self.loop_type == 'queue' and self.history:
                # Refill queue from history for looping
                for track in self.history:
                    await self.queue.put(track)
                    async with self.lock:
                        self.queue_list.append(track)
                if not self.queue.empty():
                    song = await self.queue.get()
                    async with self.lock:
                        if self.queue_list:
                            self.queue_list.pop(0)

            if not song:
                self.is_playing = False
                self.playback_active = False
                return

            self.current_song = song
            self.start_time = time.time()
            self.is_playing = True
            self.last_activity = time.time()

            # Verify file exists with better logging
            original_url = song['url']
            if not os.path.exists(original_url):
                bot_logger.error(f"File not found: {original_url}")
                await ctx.send(f"❌ File missing: {song['title']}")

                # Try to find alternative file path
                base_name = os.path.splitext(original_url)[0]
                for ext in ['.mp3', '.m4a', '.webm', '.mp4', '.wav', '.flac', '.ogg', '.aac']:
                    test_path = base_name + ext
                    if os.path.exists(test_path):
                        bot_logger.info(f"Found alternative file: {test_path}")
                        song['url'] = test_path
                        break

                # If still not found, skip to next song
                if not os.path.exists(song['url']):
                    bot_logger.error(f"File not found even after extension check: {song['title']}")
                    self.playback_active = False
                    # Try to play next song
                    asyncio.create_task(self._play_next_safe(ctx))
                    return

            # Verify the file is readable and has content
            try:
                file_size = os.path.getsize(song['url'])
                if file_size == 0:
                    bot_logger.error(f"Empty file: {song['url']}")
                    await ctx.send(f"❌ File is empty: {song['title']}")
                    self.playback_active = False
                    asyncio.create_task(self._play_next_safe(ctx))
                    return
                bot_logger.info(f"Playing file: {song['url']} (Size: {file_size} bytes)")
            except Exception as e:
                bot_logger.error(f"File access error: {song['url']} - {str(e)}")
                await ctx.send(f"❌ Cannot read file: {song['title']}")
                self.playback_active = False
                asyncio.create_task(self._play_next_safe(ctx))
                return

            # Create audio source with error handling
            try:
                source = TrackedFFmpegPCMAudio(song['url'], guild_id=self.guild_id)

                # Test if source is valid by reading a small amount
                if not hasattr(source, 'read'):
                    raise Exception("Invalid audio source created")

            except Exception as e:
                bot_logger.error(f"Failed to create audio source: {song['url']} - {str(e)}")
                await ctx.send(f"❌ Audio format error: {song['title']}")
                self.playback_active = False
                asyncio.create_task(self._play_next_safe(ctx))
                return

            def after_playback(error):
                self.playback_active = False
                self.is_playing = False
                if error:
                    logger.error(f"Playback error in guild {self.guild_id}: {error}")
                # Schedule next playback in the main event loop
                asyncio.run_coroutine_threadsafe(self._play_next_safe(ctx), bot.loop)

            try:
                ctx.voice_client.play(source, after=after_playback)
                await ctx.send(f"Now playing: {song['title']}")
            except discord.ClientException as e:
                if "Already playing audio" in str(e):
                    bot_logger.warning(f"Playback race condition in guild {self.guild_id}, retrying")
                    self.playback_active = False
                    await asyncio.sleep(1)
                    asyncio.create_task(self._play_next_safe(ctx))
                    return
                else:
                    raise

        except discord.ClientException as e:
            self.playback_active = False
            if "Not connected to voice" in str(e):
                bot_logger.warning(f"Voice connection lost in guild {self.guild_id}, will retry")
                await asyncio.sleep(2)
                asyncio.create_task(self._play_next_safe(ctx))
            else:
                bot_logger.error(f"Playback ClientException in guild {self.guild_id}: {traceback.format_exc()}")
                await ctx.send("❌ Playback error occurred")
        except Exception as e:
            self.playback_active = False
            bot_logger.error(f"Playback error in guild {self.guild_id}: {traceback.format_exc()}")
            await ctx.send("❌ Playback error occurred")


guild_states = {}


def get_guild_state(guild_id):
    """Thread-safe guild state retrieval"""
    if guild_id not in guild_states:
        guild_states[guild_id] = GuildState(guild_id)
    return guild_states[guild_id]


class MockContext:
    def __init__(self, guild, channel=None):
        self.guild = guild
        self.voice_client = guild.voice_client
        self.author = guild.me
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
            if not isinstance(self.channel, discord.TextChannel):
                raise discord.Forbidden("Not a text channel")

            if not self.channel.permissions_for(self.guild.me).send_messages:
                raise discord.Forbidden("Missing Send Messages permission")

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
bot.remove_command('help')

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

    def _safe_run_coroutine(self, coro, timeout=30):
        """Run coroutine with extended timeout support"""
        try:
            future = asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
            return future.result(timeout=timeout)
        except asyncio.TimeoutError:
            self.logger.warning("Coroutine timed out")
            print("Operation timed out - server may be busy")
            return None
        except Exception as e:
            error_msg = f"CLI command error: {traceback.format_exc()}"
            self.logger.error(error_msg)
            print(f"Error: {str(e)}")
            return None

    def do_servers(self, arg):
        """List all connected servers with status and queue information"""
        try:
            global next_guild_id
            servers = []
            for guild in self.bot.guilds:
                if guild.id not in guild_bot_ids.values():
                    guild_bot_ids[next_guild_id] = guild.id
                    next_guild_id += 1
                state = get_guild_state(guild.id)
                vc = guild.voice_client
                bot_id = [k for k, v in guild_bot_ids.items() if v == guild.id][0]

                servers.append([
                    guild.name,
                    bot_id,
                    guild.id,
                    "Connected" if vc else "Disconnected",
                    "Playing" if state.is_playing else "Idle",
                    state.current_song['title'][:20] + '...' if state.current_song else 'None',
                    f"{state.data_usage / 1024 / 1024:.2f} MB",
                    state.queue.qsize()
                ])

            table = tabulate(servers,
                             headers=["Server", "BOT ID", "ID", "VC Status", "Playback", "Current Song", "Data Usage", "Queue Size"])
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

                    # Update guild state with the new voice client
                    state = get_guild_state(guild_id)
                    state.voice_client = guild.voice_client
                    last_join_channels[guild_id] = channel

                    self._log_and_print(f"Joined {channel.name}")

                    # Start playback loop if not already running
                    if not state.playback_task or state.playback_task.done():
                        ctx = MockContext(guild)
                        await state.start_playback_loop(ctx)

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

            # Create a better mock context with proper voice handling
            # Try to find a text channel to send messages to
            text_channel = None
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    text_channel = channel
                    break

            if not text_channel:
                print("No text channel with send permissions found")
                return

            # Create enhanced mock context
            class EnhancedMockContext:
                def __init__(self, guild, channel):
                    self.guild = guild
                    self.voice_client = guild.voice_client
                    self.author = type('MockAuthor', (), {
                        'display_name': 'CLI Admin',
                        'voice': None,
                        'bot': False
                    })()
                    self.author.voice = type('MockVoice', (), {
                        'channel': guild.voice_client.channel if guild.voice_client else None
                    })()
                    self.bot = guild.me
                    self.channel = channel
                    self.message = type('MockMessage', (), {
                        'guild': guild,
                        'author': self.author,
                        'channel': channel,
                        'content': f'!stream {url}'
                    })()
                    # Add these attributes for compatibility
                    self.send = self._send_message

                async def _send_message(self, content):
                    """Send message to the channel"""
                    if self.channel:
                        try:
                            await self.channel.send(content)
                            print(f"[Bot → #{self.channel.name}] {content}")
                        except Exception as e:
                            print(f"[Bot Error] Failed to send message: {str(e)}")
                    else:
                        print(f"[Bot] {content}")

            ctx = EnhancedMockContext(guild, text_channel)

            # Check if bot is in a voice channel
            if not ctx.voice_client or not ctx.voice_client.is_connected():
                print("Bot is not in a voice channel. Use 'join' command first.")
                # Try to join default voice channel if available
                voice_channels = [ch for ch in guild.voice_channels]
                if voice_channels:
                    print(f"Attempting to join voice channel: {voice_channels[0].name}")
                    try:
                        await voice_channels[0].connect()
                        print(f"Joined {voice_channels[0].name}")
                    except Exception as e:
                        print(f"Failed to join voice channel: {str(e)}")
                        return
                else:
                    print("No voice channels available in this guild")
                    return

            # Call the stream command with the correct parameter name
            await self.bot.get_command('stream').callback(ctx, query=url)  # CHANGED: query=url instead of url=url
            print(f"Stream command executed for URL: {url}")

        self._safe_run_coroutine(stream_audio())

    def do_clear(self, arg):
        """Clear queue: clear <guild_bot_id>"""
        if not arg:
            print("Usage: clear <guild_bot_id>")
            return

        guild_id = self.resolve_guild(arg)
        if not guild_id:
            print("Invalid guild identifier")
            return

        async def clear():
            guild = self.bot.get_guild(guild_id)
            ctx = MockContext(guild)
            await self.bot.get_command('clear').callback(ctx)

        self._safe_run_coroutine(clear())

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

                        # Clear queue - UPDATED to use get_guild_state
                        state = get_guild_state(guild_id)
                        await state.stop_playback_loop()  # ADDED: Stop playback loop
                        async with state.lock:
                            state.queue = asyncio.Queue()
                            state.queue_list.clear()
                            state.current_song = None
                            state.loop_type = None
                            state.history.clear()
                            state.is_playing = False  # ADDED
                            state.playback_active = False  # NEW
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
                try:
                    sys.stdin.flush()
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

        # Clean up all guild states
        for guild_id, state in guild_states.items():
            asyncio.run_coroutine_threadsafe(state.stop_playback_loop(), self.bot.loop)

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
    bot_logger.info(f"Bot logged in as {bot.user}")

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

    socket.setdefaulttimeout(30.0)
    print(f'Logged in as {bot.user}')


async def ensure_voice_connection(ctx):
    """Enhanced voice connection handling - only used for initial joins"""
    bot_logger.info(f"Voice connection requested by {ctx.author} in {ctx.guild.name}")
    guild_id = ctx.guild.id

    if ctx.voice_client and ctx.voice_client.is_connected():
        return True

    channel = None
    if hasattr(ctx, "channel") and isinstance(ctx.channel, discord.VoiceChannel):
        channel = ctx.channel
    elif ctx.author and hasattr(ctx.author, "voice") and ctx.author.voice:
        channel = ctx.author.voice.channel

    if not channel:
        await ctx.send("❗ You need to be in a voice channel first (or specify one in CLI)!")
        return False

    if ctx.voice_client:
        try:
            await ctx.voice_client.disconnect(force=True)
            await asyncio.sleep(1)
        except Exception as e:
            bot_logger.warning(f"Cleanup error: {str(e)}")

    try:
        voice_client = await channel.connect(
            timeout=60.0,
            reconnect=True,
            self_deaf=True
        )

        # Store for potential reconnection
        last_join_channels[guild_id] = channel

        bot_logger.info(f"Connected to voice in {ctx.guild.name}")
        return True

    except Exception as e:
        bot_logger.error(f"Voice connection failed: {str(e)}")
        await ctx.send("❌ Failed to connect to voice channel")
        return False


async def play_next(ctx):
    """Start playback for a guild - uses dedicated guild playback loop"""
    guild_id = ctx.guild.id
    state = get_guild_state(guild_id)

    # Store the last join channel for reconnection
    if ctx.author and hasattr(ctx.author, "voice") and ctx.author.voice:
        last_join_channels[guild_id] = ctx.author.voice.channel
    elif hasattr(ctx, "channel") and isinstance(ctx.channel, discord.VoiceChannel):
        last_join_channels[guild_id] = ctx.channel

    await state.start_playback_loop(ctx)
    return False


def is_us_voice_server(endpoint: str) -> bool:
    """Check if voice endpoint is a US server (prone to 4006 errors)"""
    if not endpoint:
        return False

    us_indicators = [
        'dfw',  # Dallas
        'lax',  # Los Angeles
        'mia',  # Miami
        'ord',  # Chicago
        'atl',  # Atlanta
        'sea',  # Seattle
        'sjc',  # San Jose
        'us-',  # General US prefix
        'nyc',  # New York
        'sfo',  # San Francisco
    ]

    endpoint_lower = endpoint.lower()
    return any(indicator in endpoint_lower for indicator in us_indicators)

@bot.command()
async def join(ctx):
    """Join the user's voice channel"""
    try:
        if ctx.voice_client:
            try:
                await ctx.voice_client.disconnect(force=True)
                await asyncio.sleep(0.5)
            except:
                pass

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
    state = get_guild_state(guild_id)

    bot_logger.info(f"Leave command invoked in {ctx.guild.name} by {ctx.author.display_name}")

    try:
        # Stop playback loop first
        await state.stop_playback_loop()

        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            bot_logger.debug(f"Disconnected from voice channel in {ctx.guild.name}")

        async with state.lock:
            state.queue = asyncio.Queue()
            state.queue_list.clear()
            state.current_song = None
            state.loop_type = None
            state.history.clear()
            state.is_playing = False
            state.playback_active = False  # NEW
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
        f"`{BOT_PREFIX}leave` - Leave your voice channel",
        f"`{BOT_PREFIX}stream <url>` - Stream from YouTube/SoundCloud/etc",
        f"`{BOT_PREFIX}stream <text/video name>` - Search YouTube and present 5 options",
        f"`{BOT_PREFIX}queue` - Show current queue with timestamps",
        f"`{BOT_PREFIX}clear - Clears the server queue"
        f"`{BOT_PREFIX}skip` - Skip current track",
        f"`{BOT_PREFIX}pause` - Pause playback",
        f"`{BOT_PREFIX}resume` - Resume playback",
        f"`{BOT_PREFIX}stop` - Stop playback and clear queue",
        f"`{BOT_PREFIX}shuffle` - Shuffle the queue",
        f"`{BOT_PREFIX}loop` - Toggle queue/song looping",
        f"`{BOT_PREFIX}playlist_local <file>` - Load local playlist",
        "\n📊 **Info Commands**:",
        f"`{BOT_PREFIX}usage` - Show data usage and uptime",
        f"`{BOT_PREFIX}help` - Show this help message",
        "\n⚙️ **Examples**:",
        f"`{BOT_PREFIX}stream https://youtu.be/dQw4w9WgXcQ`",
        f"`{BOT_PREFIX}playlist_local my_playlist.txt`",
        "Folda Tunez v3.1",
        "\nNeed admin help? Contact your server moderators!"
    ]

    try:
        await ctx.send("\n".join(help_text))
    except discord.HTTPException as e:
        await ctx.send("📜 Command list is too long! Please check channel permissions.")
        logger.error(f"Help command error: {str(e)}")


@bot.command()
async def queue(ctx):
    """Show current queue with playback information"""
    state = get_guild_state(ctx.guild.id)
    MAX_LENGTH = 1900

    if not state.current_song and not state.queue_list:
        await ctx.send("Queue is empty")
        return

    messages = []
    current_message = []

    if state.current_song:
        elapsed = int(time.time() - state.start_time) if hasattr(state, 'start_time') else 0
        elapsed_str = f"{elapsed // 60}:{elapsed % 60:02d}"
        duration = state.current_song.get('duration', 0)
        duration_str = f"{duration // 60}:{duration % 60:02d}" if duration > 0 else "Unknown"
        current_block = [
            f"**Now Playing:** {state.current_song['title']}",
            f"`{elapsed_str}/{duration_str}` | Requested by {state.current_song['requester']}"
        ]
        current_message.extend(current_block)

    if state.queue_list:
        if current_message:
            current_message.append("\n**Upcoming:**")
        else:
            current_message.append("**Upcoming:**")

        for idx, song in enumerate(state.queue_list, 1):
            duration = song.get('duration', 0)
            duration_str = f"{duration // 60}:{duration % 60:02d}" if duration > 0 else "Unknown"
            line = f"{idx}. {song['title']} ({duration_str}) | {song['requester']}"

            if len('\n'.join(current_message + [line])) > MAX_LENGTH:
                messages.append('\n'.join(current_message))
                current_message = ["**Upcoming (cont'd):**", line]
            else:
                current_message.append(line)

    if current_message:
        messages.append('\n'.join(current_message))

    for msg in messages:
        await ctx.send(msg)


@bot.command()
async def clear(ctx):
    """Clear the current queue without stopping playback"""
    guild_id = ctx.guild.id
    state = get_guild_state(guild_id)

    # Get queue size before clearing for the response message
    queue_size = state.queue.qsize()

    # Clear the queue
    while not state.queue.empty():
        try:
            await state.queue.get()
        except:
            pass

    # Clear the queue list
    async with state.lock:
        state.queue_list.clear()

    await ctx.send(f"✅ Cleared {queue_size} songs from the queue")


@bot.command()
async def stream(ctx, *, query: str):
    """Stream audio from URL or search YouTube - FIXED to use queue system"""
    try:
        state = get_guild_state(ctx.guild.id)

        # URL handling
        if query.startswith(('http://', 'https://')):
            url = query
            if any(key in url for key in ['list=', 'playlist']):
                await process_playlist(ctx, url)
                return

            await process_single_url(ctx, url)
            bot_logger.info(f"Stream command: {url} by {ctx.author.display_name}")

        # Search handling
        else:
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

            message_lines = [f"**Search Results for '{query}':**"]
            for idx, entry in enumerate(entries, 1):
                title = entry.get('title', 'Unknown Title')[:45] + ('...' if len(entry.get('title', '')) > 45 else '')
                duration = entry.get('duration', 0) or 0
                mins = int(duration // 60)
                secs = int(duration % 60)
                duration_str = f"{mins}:{secs:02d}" if duration else "Unknown"
                message_lines.append(f"{idx}. {title} ({duration_str})")

            view = SearchView(entries, ctx)
            message = await ctx.send("\n".join(message_lines), view=view)
            view.message = message

            await view.wait()

            if view.selected_entry is None:
                await message.edit(content="⏲️ Selection timed out.", view=None)
                return

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

            # Get the actual filename that was downloaded
            # First, get the original filename
            original_file = ydl.prepare_filename(info)

            # Find the actual MP3 file that was created
            # The postprocessor creates a .mp3 file from whatever format was downloaded
            base_name = os.path.splitext(original_file)[0]
            filepath = base_name + '.mp3'

            # If mp3 file doesn't exist, try other possible extensions
            if not os.path.exists(filepath):
                possible_extensions = ['.mp3', '.m4a', '.webm', '.mp4']
                for ext in possible_extensions:
                    test_path = base_name + ext
                    if os.path.exists(test_path):
                        filepath = test_path
                        break

        state = get_guild_state(ctx.guild.id)
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

        # Verify file exists before playback
        if not os.path.exists(song['url']):
            await ctx.send(f"❌ Error: Downloaded file not found: {song['url']}")
            logger.error(f"File not found: {song['url']}")
            return

        # Start playback if not already playing
        if not state.is_playing:
            await play_next(ctx)

    except Exception as e:
        await ctx.send(f"❌ Error processing track: {str(e)}")
        logger.error(f"Single URL error: {traceback.format_exc()}")


async def download_and_queue_single(ctx, url):
    """Download and queue a single track"""
    guild_id = ctx.guild.id
    state = get_guild_state(guild_id)

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
            # Update the pending entry in queue_list
            for i, item in enumerate(state.queue_list):
                if item.get('url') == url and item.get('status') == 'pending':
                    state.queue_list[i] = song
                    break

        return info

    except youtube_dl.utils.DownloadError as e:
        logger.error(f"Download failed for {url}: {str(e)}")
        async with state.lock:
            state.queue_list = [item for item in state.queue_list if item.get('url') != url or item.get('status') != 'pending']
        return None
    except Exception as e:
        logger.error(f"Unexpected error with {url}: {traceback.format_exc()}")
        return None


async def download_and_queue_background(ctx, url):
    """Background download task"""
    try:
        await download_and_queue_single(ctx, url)
    except Exception as e:
        logger.error(f"Background download failed: {traceback.format_exc()}")


async def process_playlist(ctx, url):
    """Process YouTube playlists with reliable track extraction"""
    try:
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

        state = get_guild_state(ctx.guild.id)
        async with state.lock:
            for entry in entries:
                video_url = entry.get('url') or f"https://youtu.be/{entry['id']}"
                state.queue_list.append({
                    'url': video_url,
                    'status': 'pending',
                    'title': entry.get('title', 'Unknown Track'),
                    'requester': ctx.author.display_name,
                    'duration': entry.get('duration', 0)
                })

        tasks = []
        for entry in entries:
            video_url = entry.get('url') or f"https://youtu.be/{entry['id']}"
            tasks.append(download_and_queue_background(ctx, video_url))

        await asyncio.gather(*tasks)

        if not state.is_playing:
            await play_next(ctx)

    except Exception as e:
        logger.error(f"Playlist error: {traceback.format_exc()}")
        await ctx.send("❌ Failed to process playlist")


@bot.command()
async def skip(ctx):
    """Skip the current track"""
    guild_id = ctx.guild.id
    state = get_guild_state(guild_id)

    if not ctx.voice_client or not ctx.voice_client.is_playing():
        await ctx.send("Nothing playing to skip")
        return

    if state.loop_type == 'queue' and state.current_song:
        await state.queue.put(state.current_song)

    ctx.voice_client.stop()
    await ctx.send("Skipping current track...")


@bot.command()
async def loop(ctx):
    """Toggle loop mode - FIXED"""
    guild_id = ctx.guild.id
    state = get_guild_state(guild_id)

    if state.loop_type is None:
        state.loop_type = 'queue'
        await ctx.send("🔁 Looping entire queue")
    elif state.loop_type == 'queue':
        state.loop_type = 'song'
        await ctx.send("🔂 Looping current song")
    else:
        state.loop_type = None
        await ctx.send("➡️ Looping disabled")


@bot.command()
async def stop(ctx):
    """Stop playback and clear queue"""
    guild_id = ctx.guild.id
    state = get_guild_state(guild_id)

    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()

    # Clear queue
    while not state.queue.empty():
        await state.queue.get()

    async with state.lock:
        state.queue_list.clear()
        state.loop_type = None
        state.current_song = None
        state.is_playing = False
        state.playback_active = False

    await ctx.send("⏹️ Playback stopped and queue cleared")


@bot.command()
async def pause(ctx):
    """Pause playback"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Playback paused")
    else:
        await ctx.send("Nothing playing to pause")


@bot.command()
async def resume(ctx):
    """Resume playback"""
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Playback resumed")
    else:
        await ctx.send("Nothing paused to resume")


@bot.command()
async def shuffle(ctx):
    """Shuffle the current queue with enhanced reliability"""
    guild_id = ctx.guild.id
    state = get_guild_state(guild_id)

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
            items[shuffle_start:] = shuffle_slice

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
    """Load local playlist"""
    guild_id = ctx.guild.id
    state = get_guild_state(guild_id)

    try:
        filepath = os.path.join(os.getcwd(), filename)

        if not os.path.exists(filepath):
            await ctx.send(f"File not found: {filename}")
            return

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
                        'duration': 0
                    }
                    await state.queue.put(song)
                    state.queue_list.append(song)
                    valid_songs += 1
                else:
                    await ctx.send(f"File not found: {song_path}")

            if valid_songs > 0:
                await ctx.send(f"Added {valid_songs} songs to queue")
                if not state.is_playing:
                    await play_next(ctx)
            else:
                await ctx.send("No valid songs found in playlist")

    except Exception as e:
        logger.error(f"Playlist error: {traceback.format_exc()}")
        await ctx.send(f"Error loading playlist: {str(e)}")


@bot.command()
async def usage(ctx):
    """Show data usage and uptime"""
    guild_id = ctx.guild.id
    total_mb = DATA_USAGE[guild_id]['total_bytes'] / 1024 / 1024
    uptime = time.time() - DATA_USAGE[guild_id]['start_time']
    await ctx.send(
        f"**Data Usage:** {total_mb:.2f} MB\n"
        f"**Uptime:** {uptime // 3600:.0f}h {(uptime % 3600) // 60:.0f}m"
    )


# Event handlers
@bot.event
async def on_voice_state_update(member, before, after):
    """Enhanced voice state handling"""
    if member != bot.user:
        return

    guild_id = member.guild.id
    state = guild_states.get(guild_id)

    if before.channel and not after.channel:
        if state:
            await state.stop_playback_loop()
            async with state.lock:
                state.queue = asyncio.Queue()
                state.queue_list.clear()
                state.current_song = None
                state.loop_type = None
                state.history.clear()
                state.is_playing = False
                state.playback_active = False

        if member.guild.voice_client:
            try:
                member.guild.voice_client.cleanup()
                member.guild.voice_client = None
            except:
                pass

        bot_logger.info(f"Cleaned up after disconnect in {member.guild.name}")

    elif after.channel and not member.guild.voice_client:
        try:
            if guild_id in last_join_channels:
                del last_join_channels[guild_id]
            await member.guild.change_voice_state(channel=None)
            if hasattr(member.guild, '_voice_clients'):
                member.guild._voice_clients.clear()
        except:
            pass


@bot.event
async def on_voice_server_update(data):
    """Handle voice server updates"""
    guild_id = int(data['guild_id'])
    guild = bot.get_guild(guild_id)

    if guild and guild.voice_client:
        try:
            await guild.voice_client.on_voice_server_update(data)
        except Exception as e:
            bot_logger.error(f"Voice server update error: {str(e)}")


@bot.event
async def on_guild_join(guild):
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            await channel.send("Hello! Use !help for commands")
            break


if __name__ == "__main__":
    bot.run('YOUR_TOKEN_HERE')
