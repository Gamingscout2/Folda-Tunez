"""Per-guild playback state with a single source of truth.

The queue is a plain list (queue_list) plus a current_index pointer.
The pointer is:
    -1                -> nothing playing, next advance starts at index 0
    >= 0 and < len    -> currently playing (or last-played) song's position

Loop semantics:
    'song'  -> replay the same index
    'queue' -> advance; wrap to 0 when past the end
    None    -> advance; stop when past the end
"""

import asyncio
import os
import random
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


@dataclass
class GuildState:
    guild_id: int
    queue_list: List[Dict[str, Any]] = field(default_factory=list)
    current_index: int = -1
    current_song: Optional[Dict[str, Any]] = None
    loop_type: Optional[str] = None            # None / 'queue' / 'song'
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
    _pending_play_index: Optional[int] = None
    _force_advance: bool = False

    # ---------- loop / lifecycle ----------
    async def start_playback_loop(self, ctx):
        if self.playback_task and not self.playback_task.done():
            return
        self.playback_task = asyncio.create_task(self._playback_loop(ctx))
        bot_logger.info(f"Started playback loop for guild {self.guild_id}")

    async def stop_playback_loop(self):
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
        for song in list(self.queue_list) + ([self.current_song] if self.current_song else []):
            if song and song.get('source') == 'download':
                delete_song_file(song)
        return count

    async def _playback_loop(self, ctx):
        while True:
            try:
                if not self.playback_active and not self.is_playing:
                    await self._play_next_safe(ctx)
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception:
                bot_logger.error(
                    f"Playback loop error in guild {self.guild_id}: {traceback.format_exc()}"
                )
                await asyncio.sleep(5)

    async def _safe_send(self, ctx, content, **kwargs):
        try:
            return await ctx.send(content, **kwargs)
        except Exception as e:
            bot_logger.warning(f"Safe send failed in guild {self.guild_id}: {e}")
            return None

    async def _play_next_safe(self, ctx):
        try:
            if self.playback_active or (ctx.voice_client and ctx.voice_client.is_playing()):
                return
            self.playback_active = True

            # Ensure voice
            vc = ctx.guild.voice_client
            if vc and not vc.is_connected():
                # give an in-flight library reconnect a few seconds before
                # tearing it down, otherwise channel.connect() raises "Already connected"
                for _ in range(10):
                    await asyncio.sleep(1)
                    if vc.is_connected():
                        break
                else:
                    bot_logger.warning(
                        f"Voice client in guild {self.guild_id} stuck disconnected, resetting"
                    )
                    try:
                        await vc.disconnect(force=True)
                    except Exception as e:
                        bot_logger.error(f"Voice client reset failed: {e}")
            if not ctx.guild.voice_client or not ctx.guild.voice_client.is_connected():
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

            # Determine target index
            if self._pending_play_index is not None:
                target_index = self._pending_play_index
                self._pending_play_index = None
            elif self._force_advance:
                target_index = self.current_index + 1
                self._force_advance = False
            elif self.loop_type == 'song' and self.current_index >= 0 and self.current_song:
                target_index = self.current_index
            else:
                target_index = self.current_index + 1

            # End-of-queue handling
            if target_index >= len(self.queue_list):
                if self.loop_type == 'queue' and self.queue_list:
                    target_index = 0
                else:
                    self.is_playing = False
                    self.playback_active = False
                    return
            if target_index < 0:
                self.is_playing = False
                self.playback_active = False
                return

            song = self.queue_list[target_index]
            self.current_index = target_index
            self.current_song = song
            vote_skips[self.guild_id].clear()
            self.start_time = time.time()
            self.is_playing = True
            self.last_activity = time.time()

            # Verify file exists / is readable
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

            loop = asyncio.get_running_loop()

            def after_playback(error):
                self.playback_active = False
                self.is_playing = False
                if error:
                    bot_logger.error(f"Playback error in guild {self.guild_id}: {error}")
                asyncio.run_coroutine_threadsafe(self._play_next_safe(ctx), loop)

            try:
                ctx.guild.voice_client.play(source, after=after_playback)
                bot_logger.info(
                    f"Playing '{song['title']}' in guild {self.guild_id} "
                    f"(filter={self.audio_filter}, ffmpeg src={os.path.basename(song['url'])})"
                )
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

    # ---------- queue manipulation ----------
    async def add_song(self, song: Dict[str, Any]):
        self.queue_list.append(song)

    async def insert_next(self, song: Dict[str, Any]):
        """Insert a song right after current position (or at 0 if stopped)."""
        insert_at = (self.current_index + 1) if self.current_index >= 0 else 0
        if insert_at > len(self.queue_list):
            insert_at = len(self.queue_list)
        self.queue_list.insert(insert_at, song)

    async def remove_at(self, ctx, n: int) -> Optional[Dict[str, Any]]:
        if not (0 <= n < len(self.queue_list)):
            return None
        current_song = self.current_song
        removed = self.queue_list.pop(n)
        was_active = bool(
            ctx.voice_client
            and (ctx.voice_client.is_playing() or ctx.voice_client.is_paused())
        )

        if removed is current_song:
            if n < len(self.queue_list):
                # There is a next song now occupying position n
                self.current_song = self.queue_list[n]
                self.current_index = n
                if was_active:
                    self._pending_play_index = n
                    ctx.voice_client.stop()
            else:
                # Removed the last song in the queue
                self.current_song = None
                self.current_index = len(self.queue_list) - 1
                if was_active:
                    ctx.voice_client.stop()
                self.is_playing = False
        else:
            if current_song is not None and current_song in self.queue_list:
                self.current_index = self.queue_list.index(current_song)
        return removed

    async def move(self, src: int, dst: int) -> Optional[Dict[str, Any]]:
        if not (0 <= src < len(self.queue_list) and 0 <= dst < len(self.queue_list)):
            return None
        if src == dst:
            return self.queue_list[src]
        current_song = self.current_song
        song = self.queue_list.pop(src)
        self.queue_list.insert(dst, song)
        if current_song is not None and current_song in self.queue_list:
            self.current_index = self.queue_list.index(current_song)
        return song

    async def swap(self, a: int, b: int):
        if not (0 <= a < len(self.queue_list) and 0 <= b < len(self.queue_list)):
            return None
        current_song = self.current_song
        self.queue_list[a], self.queue_list[b] = self.queue_list[b], self.queue_list[a]
        if current_song is not None and current_song in self.queue_list:
            self.current_index = self.queue_list.index(current_song)
        return (self.queue_list[a], self.queue_list[b])

    async def shuffle(self):
        current_song = self.current_song
        random.shuffle(self.queue_list)
        if current_song is not None and current_song in self.queue_list:
            self.current_index = self.queue_list.index(current_song)
        else:
            self.current_index = -1

    async def jump_to(self, ctx, n: int) -> bool:
        if not (0 <= n < len(self.queue_list)):
            return False
        if ctx.voice_client and ctx.voice_client.is_playing():
            self._pending_play_index = n
            ctx.voice_client.stop()
        else:
            self.current_index = n - 1
            self.playback_active = False
            await self.start_playback_loop(ctx)
        return True


guild_states: Dict[int, GuildState] = {}


def get_guild_state(guild_id: int) -> GuildState:
    if guild_id not in guild_states:
        guild_states[guild_id] = GuildState(guild_id)
    return guild_states[guild_id]


async def cleanup_all_downloads():
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