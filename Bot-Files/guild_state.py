"""Per-guild playback state, playback loop, and shutdown cleanup."""
import asyncio
import os
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

import discord
from discord.ext import commands

from audio import TrackedFFmpegPCMAudio
from config import MAX_CONCURRENT_DL, SUPPORTED_AUDIO_EXTENSIONS, VOICE_TIMEOUT
from helpers import delete_song_file
from loggers import bot_logger
from runtime import ALL_DOWNLOADED_FILES, last_join_channels, vote_skips


def rebuild_queue(state: 'GuildState') -> None:
    """Re-sync the underlying asyncio.Queue from queue_list (must hold state.lock)."""
    state.queue._queue.clear()
    for item in state.queue_list:
        state.queue._queue.append(item)


@dataclass
class GuildState:
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
    download_semaphore: asyncio.Semaphore = field(
        default_factory=lambda: asyncio.Semaphore(MAX_CONCURRENT_DL)
    )
    start_time: float = 0.0
    last_activity: float = field(default_factory=time.time)
    data_usage: int = 0
    audio_filter: Optional[str] = None
    downloaded_files: Set[str] = field(default_factory=set)

    async def start_playback_loop(self, ctx: commands.Context) -> None:
        if self.playback_task and not self.playback_task.done():
            return
        self.playback_task = asyncio.create_task(self._playback_loop(ctx))
        bot_logger.info(f"Started playback loop for guild {self.guild_id}")

    async def stop_playback_loop(self) -> None:
        if self.playback_task and not self.playback_task.done():
            self.playback_task.cancel()
            try:
                await self.playback_task
            except asyncio.CancelledError:
                pass
        self.is_playing = False
        self.playback_active = False
        bot_logger.info(f"Stopped playback loop for guild {self.guild_id}")

    async def cleanup_downloads(self) -> int:
        """Delete every auto-downloaded file tracked for this guild."""
        count = 0
        for path in list(self.downloaded_files):
            try:
                if os.path.exists(path):
                    os.remove(path)
                    count += 1
            except Exception as e:
                bot_logger.error(f"Failed to delete {path}: {e}")
            ALL_DOWNLOADED_FILES.discard(path)
        self.downloaded_files.clear()
        # Also sweep queue_list / history for anything we missed
        for song in list(self.queue_list) + list(self.history) + ([self.current_song] if self.current_song else []):
            if song and song.get('source') == 'download':
                delete_song_file(song)
        return count

    async def _playback_loop(self, ctx: commands.Context) -> None:
        while True:
            try:
                if not self.playback_active and not self.is_playing:
                    await self._play_next_safe(ctx)
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception:
                bot_logger.error(f"Playback loop error in guild {self.guild_id}: {traceback.format_exc()}")
                await asyncio.sleep(5)

    async def _safe_send(self, ctx: commands.Context, content: str, **kwargs):
        try:
            return await ctx.send(content, **kwargs)
        except Exception as e:
            bot_logger.warning(f"Safe send failed in guild {self.guild_id}: {e}")
            return None

    async def _play_next_safe(self, ctx: commands.Context) -> None:
        """Thread-safe next-song playback with proper state management."""
        try:
            # Atomic check-and-set (no awaits between)
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
                        bot_logger.info(f"Reconnected to voice in guild {self.guild_id}")
                    except Exception as e:
                        bot_logger.error(f"Voice reconnect failed: {e}")
                        self.is_playing = False
                        self.playback_active = False
                        return
                else:
                    self.is_playing = False
                    self.playback_active = False
                    return

            # Get next song
            song = None
            if self.loop_type == 'song' and self.current_song:
                song = self.current_song
            else:
                while not song:
                    if self.queue.empty():
                        if self.loop_type == 'queue' and self.history:
                            for track in self.history:
                                await self.queue.put(track)
                                async with self.lock:
                                    self.queue_list.append(track)
                            continue
                        break
                    candidate = await self.queue.get()
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
            vote_skips[self.guild_id].clear()
            self.start_time = time.time()
            self.is_playing = True
            self.last_activity = time.time()

            # Verify file
            filepath = song['url']
            if not os.path.exists(filepath):
                bot_logger.error(f"File missing: {filepath}")
                await self._safe_send(ctx, f"File missing: {song['title']}")
                base = os.path.splitext(filepath)[0]
                for ext in SUPPORTED_AUDIO_EXTENSIONS:
                    test = base + ext
                    if os.path.exists(test):
                        song['url'] = test
                        break
                else:
                    self.playback_active = False
                    asyncio.create_task(self._play_next_safe(ctx))
                    return

            try:
                if os.path.getsize(song['url']) == 0:
                    raise ValueError("empty file")
            except Exception as e:
                bot_logger.error(f"File access error {song['url']}: {e}")
                await self._safe_send(ctx, f"Cannot read file: {song['title']}")
                self.playback_active = False
                asyncio.create_task(self._play_next_safe(ctx))
                return

            # Create audio source (with active filter)
            try:
                source = TrackedFFmpegPCMAudio(
                    song['url'], guild_id=self.guild_id, filter_name=self.audio_filter
                )
            except Exception as e:
                bot_logger.error(f"Audio source failed {song['url']}: {e}")
                await self._safe_send(ctx, f"Audio format error: {song['title']}")
                self.playback_active = False
                asyncio.create_task(self._play_next_safe(ctx))
                return

            # Capture loop before entering callback (callback runs on ffmpeg thread)
            loop = asyncio.get_running_loop()

            def after_playback(error):
                self.playback_active = False
                self.is_playing = False
                if error:
                    bot_logger.error(f"Playback error in guild {self.guild_id}: {error}")
                asyncio.run_coroutine_threadsafe(self._play_next_safe(ctx), loop)

            try:
                ctx.voice_client.play(source, after=after_playback)
                await self._safe_send(ctx, f"Now Playing: **{song['title']}**")
            except discord.ClientException as e:
                if "Already playing audio" in str(e):
                    bot_logger.warning(f"Playback race in guild {self.guild_id}, retrying")
                    self.playback_active = False
                    await asyncio.sleep(1)
                    asyncio.create_task(self._play_next_safe(ctx))
                else:
                    raise
        except Exception:
            self.playback_active = False
            bot_logger.error(f"Playback error in guild {self.guild_id}: {traceback.format_exc()}")
            await self._safe_send(ctx, "Playback error occurred")


guild_states: Dict[int, GuildState] = {}


def get_guild_state(guild_id: int) -> GuildState:
    if guild_id not in guild_states:
        guild_states[guild_id] = GuildState(guild_id)
    return guild_states[guild_id]


async def cleanup_all_downloads():
    """Delete every auto-downloaded file tracked across all guilds."""
    n = 0
    for path in list(ALL_DOWNLOADED_FILES):
        try:
            if os.path.exists(path):
                os.remove(path)
                n += 1
        except Exception as e:
            bot_logger.error(f"Cleanup failed for {path}: {e}")
    ALL_DOWNLOADED_FILES.clear()
    for state in guild_states.values():
        state.downloaded_files.clear()
    bot_logger.info(f"Deleted {n} tracked files on shutdown")