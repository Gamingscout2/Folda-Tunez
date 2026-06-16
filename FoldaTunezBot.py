"""
Folda Tunez Discord Bot
by Phaedra Parsons
Version 0.5.1
- Added case-insensitive command support (e.g., !sTrEam works now)
- Introduced !playnext command with three modes:
    • !playnext <queue_number>   - move existing queue item to next
    • !playnext <youtube_link>   - download and insert as next song
    • !playnext <local_file>     - add local file to front of queue
- Updated !help text to include the new playnext command
"""

import asyncio
import logging
import os
import random
import sys
import time
import traceback
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict, List, Any, Union

import discord
from discord.ext import commands
import yt_dlp as youtube_dl
from discord.ui import View, Button

# ==================== Configuration ====================
from dotenv import load_dotenv
load_dotenv()

TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if not TOKEN:
    raise ValueError("No Discord bot token found. Set DISCORD_BOT_TOKEN environment variable.")

BOT_PREFIX = "!"
FFMPEG_PATH = os.getenv('FFMPEG_PATH', "ffmpeg")
MAX_CONCURRENT_DOWNLOADS = int(os.getenv('MAX_CONCURRENT_DOWNLOADS', '5'))
DOWNLOAD_TIMEOUT = int(os.getenv('DOWNLOAD_TIMEOUT', '300'))
VOICE_TIMEOUT = int(os.getenv('VOICE_TIMEOUT', '60'))
MAX_PLAYLIST_ITEMS = int(os.getenv('MAX_PLAYLIST_ITEMS', '200'))

SUPPORTED_AUDIO_EXTENSIONS = {'.mp3', '.m4a', '.mp4', '.wav', '.flac', '.ogg', '.aac', '.webm'}

