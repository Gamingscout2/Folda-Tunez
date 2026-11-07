"""The Music cog: playback, queue, playlists, filters."""

import asyncio
import os
import time
import traceback
from typing import List

import discord
from discord.ext import commands

import playlists as playlist_mod
from audio import SONG_FILTERS
from config import BOT_PREFIX, MAX_PLAYLIST_ITEMS
from downloader import downloader, search_youtube
from guild_state import cleanup_all_downloads, get_guild_state
from helpers import is_admin, is_dj
from loggers import bot_logger
from runtime import DATA_USAGE, guild_dj_roles, last_join_channels, stay_247, vote_skips
from search_view import SearchView


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- helpers ----------
    async def ensure_voice(self, ctx) -> bool:
        if ctx.voice_client and ctx.voice_client.is_connected():
            return True
        if not getattr(ctx.author, 'voice', None) or not ctx.author.voice:
            await ctx.send("You need to be in a voice channel first!")
            return False
        channel = ctx.author.voice.channel
        try:
            await channel.connect(timeout=60, reconnect=True)
            last_join_channels[ctx.guild.id] = channel
            return True
        except Exception as e:
            bot_logger.error(f"Voice connection failed: {e}")
            await ctx.send("Failed to connect to voice channel")
            return False

    async def _check_dj(self, ctx) -> bool:
        if is_dj(ctx, ctx.guild.id):
            return True
        await ctx.send("You need the DJ role or `Manage Server` permission.")
        return False

    # ---------- playback ----------
    @commands.command(name='join', aliases=['getinherelittleboy'])
    async def join(self, ctx):
        if not await self.ensure_voice(ctx):
            return
        await ctx.send(f"Joined **{ctx.author.voice.channel.name}**")

    @commands.command(name='leave')
    async def leave(self, ctx):
        if not await self._check_dj(ctx):
            return
        state = get_guild_state(ctx.guild.id)
        await state.stop_playback_loop()
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
        deleted = await state.cleanup_downloads()
        state.queue_list.clear()
        state.current_index = -1
        state.current_song = None
        state.loop_type = None
        state.is_playing = False
        state.playback_active = False
        await ctx.send(f"Left voice and cleared queue (deleted **{deleted}** files)")

    @commands.command(name='stream', aliases=['play', 'p'])
    async def stream(self, ctx, *, query: str = ""):
        if not query:
            await ctx.send("Usage: `!stream <url or search>`")
            return
        if not await self.ensure_voice(ctx):
            return
        if query.startswith(('http://', 'https://')):
            if 'list=' in query or 'playlist' in query:
                await self._handle_playlist(ctx, query)
            else:
                await self._handle_single_url(ctx, query)
            return
        entries = await search_youtube(query, limit=5)
        if not entries:
            await ctx.send("No results found.")
            return
        view = SearchView(entries, ctx)
        lines = [f"**Search results for '{query}':**"]
        for idx, entry in enumerate(entries, 1):
            title = (entry.get('title') or 'Unknown')[:60]
            dur = int(entry.get('duration') or 0)
            m, s = divmod(dur, 60)
            lines.append(f"`{idx}.` {title} ({m}:{s:02d})")
        msg = await ctx.send("\n".join(lines), view=view)
        view.message = msg
        await view.wait()
        if view.selected_entry is None:
            try:
                await msg.edit(content="Selection cancelled.", view=None)
            except Exception:
                pass
            return
        url = view.selected_entry.get('webpage_url') or f"https://youtu.be/{view.selected_entry['id']}"
        await self._handle_single_url(ctx, url)

    async def _handle_single_url(self, ctx, url: str):
        state = get_guild_state(ctx.guild.id)
        msg = await ctx.send("Downloading...")
        song = await downloader.download_single(url)
        if not song:
            await msg.edit(content="Failed to download track")
            return
        song['requester'] = ctx.author.display_name
        state.downloaded_files.add(song['url'])
        await state.add_song(song)
        await msg.edit(content=f"Added: **{song['title']}**")
        if not state.is_playing:
            await state.start_playback_loop(ctx)

    async def _handle_playlist(self, ctx, url: str):
        state = get_guild_state(ctx.guild.id)
        status = await ctx.send("Analyzing playlist...")
        try:
            info = await downloader.extract_info(url, download=False, process=False)
            entries = [e for e in (info.get('entries') or []) if e][:MAX_PLAYLIST_ITEMS]
            if not entries:
                await status.edit(content="No valid tracks in playlist")
                return
            total = len(entries)
            title = info.get('title', 'Playlist')
            await status.edit(content=f"Downloading **{total}** tracks from **{title}**...")
            progress_msg = await ctx.send(f"Progress: 0/{total}")
            completed = 0

            async def progress_cb(_song):
                nonlocal completed
                completed += 1
                try:
                    await progress_msg.edit(content=f"Progress: {completed}/{total}")
                except Exception:
                    pass

            downloaded = await downloader.download_playlist_batch(
                entries, ctx.author.display_name, progress_callback=progress_cb, state=state
            )
            for song in downloaded:
                await state.add_song(song)
            if downloaded:
                await progress_msg.edit(content=f"Added **{len(downloaded)}** tracks from **{title}**")
            else:
                await progress_msg.edit(content="Failed to download any tracks")
            if not state.is_playing and downloaded:
                await state.start_playback_loop(ctx)
        except Exception:
            bot_logger.error(f"Playlist error: {traceback.format_exc()}")
            await ctx.send("Failed to process playlist")

    @commands.command(name='playnext', aliases=['pn'])
    async def playnext(self, ctx, *, args: str = ""):
        """!playnext <queue_num|url|local_file>"""
        if not args:
            await ctx.send("Usage: `!playnext <queue_number|url|local_file>`")
            return
        if not await self.ensure_voice(ctx):
            return
        state = get_guild_state(ctx.guild.id)
        args = args.strip()

        if args.isdigit():
            idx = int(args)
            if not (1 <= idx <= len(state.queue_list)):
                await ctx.send(f"Queue only has {len(state.queue_list)} songs.")
                return
            src = idx - 1
            target = state.current_index + 1 if state.current_index >= 0 else 0
            target = min(target, len(state.queue_list) - 1)
            if src == target:
                await ctx.send(f"**{state.queue_list[src]['title']}** is already next.")
                return
            song = await state.move(src, target)
            if song:
                await ctx.send(f"Moved **{song['title']}** to next in queue.")
        elif args.startswith(('http://', 'https://')):
            msg = await ctx.send("Downloading...")
            song = await downloader.download_single(args)
            if not song:
                await msg.edit(content="Failed to download")
                return
            song['requester'] = ctx.author.display_name
            state.downloaded_files.add(song['url'])
            await state.insert_next(song)
            await msg.edit(content=f"Added next: **{song['title']}**")
        else:
            if not os.path.exists(args):
                await ctx.send(f"File not found: `{args}`")
                return
            song = {
                'title': os.path.basename(args),
                'url': os.path.abspath(args),
                'requester': ctx.author.display_name,
                'duration': 0,
                'source': 'local',
            }
            await state.insert_next(song)
            await ctx.send(f"Added next: **{song['title']}**")
        if not state.is_playing:
            await state.start_playback_loop(ctx)

    # ---------- queue display ----------
    @commands.command(name='queue', aliases=['q'])
    async def queue_cmd(self, ctx):
        state = get_guild_state(ctx.guild.id)
        if not state.queue_list:
            await ctx.send("Queue is empty")
            return

        header = "**Queue:**"
        if state.loop_type:
            header += f" (loop: {state.loop_type})"
        if state.audio_filter:
            header += f" (filter: {state.audio_filter})"

        chunks: List[str] = []
        current: List[str] = [header]

        for i, song in enumerate(state.queue_list):
            num = i + 1
            dur = int(song.get('duration') or 0)
            d_str = f"{dur//60}:{dur%60:02d}" if dur else "?:??"
            requester = song.get('requester', '?')
            title = song['title']
            if i == state.current_index:
                if state.is_playing:
                    line = f"> **{num}. {title} ({d_str})** | {requester}"
                else:
                    line = f"> {num}. {title} ({d_str}) | {requester}"
            else:
                line = f"  {num}. {title} ({d_str}) | {requester}"

            if len('\n'.join(current + [line])) > 1900:
                chunks.append('\n'.join(current))
                current = ["**Queue (cont'd):**", line]
            else:
                current.append(line)

        if len(current) > 1:
            chunks.append('\n'.join(current))
        for c in chunks:
            await ctx.send(c)

    @commands.command(name='np', aliases=['nowplaying'])
    async def np_cmd(self, ctx):
        state = get_guild_state(ctx.guild.id)
        if not state.current_song:
            await ctx.send("Nothing is playing")
            return
        song = state.current_song
        elapsed = int(time.time() - state.start_time)
        dur = int(song.get('duration') or 0)
        e_str = f"{elapsed//60}:{elapsed%60:02d}"
        d_str = f"{dur//60}:{dur%60:02d}" if dur else "??:??"
        loop = {'song': ' | loop: song', 'queue': ' | loop: queue', None: ''}[state.loop_type]
        filt = f" | filter: {state.audio_filter}" if state.audio_filter else ""
        await ctx.send(
            f"**{song['title']}**\n`{e_str} / {d_str}` | {song.get('requester', '?')}{loop}{filt}"
        )

    # ---------- queue ops ----------
    @commands.command(name='remove', aliases=['rm'])
    async def remove_cmd(self, ctx, index: int):
        if not await self._check_dj(ctx):
            return
        state = get_guild_state(ctx.guild.id)
        if not (1 <= index <= len(state.queue_list)):
            await ctx.send(f"Invalid index. Queue has {len(state.queue_list)} songs.")
            return
        removed = await state.remove_at(ctx, index - 1)
        if removed:
            await ctx.send(f"Removed: **{removed['title']}**")

    @commands.command(name='move')
    async def move_cmd(self, ctx, src: int, dst: int):
        if not await self._check_dj(ctx):
            return
        state = get_guild_state(ctx.guild.id)
        n = len(state.queue_list)
        if not (1 <= src <= n and 1 <= dst <= n):
            await ctx.send(f"Indices must be between 1 and {n}")
            return
        song = await state.move(src - 1, dst - 1)
        if song:
            await ctx.send(f"Moved **{song['title']}** to position {dst}")

    @commands.command(name='jump', aliases=['skipto'])
    async def jump_cmd(self, ctx, index: int):
        if not await self._check_dj(ctx):
            return
        state = get_guild_state(ctx.guild.id)
        if not (1 <= index <= len(state.queue_list)):
            await ctx.send(f"Invalid index. Queue has {len(state.queue_list)} songs.")
            return
        if await state.jump_to(ctx, index - 1):
            await ctx.send(f"Jumped to #{index}")

    @commands.command(name='swap')
    async def swap_cmd(self, ctx, a: int, b: int):
        if not await self._check_dj(ctx):
            return
        state = get_guild_state(ctx.guild.id)
        n = len(state.queue_list)
        if not (1 <= a <= n and 1 <= b <= n):
            await ctx.send(f"Indices must be between 1 and {n}")
            return
        await state.swap(a - 1, b - 1)
        await ctx.send(f"Swapped positions {a} and {b}")

    @commands.command(name='shuffle', aliases=['random'])
    async def shuffle_cmd(self, ctx):
        state = get_guild_state(ctx.guild.id)
        if len(state.queue_list) < 2:
            await ctx.send("Need at least 2 songs to shuffle")
            return
        await state.shuffle()
        await ctx.send("Queue shuffled")

    @commands.command(name='clear')
    async def clear_cmd(self, ctx):
        if not await self._check_dj(ctx):
            return
        state = get_guild_state(ctx.guild.id)
        size = len(state.queue_list)
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
        state.queue_list.clear()
        state.current_index = -1
        state.current_song = None
        state.is_playing = False
        state.playback_active = False
        deleted = await state.cleanup_downloads()
        await ctx.send(f"Cleared {size} songs (deleted **{deleted}** files)")

    @commands.command(name='skip')
    async def skip_cmd(self, ctx):
        if not ctx.voice_client or not ctx.voice_client.is_playing():
            await ctx.send("Nothing playing")
            return
        state = get_guild_state(ctx.guild.id)
        if is_dj(ctx, ctx.guild.id):
            vote_skips[ctx.guild.id].clear()
            state._force_advance = True
            ctx.voice_client.stop()
            await ctx.send("Skipped")
            return
        await self._vote_skip(ctx)

    @commands.command(name='voteskip', aliases=['vs'])
    async def voteskip_cmd(self, ctx):
        if not ctx.voice_client or not ctx.voice_client.is_playing():
            await ctx.send("Nothing playing")
            return
        await self._vote_skip(ctx)

    async def _vote_skip(self, ctx):
        vc = ctx.voice_client
        if not vc or not vc.channel:
            await ctx.send("I'm not connected to a voice channel.")
            return
        if not vc.is_playing():
            await ctx.send("Nothing playing")
            return
        guild_id = ctx.guild.id
        vote_skips[guild_id].add(ctx.author.id)
        members = [m for m in vc.channel.members if not m.bot]
        needed = max(2, len(members) // 2 + 1)
        votes = len(vote_skips[guild_id])
        if votes >= needed:
            vote_skips[guild_id].clear()
            state = get_guild_state(guild_id)
            state._force_advance = True
            vc.stop()
            await ctx.send(f"Vote passed ({votes}/{needed}) - skipped")
        else:
            await ctx.send(f"Vote skip: **{votes}/{needed}**")

    @commands.command(name='pause')
    async def pause_cmd(self, ctx):
        if not await self._check_dj(ctx):
            return
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("Paused")
        else:
            await ctx.send("Nothing playing")

    @commands.command(name='resume')
    async def resume_cmd(self, ctx):
        if not await self._check_dj(ctx):
            return
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("Resumed")
        else:
            await ctx.send("Nothing paused")

    @commands.command(name='stop')
    async def stop_cmd(self, ctx):
        if not await self._check_dj(ctx):
            return
        state = get_guild_state(ctx.guild.id)
        if ctx.voice_client:
            ctx.voice_client.stop()
        state.queue_list.clear()
        state.current_index = -1
        state.current_song = None
        state.loop_type = None
        state.is_playing = False
        state.playback_active = False
        deleted = await state.cleanup_downloads()
        await ctx.send(f"Stopped (deleted **{deleted}** files)")

    @commands.command(name='loop')
    async def loop_cmd(self, ctx):
        state = get_guild_state(ctx.guild.id)
        if state.loop_type is None:
            state.loop_type = 'queue'
            await ctx.send("Looping queue (last -> first)")
        elif state.loop_type == 'queue':
            state.loop_type = 'song'
            await ctx.send("Looping current song")
        else:
            state.loop_type = None
            await ctx.send("Looping disabled")

    # ---------- filters ----------
    @commands.command(name='filter', aliases=['filters', 'eq'])
    async def filter_cmd(self, ctx, name: str = ""):
        state = get_guild_state(ctx.guild.id)
        name = name.lower().strip()
        if not name:
            names = ", ".join(f"`{n}`" for n in SONG_FILTERS)
            current = f" (current: `{state.audio_filter or 'none'}`)" if state.audio_filter else ""
            await ctx.send(f"Available filters: {names}{current}\nUse `!filter <name>` - applies to **next** track.")
            return
        if name not in SONG_FILTERS:
            await ctx.send(f"Unknown filter `{name}`. Options: {', '.join(SONG_FILTERS)}")
            return
        if not await self._check_dj(ctx):
            return
        state.audio_filter = name
        suffix = " (applies to next track)" if state.is_playing else ""
        await ctx.send(f"Filter set to `{name}`{suffix}")

    # ---------- 24/7 & DJ ----------
    @commands.command(name='247', aliases=['stay'])
    async def toggle_247(self, ctx, mode: str = ""):
        if not await self._check_dj(ctx):
            return
        gid = ctx.guild.id
        if mode.lower() in ('on', 'true', '1', 'enable'):
            stay_247[gid] = True
            await ctx.send("24/7 mode **enabled** - I'll reconnect if dropped.")
        elif mode.lower() in ('off', 'false', '0', 'disable'):
            stay_247[gid] = False
            await ctx.send("24/7 mode **disabled**.")
        else:
            state = "on" if stay_247[gid] else "off"
            await ctx.send(f"24/7 mode is currently **{state}**. Use `!247 on|off`.")

    @commands.command(name='dj')
    async def dj_cmd(self, ctx, action: str = "", *, role_arg: str = ""):
        gid = ctx.guild.id
        action = action.lower()
        if action == 'set':
            if not is_admin(ctx):
                await ctx.send("Only admins can set the DJ role.")
                return
            if not getattr(ctx.message, 'role_mentions', None):
                await ctx.send("Usage: `!dj set @Role`")
                return
            role = ctx.message.role_mentions[0]
            guild_dj_roles[gid] = role.id
            await ctx.send(f"DJ role set to **{role.name}**")
        elif action == 'clear':
            if not is_admin(ctx):
                await ctx.send("Only admins can clear the DJ role.")
                return
            guild_dj_roles.pop(gid, None)
            await ctx.send("DJ role cleared - everyone is a DJ again.")
        else:
            role_id = guild_dj_roles.get(gid)
            role = ctx.guild.get_role(role_id) if role_id else None
            if role:
                await ctx.send(f"Current DJ role: **{role.name}**")
            else:
                await ctx.send("No DJ role set (everyone can use restricted commands).")

    # ---------- playlists ----------
    @commands.command(name='qlist')
    async def qlist_cmd(self, ctx, *, name: str = ""):
        """Save current queue as a playlist of URLs."""
        name = name.strip()
        if not name:
            await ctx.send("Usage: `!qlist <playlist_name>`")
            return
        state = get_guild_state(ctx.guild.id)
        if not state.queue_list:
            await ctx.send("Queue is empty - nothing to save.")
            return
        urls: List[str] = []
        for song in state.queue_list:
            wp = song.get('webpage_url')
            if wp and wp.startswith(('http://', 'https://')):
                urls.append(wp)
            elif song.get('source') == 'download' and song.get('url', '').startswith(('http://', 'https://')):
                urls.append(song['url'])
            # skip local files (can't be recreated from a URL)
        if not urls:
            await ctx.send("No downloadable tracks in queue - nothing to save.")
            return
        if playlist_mod.save_playlist(name, urls):
            await ctx.send(f"Saved **{len(urls)}** tracks to playlist `{name}`")
        else:
            await ctx.send("Failed to save playlist.")

    @commands.command(name='qload')
    async def qload_cmd(self, ctx, *, name: str = ""):
        """Download a saved playlist and append it to the queue."""
        name = name.strip()
        if not name:
            await ctx.send("Usage: `!qload <playlist_name>`")
            return
        urls = playlist_mod.load_playlist(name)
        if urls is None:
            await ctx.send(f"Playlist `{name}` not found. Use `!qsearch` to browse.")
            return
        if not urls:
            await ctx.send(f"Playlist `{name}` is empty.")
            return
        if not await self.ensure_voice(ctx):
            return
        state = get_guild_state(ctx.guild.id)
        total = len(urls)
        status = await ctx.send(f"Loading **{name}** ({total} tracks)...")
        progress_msg = await ctx.send(f"Progress: 0/{total}")
        completed = 0

        async def progress_cb(_song):
            nonlocal completed
            completed += 1
            try:
                await progress_msg.edit(content=f"Progress: {completed}/{total}")
            except Exception:
                pass

        entries = [{'webpage_url': u, 'id': u} for u in urls]
        downloaded = await downloader.download_playlist_batch(
            entries, ctx.author.display_name, progress_callback=progress_cb, state=state
        )
        for song in downloaded:
            await state.add_song(song)
        try:
            await status.edit(content=f"Loaded **{len(downloaded)}/{total}** tracks from **{name}**")
            await progress_msg.delete()
        except Exception:
            pass
        if not state.is_playing and downloaded:
            await state.start_playback_loop(ctx)

    @commands.command(name='qsearch')
    async def qsearch_cmd(self, ctx):
        """Browse available playlists with arrow navigation."""
        names = playlist_mod.list_playlists()
        if not names:
            await ctx.send("No playlists saved. Use `!qlist <name>` to create one.")
            return
        view = playlist_mod.PlaylistBrowser(ctx, names)
        msg = await ctx.send(view.format_page(), view=view)
        view.message = msg

    @commands.command(name='deleteplaylist', aliases=['delplaylist'])
    async def delete_playlist_cmd(self, ctx, *, name: str = ""):
        if not name:
            await ctx.send("Usage: `!deleteplaylist <name>`")
            return
        if playlist_mod.delete_playlist(name):
            await ctx.send(f"Deleted playlist `{name}`")
        else:
            await ctx.send(f"Playlist `{name}` not found.")

    @commands.command(name='playlist_local')
    async def playlist_local(self, ctx, filename: str = ""):
        if not filename:
            await ctx.send("Usage: `!playlist_local <filename>`")
            return
        if not await self.ensure_voice(ctx):
            return
        state = get_guild_state(ctx.guild.id)
        filepath = os.path.join(os.getcwd(), filename)
        if not os.path.exists(filepath):
            await ctx.send(f"File not found: `{filename}`")
            return
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = [l.strip() for l in f if l.strip()]
            added = 0
            for line in lines:
                if os.path.exists(line):
                    song = {
                        'title': os.path.basename(line),
                        'url': os.path.abspath(line),
                        'requester': ctx.author.display_name,
                        'duration': 0,
                        'source': 'local',
                    }
                    await state.add_song(song)
                    added += 1
                else:
                    await ctx.send(f"Skipped (not found): `{line}`")
            await ctx.send(f"Added {added} local files")
            if not state.is_playing and added > 0:
                await state.start_playback_loop(ctx)
        except Exception as e:
            await ctx.send(f"Error: {e}")

    # ---------- meta ----------
    @commands.command(name='usage')
    async def usage_cmd(self, ctx):
        data = DATA_USAGE[ctx.guild.id]
        mb = data['total_bytes'] / 1024 / 1024
        uptime = time.time() - data['start_time']
        h, rem = divmod(uptime, 3600)
        m, _ = divmod(rem, 60)
        state = get_guild_state(ctx.guild.id)
        await ctx.send(
            f"**Usage**\n"
            f"Data: **{mb:.2f} MB**\n"
            f"Uptime: **{int(h)}h {int(m)}m**\n"
            f"Tracked files: **{len(state.downloaded_files)}**\n"
            f"Queue: **{len(state.queue_list)}** songs"
        )

    @commands.command(name='cleanup')
    async def cleanup_cmd(self, ctx):
        if not await self._check_dj(ctx):
            return
        state = get_guild_state(ctx.guild.id)
        n = await state.cleanup_downloads()
        await ctx.send(f"Deleted **{n}** tracked download files")

    @commands.command(name='shutdown')
    async def shutdown_cmd(self, ctx):
        if not is_admin(ctx):
            await ctx.send("Admins only")
            return
        await ctx.send("Shutting down and cleaning up...")
        await cleanup_all_downloads()
        await self.bot.close()

    @commands.command(name='help')
    async def help_cmd(self, ctx):
        p = BOT_PREFIX
        dj_access = (
            "DJ-only actions require the configured DJ role, Administrator, "
            "or Manage Server. If no DJ role is set, everyone has DJ access."
        )
        pages = (
            (
                "**Folda Tunez - Discord Help (1/4): Playback**\n"
                f"`{p}join` (alias: `{p}getinherelittleboy`) - Join the voice channel you are in.\n"
                f"`{p}leave` - Leave voice, stop playback, clear the queue, and delete downloads. {dj_access}\n"
                f"`{p}play <search terms or URL>` (aliases: `{p}stream`, `{p}p`) - Choose from YouTube search results, play a track URL, or load a playlist URL.\n"
                f"`{p}playnext <queue number|URL|local file>` (alias: `{p}pn`) - Move a queued track to next, or add a URL/file from the bot's host to play next.\n"
                f"`{p}pause` / `{p}resume` - Pause or resume the current track. {dj_access}\n"
                f"`{p}skip` - DJs skip immediately; other listeners start a vote-skip.\n"
                f"`{p}voteskip` (alias: `{p}vs`) - Vote to skip; a majority of at least two non-bot voice listeners is required.\n"
                f"`{p}stop` - Stop playback, clear the queue, and delete downloads. {dj_access}\n"
                f"`{p}loop` - Cycle through loop off, queue, and current track.\n"
            ),
            (
                "**Folda Tunez - Discord Help (2/4): Queue**\n"
                f"`{p}queue` (alias: `{p}q`) - Show the queue and track positions.\n"
                f"`{p}np` (alias: `{p}nowplaying`) - Show the current track and elapsed/total time.\n"
                f"`{p}remove <position>` (alias: `{p}rm`) - Remove a track by its queue position. {dj_access}\n"
                f"`{p}move <from position> <to position>` - Move a track. {dj_access}\n"
                f"`{p}jump <position>` (alias: `{p}skipto`) - Jump to a queue position. {dj_access}\n"
                f"`{p}swap <position 1> <position 2>` - Swap two tracks. {dj_access}\n"
                f"`{p}shuffle` (alias: `{p}random`) - Randomize the queue order.\n"
                f"`{p}clear` - Clear the queue and delete downloads. {dj_access}\n"
            ),
            (
                "**Folda Tunez - Discord Help (3/4): Playlists**\n"
                f"`{p}qlist <name>` - Save URL-based tracks in the current queue as a playlist. Local files are skipped.\n"
                f"`{p}qload <name>` - Download a saved playlist and append its tracks to the queue.\n"
                f"`{p}qsearch` - Browse saved playlists with the navigation buttons.\n"
                f"`{p}deleteplaylist <name>` (alias: `{p}delplaylist`) - Delete a saved playlist.\n"
                f"`{p}playlist_local <filename>` - Read local file paths, one per line, from a text file on the bot host and queue those files.\n"
            ),
            (
                "**Folda Tunez - Discord Help (4/4): Settings and Info**\n"
                f"`{p}filter` (aliases: `{p}filters`, `{p}eq`) - List available filters and show the current filter.\n"
                f"`{p}filter <name>` - Set a filter for the next track. Available: {', '.join(SONG_FILTERS)}. {dj_access}\n"
                f"`{p}247 on|off` (alias: `{p}stay`) - Enable or disable automatic voice reconnect. {dj_access}\n"
                f"`{p}dj` - Show the current DJ role.\n"
                f"`{p}dj set @Role` / `{p}dj clear` - Set or clear the DJ role. Administrator only.\n"
                f"`{p}usage` - Show tracked data usage, uptime, download count, and queue size.\n"
                f"`{p}cleanup` - Delete tracked downloads for this server. {dj_access}\n"
                f"`{p}shutdown` - Shut down the bot. Administrator only.\n"
                f"`{p}help` - Show this guide.\n"
                "Slash commands: `/play query`, `/skip`, `/pause`, `/resume`, `/np`, `/queue`, `/filter name`.\n"
            ),
        )
        for page in pages:
            await ctx.send(page)