# ==================== Logging Setup ====================
def setup_logger(name: str, log_file: str, level=logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger

bot_logger = setup_logger('bot', 'bot.log')
cli_logger = setup_logger('cli', 'cli.log')
yt_logger = setup_logger('yt_dlp', 'yt_dlp.log', level=logging.WARNING)

# ==================== Data Tracking ====================
DATA_USAGE = defaultdict(lambda: {'total_bytes': 0, 'start_time': time.time()})
last_join_channels: Dict[int, discord.VoiceChannel] = {}

# ==================== Guild State Management ====================
@dataclass
class GuildState:
    """Represents the state of the bot in a specific guild."""
    guild_id: int
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    queue_list: List[Dict[str, Any]] = field(default_factory=list)
    history: List[Dict[str, Any]] = field(default_factory=list)
    current_song: Optional[Dict[str, Any]] = None
    loop_type: Optional[str] = None  # 'queue', 'song', or None
    is_playing: bool = False
    playback_active: bool = False
    playback_task: Optional[asyncio.Task] = None
    voice_client: Optional[discord.VoiceClient] = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    download_semaphore: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS))
    start_time: float = 0.0
    last_activity: float = field(default_factory=time.time)
    data_usage: int = 0

    async def start_playback_loop(self, ctx: commands.Context) -> None:
        """Start dedicated playback loop for this guild."""
        if self.playback_task and not self.playback_task.done():
            return
        self.playback_task = asyncio.create_task(self._playback_loop(ctx))
        bot_logger.info(f"Started playback loop for guild {self.guild_id}")

    async def stop_playback_loop(self) -> None:
        """Stop the playback loop."""
        if self.playback_task and not self.playback_task.done():
            self.playback_task.cancel()
            try:
                await self.playback_task
            except asyncio.CancelledError:
                pass
        self.is_playing = False
        self.playback_active = False
        bot_logger.info(f"Stopped playback loop for guild {self.guild_id}")

    async def _playback_loop(self, ctx: commands.Context) -> None:
        """Main playback loop."""
        while True:
            try:
                if not self.playback_active and not self.is_playing:
                    await self._play_next_safe(ctx)
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                bot_logger.error(f"Playback loop error in guild {self.guild_id}: {traceback.format_exc()}")
                await asyncio.sleep(5)

    async def _play_next_safe(self, ctx: commands.Context) -> None:
        """Thread-safe next song playback with proper state management."""
        try:
            if self.playback_active or (ctx.voice_client and ctx.voice_client.is_playing()):
                return

            self.playback_active = True

            # Ensure voice connection
            if not ctx.voice_client or not ctx.voice_client.is_connected():
                channel = None
                if hasattr(ctx.author, 'voice') and ctx.author.voice:
                    channel = ctx.author.voice.channel
                elif self.guild_id in last_join_channels:
                    channel = last_join_channels[self.guild_id]

                if channel and isinstance(channel, discord.VoiceChannel):
                    try:
                        await channel.connect(timeout=VOICE_TIMEOUT, reconnect=True)
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

            # Get next song, skipping any marked as removed
            song = None
            if self.loop_type == 'song' and self.current_song:
                song = self.current_song
            else:
                # Loop to skip songs flagged as 'removed'
                while not song:
                    if self.queue.empty():
                        if self.loop_type == 'queue' and self.history:
                            # Refill queue from history for looping
                            for track in self.history:
                                await self.queue.put(track)
                                async with self.lock:
                                    self.queue_list.append(track)
                            continue
                        else:
                            break  # no more songs

                    candidate = await self.queue.get()
                    # Keep queue_list in sync
                    async with self.lock:
                        if self.queue_list and self.queue_list[0] is candidate:
                            self.queue_list.pop(0)
                    if not candidate.get('removed'):
                        song = candidate
                        self.history.append(song)

            if not song:
                self.is_playing = False
                self.playback_active = False
                return

            self.current_song = song
            self.start_time = time.time()
            self.is_playing = True
            self.last_activity = time.time()

            # Verify file exists
            filepath = song['url']
            if not os.path.exists(filepath):
                bot_logger.error(f"File not found: {filepath}")
                await ctx.send(f"ERROR File missing: {song['title']}")
                # Try alternative extensions
                base = os.path.splitext(filepath)[0]
                for ext in SUPPORTED_AUDIO_EXTENSIONS:
                    test_path = base + ext
                    if os.path.exists(test_path):
                        song['url'] = test_path
                        break
                else:
                    self.playback_active = False
                    asyncio.create_task(self._play_next_safe(ctx))
                    return

            # Verify file readable
            try:
                if os.path.getsize(song['url']) == 0:
                    raise ValueError("Empty file")
            except Exception as e:
                bot_logger.error(f"File access error: {song['url']} - {str(e)}")
                await ctx.send(f"ERROR Cannot read file: {song['title']}")
                self.playback_active = False
                asyncio.create_task(self._play_next_safe(ctx))
                return

            # Create audio source
            try:
                source = TrackedFFmpegPCMAudio(song['url'], guild_id=self.guild_id)
            except Exception as e:
                bot_logger.error(f"Failed to create audio source: {song['url']} - {str(e)}")
                await ctx.send(f"ERROR Audio format error: {song['title']}")
                self.playback_active = False
                asyncio.create_task(self._play_next_safe(ctx))
                return

            def after_playback(error):
                self.playback_active = False
                self.is_playing = False
                if error:
                    bot_logger.error(f"Playback error in guild {self.guild_id}: {error}")
                asyncio.run_coroutine_threadsafe(self._play_next_safe(ctx), bot.loop)

            try:
                ctx.voice_client.play(source, after=after_playback)
                await ctx.send(f"Now Playing: **{song['title']}**")
            except discord.ClientException as e:
                if "Already playing audio" in str(e):
                    bot_logger.warning(f"Playback race condition in guild {self.guild_id}, retrying")
                    self.playback_active = False
                    await asyncio.sleep(1)
                    asyncio.create_task(self._play_next_safe(ctx))
                    return
                else:
                    raise
        except Exception as e:
            self.playback_active = False
            bot_logger.error(f"Playback error in guild {self.guild_id}: {traceback.format_exc()}")
            await ctx.send("ERROR Playback error occurred")

            def after_playback(error):
                self.playback_active = False
                self.is_playing = False
                if error:
                    bot_logger.error(f"Playback error in guild {self.guild_id}: {error}")
                asyncio.run_coroutine_threadsafe(self._play_next_safe(ctx), bot.loop)

            try:
                ctx.voice_client.play(source, after=after_playback)
                await ctx.send(f"Now Playing: **{song['title']}**")
            except discord.ClientException as e:
                if "Already playing audio" in str(e):
                    bot_logger.warning(f"Playback race condition in guild {self.guild_id}, retrying")
                    self.playback_active = False
                    await asyncio.sleep(1)
                    asyncio.create_task(self._play_next_safe(ctx))
                    return
                else:
                    raise
        except Exception as e:
            self.playback_active = False
            bot_logger.error(f"Playback error in guild {self.guild_id}: {traceback.format_exc()}")
            await ctx.send("ERROR Playback error occurred")

guild_states: Dict[int, GuildState] = {}

def get_guild_state(guild_id: int) -> GuildState:
    """Thread-safe guild state retrieval."""
    if guild_id not in guild_states:
        guild_states[guild_id] = GuildState(guild_id)
    return guild_states[guild_id]

# ==================== Audio Source with Tracking ====================
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

# ==================== Mock Context for CLI ====================
class MockContext:
    def __init__(self, guild: discord.Guild, channel: Optional[discord.TextChannel] = None):
        self.guild = guild
        self.voice_client = guild.voice_client
        self.author = type('MockAuthor', (), {
            'display_name': 'CLI Admin',
            'voice': type('MockVoice', (), {'channel': guild.voice_client.channel if guild.voice_client else None})()
        })()
        self.bot = guild.me
        self.channel = channel
        self.message = type('MockMessage', (), {
            'guild': guild,
            'author': self.author,
            'channel': channel,
            'content': ''
        })()

    async def send(self, content):
        if self.channel:
            try:
                await self.channel.send(content)
            except Exception as e:
                print(f"[Bot Error] Failed to send message: {e}")
        else:
            print(f"[Bot] {content}")

# ==================== Downloader Module ====================
class Downloader:
    """Handles all audio downloading with yt-dlp and parallel processing."""

    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_DOWNLOADS)
        self.ydl_opts_base = {
            'format': 'bestaudio/best',
            'outtmpl': 'downloads/%(title)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'socket_timeout': DOWNLOAD_TIMEOUT,
            'retries': 3,
            'quiet': True,
            'no_warnings': True,
            'logger': yt_logger,
        }

    async def extract_info(self, url: str, download: bool = False, process: bool = True) -> dict:
        """Extract info from URL, optionally downloading."""
        opts = self.ydl_opts_base.copy()
        if not download:
            opts['extract_flat'] = 'in_playlist'

        def _extract():
            with youtube_dl.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=download, process=process)

        return await asyncio.get_event_loop().run_in_executor(self.executor, _extract)

    async def download_single(self, url: str) -> Optional[Dict[str, Any]]:
        """Download a single track and return song dict."""
        try:
            info = await self.extract_info(url, download=True)
            if not info:
                return None

            # Determine actual file path
            filepath = youtube_dl.YoutubeDL(self.ydl_opts_base).prepare_filename(info)
            base = os.path.splitext(filepath)[0]
            for ext in SUPPORTED_AUDIO_EXTENSIONS:
                test_path = base + ext
                if os.path.exists(test_path):
                    filepath = test_path
                    break

            return {
                'title': info.get('title', 'Unknown Track'),
                'url': os.path.abspath(filepath),
                'webpage_url': info.get('webpage_url', url),
                'duration': info.get('duration', 0),
            }
        except Exception as e:
            bot_logger.error(f"Download failed for {url}: {str(e)}")
            return None

    async def download_playlist_batch(self, entries: List[Dict], requester: str,
                                     progress_callback=None) -> List[Dict]:
        """Download multiple playlist entries concurrently with semaphore control."""
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)

        async def download_one(entry):
            async with semaphore:
                video_url = entry.get('webpage_url') or f"https://youtu.be/{entry['id']}"
                song = await self.download_single(video_url)
                if song:
                    song['requester'] = requester
                    if progress_callback:
                        await progress_callback(song)
                return song

        tasks = [download_one(e) for e in entries if e]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if isinstance(r, dict)]

downloader = Downloader()

# ==================== Music Cog ====================
class Music(commands.Cog):
    """Music playback commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def ensure_voice(self, ctx: commands.Context) -> bool:
        """Ensure bot is connected to a voice channel."""
        if ctx.voice_client and ctx.voice_client.is_connected():
            return True

        if not ctx.author.voice:
            await ctx.send("You need to be in a voice channel first!")
            return False

        channel = ctx.author.voice.channel
        try:
            await channel.connect(timeout=VOICE_TIMEOUT, reconnect=True)
            last_join_channels[ctx.guild.id] = channel
            return True
        except Exception as e:
            bot_logger.error(f"Voice connection failed: {str(e)}")
            await ctx.send("ERROR Failed to connect to voice channel")
            return False

    @commands.command(name='playnext', aliases=['pn', 'playsnext'])
    async def playnext(self, ctx: commands.Context, *, args: str):
        """Add a song to the front of the queue.
        Usage:
          !playnext <queue_number>   - move that song to next
          !playnext <youtube link>   - download and add as next
          !playnext <local_file>     - add local file as next
        """
        if not await self.ensure_voice(ctx):
            return

        state = get_guild_state(ctx.guild.id)
        args = args.strip()

        # --- Move an existing queue item to the front ---
        if args.isdigit():
            try:
                index = int(args)
            except ValueError:
                await ctx.send("ERROR Invalid queue number.")
                return

            async with state.lock:
                if index < 1 or index > len(state.queue_list):
                    await ctx.send(f"ERROR Queue only has {len(state.queue_list)} songs.")
                    return

                song = state.queue_list.pop(index - 1)
                state.queue_list.insert(0, song)

                # Rebuild the internal asyncio.Queue to match the new order
                state.queue._queue.clear()
                for item in state.queue_list:
                    state.queue._queue.append(item)

            await ctx.send(f"Moved **{song['title']}** to next in queue.")

        # --- Download a YouTube / direct URL and add to front ---
        elif args.startswith(('http://', 'https://')):
            msg = await ctx.send("Downloading...")
            song = await downloader.download_single(args)
            if not song:
                await msg.edit(content="ERROR Failed to download track")
                return

            song['requester'] = ctx.author.display_name

            async with state.lock:
                state.queue_list.insert(0, song)
                state.queue._queue.appendleft(song)

            await msg.edit(content=f"OK Added next: **{song['title']}**")

        # --- Local file ---
        else:
            filepath = args
            if not os.path.exists(filepath):
                await ctx.send(f"ERROR File not found: {filepath}")
                return

            song = {
                'title': os.path.basename(filepath),
                'url': filepath,
                'requester': ctx.author.display_name,
                'duration': 0,
            }

            async with state.lock:
                state.queue_list.insert(0, song)
                state.queue._queue.appendleft(song)

            await ctx.send(f"OK Added next: **{song['title']}**")

        # If the bot wasn't already playing, start the playback loop
        if not state.is_playing:
            await state.start_playback_loop(ctx)


    @commands.command(name='join', aliases=['getinherelittleboy'])
    async def join(self, ctx: commands.Context):
        """Join the user's voice channel."""
        if not await self.ensure_voice(ctx):
            return
        await ctx.send(f"OK Joined {ctx.author.voice.channel.name}")

    @commands.command(name='leave')
    async def leave(self, ctx: commands.Context):
        """Leave voice channel and clear queue."""
        state = get_guild_state(ctx.guild.id)
        await state.stop_playback_loop()

        if ctx.voice_client:
            await ctx.voice_client.disconnect()

        async with state.lock:
            state.queue = asyncio.Queue()
            state.queue_list.clear()
            state.current_song = None
            state.loop_type = None
            state.history.clear()
            state.is_playing = False
            state.playback_active = False

        await ctx.send("OK Left voice channel and cleared queue")

    @commands.command(name='stream')
    async def stream(self, ctx: commands.Context, *, query: str):
        """Stream audio from URL or search YouTube."""
        if not await self.ensure_voice(ctx):
            return

        state = get_guild_state(ctx.guild.id)

        # Handle URLs directly
        if query.startswith(('http://', 'https://')):
            if 'list=' in query or 'playlist' in query:
                await self._handle_playlist(ctx, query)
            else:
                await self._handle_single_url(ctx, query)
            return

        # Search YouTube
        try:
            info = await downloader.extract_info(f"ytsearch5:{query}", download=False)
            entries = info.get('entries', [])[:5]
            if not entries:
                await ctx.send("ERROR No results found.")
                return

            # Create selection view
            view = SearchView(entries, ctx)
            lines = [f"**Search Results for '{query}':**"]
            for idx, entry in enumerate(entries, 1):
                title = entry.get('title', 'Unknown')[:45]
                duration = entry.get('duration', 0) or 0
                mins, secs = divmod(int(duration), 60)
                lines.append(f"{idx}. {title} ({mins}:{secs:02d})")

            msg = await ctx.send("\n".join(lines), view=view)
            view.message = msg

            await view.wait()
            if view.selected_entry is None:
                await msg.edit(content="Selection timed out.", view=None)
                return

            selected_url = view.selected_entry.get('webpage_url') or f"https://youtu.be/{view.selected_entry['id']}"
            await self._handle_single_url(ctx, selected_url)
        except Exception as e:
            bot_logger.error(f"Search error: {traceback.format_exc()}")
            await ctx.send("ERROR Search failed")

    async def _handle_single_url(self, ctx: commands.Context, url: str):
        """Process a single URL."""
        state = get_guild_state(ctx.guild.id)
        msg = await ctx.send("Downloading...")

        song = await downloader.download_single(url)
        if not song:
            await msg.edit(content="ERROR Failed to download track")
            return

        song['requester'] = ctx.author.display_name

        async with state.lock:
            await state.queue.put(song)
            state.queue_list.append(song)

        await msg.edit(content=f"OK Added: **{song['title']}**")

        if not state.is_playing:
            await state.start_playback_loop(ctx)

    async def _handle_playlist(self, ctx: commands.Context, url: str):
        """Process a YouTube playlist."""
        state = get_guild_state(ctx.guild.id)
        status_msg = await ctx.send("Analyzing playlist...")

        try:
            info = await downloader.extract_info(url, download=False, process=False)
            entries = [e for e in info.get('entries', []) if e]
            total = len(entries)
            if total == 0:
                await status_msg.edit(content="ERROR No valid tracks in playlist")
                return

            playlist_title = info.get('title', 'Playlist')
            await status_msg.edit(content=f"Adding **{total}** tracks from: {playlist_title}")

            # Add placeholder entries to queue_list only (display purposes)
            async with state.lock:
                for entry in entries:
                    placeholder = {
                        'title': entry.get('title', 'Unknown'),
                        'url': entry.get('webpage_url') or f"https://youtu.be/{entry['id']}",
                        'requester': ctx.author.display_name,
                        'duration': entry.get('duration', 0),
                        'status': 'pending'
                    }
                    state.queue_list.append(placeholder)

            # Download concurrently with progress
            completed = 0
            progress_msg = await ctx.send(f"Downloading 0/{total}...")

            async def progress_callback(song):
                nonlocal completed
                completed += 1
                await progress_msg.edit(content=f"Downloading {completed}/{total}...")

            downloaded = await downloader.download_playlist_batch(
                entries,
                ctx.author.display_name,
                progress_callback=progress_callback
            )

            # Replace placeholders with actual downloaded songs
            async with state.lock:
                # Remove all placeholders
                state.queue_list = [s for s in state.queue_list if s.get('status') != 'pending']
                for song in downloaded:
                    await state.queue.put(song)
                    state.queue_list.append(song)

            if downloaded:
                await progress_msg.edit(content=f"OK Added **{len(downloaded)}** tracks from playlist **{playlist_title}**")
            else:
                await progress_msg.edit(content=f"ERROR Failed to download any tracks from the playlist")

            if not state.is_playing and downloaded:
                await state.start_playback_loop(ctx)

        except Exception as e:
            bot_logger.error(f"Playlist error: {traceback.format_exc()}")
            await ctx.send("ERROR Failed to process playlist")

    @commands.command(name='queue')
    async def queue(self, ctx: commands.Context):
        """Show current queue."""
        state = get_guild_state(ctx.guild.id)
        if not state.current_song and not state.queue_list:
            await ctx.send("Queue is empty")
            return

        messages = []
        current_message = []

        # Now playing
        if state.current_song:
            elapsed = int(time.time() - state.start_time)
            elapsed_str = f"{elapsed//60}:{elapsed%60:02d}"
            dur = int(state.current_song.get('duration', 0))
            dur_str = f"{dur//60}:{dur%60:02d}" if dur else "??:??"
            current_message.append(f"**Now Playing:** {state.current_song['title']}")
            current_message.append(f"`{elapsed_str}/{dur_str}` | Requested by {state.current_song['requester']}")

        # Upcoming queue
        if state.queue_list:
            if current_message:
                current_message.append("\n**Upcoming:**")
            else:
                current_message.append("**Upcoming:**")

            for idx, song in enumerate(state.queue_list, 1):
                dur = int(song.get('duration', 0))
                dur_str = f"{dur//60}:{dur%60:02d}" if dur else "??:??"
                line = f"{idx}. {song['title']} ({dur_str}) | {song['requester']}"

                if len('\n'.join(current_message + [line])) > 1900:
                    messages.append('\n'.join(current_message))
                    current_message = ["**Upcoming (cont'd):**", line]
                else:
                    current_message.append(line)

        if current_message:
            messages.append('\n'.join(current_message))

        for msg in messages:
            await ctx.send(msg)

    @commands.command(name='remove')
    async def remove(self, ctx: commands.Context, index: int):
        """Remove a song from the queue by its number (!remove <song_num>)."""
        state = get_guild_state(ctx.guild.id)

        async with state.lock:
            if index < 1 or index > len(state.queue_list):
                await ctx.send(f"ERROR Invalid index. Queue has {len(state.queue_list)} songs.")
                return

            removed = state.queue_list.pop(index - 1)
            # Mark as removed so the playback loop can skip it when it reaches the front
            removed['removed'] = True

        await ctx.send(f"OK Removed: **{removed['title']}**")

    @commands.command(name='clear')
    async def clear(self, ctx: commands.Context):
        """Clear the queue."""
        state = get_guild_state(ctx.guild.id)
        size = state.queue.qsize()
        while not state.queue.empty():
            try:
                await state.queue.get()
            except:
                pass
        async with state.lock:
            state.queue_list.clear()
        await ctx.send(f"OK Cleared {size} songs from queue")

    @commands.command(name='skip')
    async def skip(self, ctx: commands.Context):
        """Skip current track."""
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("Skipped")
        else:
            await ctx.send("Nothing playing")

    @commands.command(name='pause')
    async def pause(self, ctx: commands.Context):
        """Pause playback."""
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("Paused")
        else:
            await ctx.send("Nothing playing")

    @commands.command(name='resume')
    async def resume(self, ctx: commands.Context):
        """Resume playback."""
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("Resumed")
        else:
            await ctx.send("Nothing paused")

    @commands.command(name='stop')
    async def stop(self, ctx: commands.Context):
        """Stop playback and clear queue."""
        state = get_guild_state(ctx.guild.id)
        if ctx.voice_client:
            ctx.voice_client.stop()
        async with state.lock:
            state.queue = asyncio.Queue()
            state.queue_list.clear()
            state.current_song = None
            state.loop_type = None
            state.history.clear()
            state.is_playing = False
            state.playback_active = False
        await ctx.send("Stopped")

    @commands.command(name='shuffle')
    async def shuffle(self, ctx: commands.Context):
        """Shuffle the queue."""
        state = get_guild_state(ctx.guild.id)
        async with state.lock:
            if state.queue.qsize() < 2:
                await ctx.send("Need at least 2 songs to shuffle")
                return

            items = []
            while not state.queue.empty():
                items.append(await state.queue.get())

            random.shuffle(items)
            state.queue_list = items.copy()
            for item in items:
                await state.queue.put(item)

        await ctx.send("Queue shuffled")

    @commands.command(name='loop')
    async def loop(self, ctx: commands.Context):
        """Toggle loop mode."""
        state = get_guild_state(ctx.guild.id)
        if state.loop_type is None:
            state.loop_type = 'queue'
            await ctx.send("Looping queue")
        elif state.loop_type == 'queue':
            state.loop_type = 'song'
            await ctx.send("Looping current song")
        else:
            state.loop_type = None
            await ctx.send("Looping disabled")

    @commands.command(name='playlist_local')
    async def playlist_local(self, ctx: commands.Context, filename: str):
        """Load local playlist file."""
        state = get_guild_state(ctx.guild.id)
        filepath = os.path.join(os.getcwd(), filename)

        if not os.path.exists(filepath):
            await ctx.send(f"File not found: {filename}")
            return

        try:
            with open(filepath, 'r') as f:
                lines = [line.strip() for line in f if line.strip()]

            added = 0
            async with state.lock:
                for line in lines:
                    if os.path.exists(line):
                        song = {
                            'title': os.path.basename(line),
                            'url': line,
                            'requester': ctx.author.display_name,
                            'duration': 0
                        }
                        await state.queue.put(song)
                        state.queue_list.append(song)
                        added += 1
                    else:
                        await ctx.send(f"Warning: File not found: {line}")

            await ctx.send(f"OK Added {added} local files to queue")
            if not state.is_playing and added > 0:
                await state.start_playback_loop(ctx)
        except Exception as e:
            await ctx.send(f"ERROR: {str(e)}")

    @commands.command(name='usage')
    async def usage(self, ctx: commands.Context):
        """Show data usage."""
        data = DATA_USAGE[ctx.guild.id]
        mb = data['total_bytes'] / 1024 / 1024
        uptime = time.time() - data['start_time']
        hours, rem = divmod(uptime, 3600)
        minutes, _ = divmod(rem, 60)
        await ctx.send(f"**Data Usage:** {mb:.2f} MB\n**Uptime:** {int(hours)}h {int(minutes)}m")

    @commands.command(name='help')
    async def help_cmd(self, ctx: commands.Context):
        """Show help."""
        help_text = (
            "**Folda Tunez Commands**\n"
            f"`{BOT_PREFIX}join` - Join voice channel\n"
            f"`{BOT_PREFIX}leave` - Leave and clear queue\n"
            f"`{BOT_PREFIX}stream <url/search>` - Play from YouTube or search\n"
            f"`{BOT_PREFIX}queue` - Show queue\n"
            f"`{BOT_PREFIX}remove <number>` - Remove song from queue by number\n"
            f"`{BOT_PREFIX}clear` - Clear queue\n"
            f"`{BOT_PREFIX}playnext <number|url|file>` - Add a song to the front of the queue\n"
            f"`{BOT_PREFIX}skip` - Skip current track\n"
            f"`{BOT_PREFIX}pause` / `resume` - Pause/Resume\n"
            f"`{BOT_PREFIX}stop` - Stop and clear\n"
            f"`{BOT_PREFIX}shuffle` - Shuffle queue\n"
            f"`{BOT_PREFIX}loop` - Toggle loop mode\n"
            f"`{BOT_PREFIX}playlist_local <file>` - Load local playlist\n"
            f"`{BOT_PREFIX}usage` - Show data usage\n"
            f"`{BOT_PREFIX}help` - This message\n"
        )
        await ctx.send(help_text)

# ==================== Search View ====================
class SearchView(View):
    def __init__(self, entries, ctx):
        super().__init__(timeout=30)
        self.entries = entries
        self.ctx = ctx
        self.selected_entry = None
        self.message = None

        for idx in range(min(5, len(entries))):
            button = Button(style=discord.ButtonStyle.primary, label=str(idx+1), custom_id=str(idx))
            button.callback = self.make_callback(idx)
            self.add_item(button)

    def make_callback(self, idx):
        async def callback(interaction: discord.Interaction):
            if interaction.user != self.ctx.author:
                await interaction.response.send_message("ERROR You didn't start this search!", ephemeral=True)
                return
            self.selected_entry = self.entries[idx]
            await interaction.response.defer()
            self.stop()
        return callback

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            await self.message.edit(view=self)

# ==================== Admin CLI (with robust input) ====================
class AdminCLI:
    """CLI for remote administration."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.running = True
        self.guild_ids = {}
        self.channel_ids = {}
        self.next_guild_id = 1
        self.next_channel_id = 1

    def safe_input(self, prompt: str) -> str:
        """Read input with encoding error handling."""
        try:
            return input(prompt)
        except UnicodeDecodeError:
            # If input contains invalid UTF-8, try reading raw bytes and decode with replace
            try:
                raw = sys.stdin.buffer.readline()
                return raw.decode('utf-8', errors='replace').rstrip('\n')
            except:
                return ""

    async def run_async(self):
        """Main CLI loop."""
        while self.running:
            try:
                # Use safe_input in executor to avoid blocking
                cmd = await asyncio.get_event_loop().run_in_executor(
                    None, self.safe_input, "\nFoldaTunez> "
                )
                if not cmd:
                    continue
                await self.process_command(cmd.strip())
            except EOFError:
                break
            except Exception as e:
                cli_logger.error(f"CLI error: {traceback.format_exc()}")
                print(f"Error: {str(e)}")

    async def process_command(self, cmd_line: str):
        parts = cmd_line.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        handlers = {
            'servers': self.cmd_servers,
            'channels': self.cmd_channels,
            'sendmsg': self.cmd_sendmsg,
            'join': self.cmd_join,
            'stream': self.cmd_stream,
            'clear': self.cmd_clear,
            'leave': self.cmd_leave,
            'pause': self.cmd_pause,
            'resume': self.cmd_resume,
            'queue': self.cmd_queue,
            'shuffle': self.cmd_shuffle,
            'loop': self.cmd_loop,
            'playlist_local': self.cmd_playlist_local,
            'usage': self.cmd_usage,
            'kill': self.cmd_kill,
            'exit': self.cmd_exit,
        }

        if cmd in handlers:
            await handlers[cmd](args)
        else:
            print(f"Unknown command: {cmd}")

    def _get_guild(self, bot_id: str) -> Optional[discord.Guild]:
        try:
            gid = self.guild_ids.get(int(bot_id))
            return self.bot.get_guild(gid) if gid else None
        except:
            return None

    def _get_channel(self, guild: discord.Guild, bot_id: str) -> Optional[discord.abc.GuildChannel]:
        try:
            cid = self.channel_ids.get(int(bot_id))
            return guild.get_channel(cid) if cid else None
        except:
            return None

    async def cmd_servers(self, args):
        for guild in self.bot.guilds:
            if guild.id not in self.guild_ids.values():
                self.guild_ids[self.next_guild_id] = guild.id
                self.next_guild_id += 1
            bot_id = next(k for k, v in self.guild_ids.items() if v == guild.id)
            state = get_guild_state(guild.id)
            vc_status = "Connected" if guild.voice_client else "Disconnected"
            playback = "Playing" if state.is_playing else "Idle"
            current = state.current_song['title'][:20] + '...' if state.current_song else 'None'
            print(f"{guild.name} | BOT ID: {bot_id} | {vc_status} | {playback} | {current} | Queue: {state.queue.qsize()}")

    async def cmd_channels(self, args):
        guild = self._get_guild(args)
        if not guild:
            print("Invalid guild ID")
            return
        for channel in guild.channels:
            if channel.id not in self.channel_ids.values():
                self.channel_ids[self.next_channel_id] = channel.id
                self.next_channel_id += 1
            bot_id = next(k for k, v in self.channel_ids.items() if v == channel.id)
            print(f"{channel.name} | BOT ID: {bot_id} | {type(channel).__name__}")

    async def cmd_sendmsg(self, args):
        parts = args.split(maxsplit=2)
        if len(parts) < 3:
            print("Usage: sendmsg <guild_bot_id> <channel_bot_id> <message>")
            return
        guild = self._get_guild(parts[0])
        if not guild:
            print("Invalid guild ID")
            return
        channel = self._get_channel(guild, parts[1])
        if not channel or not isinstance(channel, discord.TextChannel):
            print("Invalid channel")
            return
        await channel.send(parts[2])
        print("Message sent")

    async def cmd_join(self, args):
        parts = args.split()
        if len(parts) < 2:
            print("Usage: join <guild_bot_id> <channel_bot_id>")
            return
        guild = self._get_guild(parts[0])
        if not guild:
            print("Invalid guild ID")
            return
        channel = self._get_channel(guild, parts[1])
        if not channel or not isinstance(channel, discord.VoiceChannel):
            print("Invalid voice channel")
            return
        if guild.voice_client:
            await guild.voice_client.move_to(channel)
        else:
            await channel.connect()
        print(f"Joined {channel.name}")

    async def cmd_stream(self, args):
        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            print("Usage: stream <guild_bot_id> <url>")
            return
        guild = self._get_guild(parts[0])
        if not guild:
            print("Invalid guild ID")
            return
        ctx = MockContext(guild)
        await self.bot.get_command('stream').callback(ctx, query=parts[1])

    async def cmd_clear(self, args):
        guild = self._get_guild(args)
        if not guild:
            print("Invalid guild ID")
            return
        ctx = MockContext(guild)
        await self.bot.get_command('clear').callback(ctx)

    async def cmd_leave(self, args):
        guild = self._get_guild(args)
        if not guild:
            print("Invalid guild ID")
            return
        ctx = MockContext(guild)
        await self.bot.get_command('leave').callback(ctx)

    async def cmd_pause(self, args):
        guild = self._get_guild(args)
        if not guild:
            print("Invalid guild ID")
            return
        ctx = MockContext(guild)
        await self.bot.get_command('pause').callback(ctx)

    async def cmd_resume(self, args):
        guild = self._get_guild(args)
        if not guild:
            print("Invalid guild ID")
            return
        ctx = MockContext(guild)
        await self.bot.get_command('resume').callback(ctx)

    async def cmd_queue(self, args):
        parts = args.split()
        if len(parts) < 2:
            print("Usage: queue <guild_bot_id> <channel_bot_id>")
            return
        guild = self._get_guild(parts[0])
        if not guild:
            print("Invalid guild ID")
            return
        channel = self._get_channel(guild, parts[1])
        if not channel or not isinstance(channel, discord.TextChannel):
            print("Invalid text channel")
            return
        ctx = MockContext(guild, channel)
        await self.bot.get_command('queue').callback(ctx)

    async def cmd_shuffle(self, args):
        guild = self._get_guild(args)
        if not guild:
            print("Invalid guild ID")
            return
        ctx = MockContext(guild)
        await self.bot.get_command('shuffle').callback(ctx)

    async def cmd_loop(self, args):
        guild = self._get_guild(args)
        if not guild:
            print("Invalid guild ID")
            return
        ctx = MockContext(guild)
        await self.bot.get_command('loop').callback(ctx)

    async def cmd_playlist_local(self, args):
        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            print("Usage: playlist_local <guild_bot_id> <filename>")
            return
        guild = self._get_guild(parts[0])
        if not guild:
            print("Invalid guild ID")
            return
        ctx = MockContext(guild)
        await self.bot.get_command('playlist_local').callback(ctx, filename=parts[1])

    async def cmd_usage(self, args):
        guild = self._get_guild(args)
        if not guild:
            print("Invalid guild ID")
            return
        ctx = MockContext(guild)
        await self.bot.get_command('usage').callback(ctx)

    async def cmd_kill(self, args):
        print("Shutting down bot...")
        await self.bot.close()
        self.running = False

    async def cmd_exit(self, args):
        self.running = False
        print("Exiting CLI. Bot continues running.")

# ==================== Bot Setup ====================
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents, case_insensitive=True)

@bot.event
async def on_ready():
    bot_logger.info(f"Logged in as {bot.user}")
    print(f"Folda Tunez v0.5.1 - Logged in as {bot.user}")

    # Remove default help command to avoid conflict
    bot.remove_command('help')

    # Add music cog
    await bot.add_cog(Music(bot))

    # Start CLI in background task
    cli = AdminCLI(bot)
    bot.loop.create_task(cli.run_async())

    # Verify FFmpeg
    import subprocess
    try:
        subprocess.run([FFMPEG_PATH, '-version'], capture_output=True, check=True)
    except:
        bot_logger.critical("FFmpeg not found!")
        await bot.close()

@bot.event
async def on_voice_state_update(member, before, after):
    if member != bot.user:
        return
    guild_id = member.guild.id
    state = guild_states.get(guild_id)
    if before.channel and not after.channel:
        if state:
            await state.stop_playback_loop()
        if member.guild.voice_client:
            await member.guild.voice_client.disconnect(force=True)

if __name__ == "__main__":
    bot.run('YOUR_TOKEN_HERE')
