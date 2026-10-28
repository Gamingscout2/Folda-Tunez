"""The Music cog: all user-facing playback commands."""
import asyncio
import os
import random
import time
import traceback
from typing import List

import discord
from discord.ext import commands

from audio import SONG_FILTERS
from config import BOT_PREFIX, MAX_PLAYLIST_ITEMS
from downloader import downloader, search_youtube
from guild_state import cleanup_all_downloads, get_guild_state, rebuild_queue
from helpers import is_admin, is_dj
from loggers import bot_logger
from persistence import load_playlists, save_playlists
from runtime import DATA_USAGE, guild_dj_roles, stay_247, vote_skips
from search_view import SearchView


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- helpers ----------
    async def ensure_voice(self, ctx: commands.Context) -> bool:
        if ctx.voice_client and ctx.voice_client.is_connected():
            return True
        if not getattr(ctx.author, 'voice', None) or not ctx.author.voice:
            await ctx.send("You need to be in a voice channel first!")
            return False
        channel = ctx.author.voice.channel
        try:
            await channel.connect(timeout=60, reconnect=True)
            from runtime import last_join_channels
            last_join_channels[ctx.guild.id] = channel
            return True
        except Exception as e:
            bot_logger.error(f"Voice connection failed: {e}")
            await ctx.send("Failed to connect to voice channel")
            return False

    async def _check_dj(self, ctx: commands.Context) -> bool:
        if is_dj(ctx, ctx.guild.id):
            return True
        await ctx.send("You need the DJ role or `Manage Server` permission.")
        return False

    # ---------- playback entry points ----------
    @commands.command(name='join', aliases=['getinherelittleboy'])
    async def join(self, ctx: commands.Context):
        if not await self.ensure_voice(ctx):
            return
        await ctx.send(f"Joined **{ctx.author.voice.channel.name}**")

    @commands.command(name='leave')
    async def leave(self, ctx: commands.Context):
        if not await self._check_dj(ctx):
            return
        state = get_guild_state(ctx.guild.id)
        await state.stop_playback_loop()
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
        deleted = await state.cleanup_downloads()
        async with state.lock:
            state.queue = asyncio.Queue()
            state.queue_list.clear()
            state.current_song = None
            state.loop_type = None
            state.history.clear()
            state.is_playing = False
            state.playback_active = False
        await ctx.send(f"Left voice and cleared queue (deleted **{deleted}** files)")

    @commands.command(name='stream', aliases=['play', 'p'])
    async def stream(self, ctx: commands.Context, *, query: str = ""):
        if not query:
            await ctx.send("Usage: `!stream <url or search>`")
            return
        if not await self.ensure_voice(ctx):
            return
        state = get_guild_state(ctx.guild.id)

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

    async def _handle_single_url(self, ctx: commands.Context, url: str):
        state = get_guild_state(ctx.guild.id)
        msg = await ctx.send("Downloading...")
        song = await downloader.download_single(url)
        if not song:
            await msg.edit(content="Failed to download track")
            return
        song['requester'] = ctx.author.display_name
        state.downloaded_files.add(song['url'])
        async with state.lock:
            await state.queue.put(song)
            state.queue_list.append(song)
        await msg.edit(content=f"Added: **{song['title']}**")
        if not state.is_playing:
            await state.start_playback_loop(ctx)

    async def _handle_playlist(self, ctx: commands.Context, url: str):
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
            async with state.lock:
                for song in downloaded:
                    await state.queue.put(song)
                    state.queue_list.append(song)

            if downloaded:
                await progress_msg.edit(
                    content=f"Added **{len(downloaded)}** tracks from **{title}**"
                )
            else:
                await progress_msg.edit(content="Failed to download any tracks")

            if not state.is_playing and downloaded:
                await state.start_playback_loop(ctx)
        except Exception:
            bot_logger.error(f"Playlist error: {traceback.format_exc()}")
            await ctx.send("Failed to process playlist")

    @commands.command(name='playnext', aliases=['pn'])
    async def playnext(self, ctx: commands.Context, *, args: str = ""):
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
            async with state.lock:
                if idx < 1 or idx > len(state.queue_list):
                    await ctx.send(f"Queue only has {len(state.queue_list)} songs.")
                    return
                song = state.queue_list.pop(idx - 1)
                song.pop('removed', None)
                state.queue_list.insert(0, song)
                rebuild_queue(state)
            await ctx.send(f"Moved **{song['title']}** to next.")

        elif args.startswith(('http://', 'https://')):
            msg = await ctx.send("Downloading...")
            song = await downloader.download_single(args)
            if not song:
                await msg.edit(content="Failed to download")
                return
            song['requester'] = ctx.author.display_name
            state.downloaded_files.add(song['url'])
            async with state.lock:
                state.queue_list.insert(0, song)
                state.queue._queue.appendleft(song)
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
            async with state.lock:
                state.queue_list.insert(0, song)
                state.queue._queue.appendleft(song)
            await ctx.send(f"Added next: **{song['title']}**")

        if not state.is_playing:
            await state.start_playback_loop(ctx)

    @commands.command(name='queue', aliases=['q'])
    async def queue_cmd(self, ctx: commands.Context):
        state = get_guild_state(ctx.guild.id)
        if not state.current_song and not state.queue_list:
            await ctx.send("Queue is empty")
            return

        chunks: List[str] = []
        current: List[str] = []

        if state.current_song:
            elapsed = int(time.time() - state.start_time)
            dur = int(state.current_song.get('duration') or 0)
            e_str = f"{elapsed//60}:{elapsed%60:02d}"
            d_str = f"{dur//60}:{dur%60:02d}" if dur else "??:??"
            current.append(f"**Now Playing:** {state.current_song['title']}")
            current.append(f"`{e_str}/{d_str}` | {state.current_song.get('requester', '?')}")

        if state.queue_list:
            current.append("\n**Upcoming:**" if current else "**Upcoming:**")
            for idx, song in enumerate(state.queue_list, 1):
                dur = int(song.get('duration') or 0)
                d_str = f"{dur//60}:{dur%60:02d}" if dur else "??:??"
                line = f"`{idx}.` {song['title']} ({d_str}) | {song.get('requester', '?')}"
                if len('\n'.join(current + [line])) > 1900:
                    chunks.append('\n'.join(current))
                    current = ["**Upcoming (cont'd):**", line]
                else:
                    current.append(line)

        if current:
            chunks.append('\n'.join(current))
        for c in chunks:
            await ctx.send(c)

    @commands.command(name='np', aliases=['nowplaying'])
    async def np_cmd(self, ctx: commands.Context):
        state = get_guild_state(ctx.guild.id)
        if not state.current_song:
            await ctx.send("Nothing is playing")
            return
        song = state.current_song
        elapsed = int(time.time() - state.start_time)
        dur = int(song.get('duration') or 0)
        e_str = f"{elapsed//60}:{elapsed%60:02d}"
        d_str = f"{dur//60}:{dur%60:02d}" if dur else "??:??"
        loop = {'song': '', 'queue': '', None: ''}[state.loop_type]
        filt = f" | `{state.audio_filter}`" if state.audio_filter else ""
        await ctx.send(
            f"**{song['title']}**\n"
            f"`{e_str} / {d_str}` | {song.get('requester', '?')} {loop}{filt}"
        )

    @commands.command(name='remove', aliases=['rm'])
    async def remove_cmd(self, ctx: commands.Context, index: int):
        if not await self._check_dj(ctx):
            return
        state = get_guild_state(ctx.guild.id)
        async with state.lock:
            if index < 1 or index > len(state.queue_list):
                await ctx.send(f"Invalid index. Queue has {len(state.queue_list)} songs.")
                return
            removed = state.queue_list.pop(index - 1)
            removed['removed'] = True
            rebuild_queue(state)
        await ctx.send(f"Removed: **{removed['title']}**")

    @commands.command(name='move')
    async def move_cmd(self, ctx: commands.Context, src: int, dst: int):
        if not await self._check_dj(ctx):
            return
        state = get_guild_state(ctx.guild.id)
        async with state.lock:
            n = len(state.queue_list)
            if not (1 <= src <= n and 1 <= dst <= n):
                await ctx.send(f"Indices must be between 1 and {n}")
                return
            song = state.queue_list.pop(src - 1)
            state.queue_list.insert(dst - 1, song)
            rebuild_queue(state)
        await ctx.send(f"Moved **{song['title']}** to position {dst}")

    @commands.command(name='jump', aliases=['skipto'])
    async def jump_cmd(self, ctx: commands.Context, index: int):
        if not await self._check_dj(ctx):
            return
        state = get_guild_state(ctx.guild.id)
        async with state.lock:
            if index < 1 or index > len(state.queue_list):
                await ctx.send(f"Invalid index. Queue has {len(state.queue_list)} songs.")
                return
            if index > 1:
                # remove everything before target
                state.queue_list = state.queue_list[index - 1:]
                rebuild_queue(state)
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
        await ctx.send(f"Jumped to #{index}")

    @commands.command(name='swap')
    async def swap_cmd(self, ctx: commands.Context, a: int, b: int):
        if not await self._check_dj(ctx):
            return
        state = get_guild_state(ctx.guild.id)
        async with state.lock:
            n = len(state.queue_list)
            if not (1 <= a <= n and 1 <= b <= n):
                await ctx.send(f"Indices must be between 1 and {n}")
                return
            state.queue_list[a - 1], state.queue_list[b - 1] = \
                state.queue_list[b - 1], state.queue_list[a - 1]
            rebuild_queue(state)
        await ctx.send(f"Swapped positions {a} and {b}")

    @commands.command(name='shuffle', aliases=['random'])
    async def shuffle_cmd(self, ctx: commands.Context):
        state = get_guild_state(ctx.guild.id)
        async with state.lock:
            if len(state.queue_list) < 2:
                await ctx.send("Need at least 2 songs to shuffle")
                return
            random.shuffle(state.queue_list)
            rebuild_queue(state)
        await ctx.send("Queue shuffled")

    @commands.command(name='clear')
    async def clear_cmd(self, ctx: commands.Context):
        if not await self._check_dj(ctx):
            return
        state = get_guild_state(ctx.guild.id)
        size = len(state.queue_list)
        async with state.lock:
            state.queue = asyncio.Queue()
            state.queue_list.clear()
            state.history.clear()
        deleted = await state.cleanup_downloads()
        await ctx.send(f"Cleared {size} songs (deleted **{deleted}** files)")

    @commands.command(name='skip')
    async def skip_cmd(self, ctx: commands.Context):
        if not ctx.voice_client or not ctx.voice_client.is_playing():
            await ctx.send("Nothing playing")
            return
        if is_dj(ctx, ctx.guild.id):
            vote_skips[ctx.guild.id].clear()
            ctx.voice_client.stop()
            await ctx.send("Skipped")
            return
        await self._vote_skip(ctx)

    @commands.command(name='voteskip', aliases=['vs'])
    async def voteskip_cmd(self, ctx: commands.Context):
        if not ctx.voice_client or not ctx.voice_client.is_playing():
            await ctx.send("Nothing playing")
            return
        await self._vote_skip(ctx)

    async def _vote_skip(self, ctx: commands.Context):
        """Register a vote-skip. Majority of non-bot listeners needed."""
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
            vc.stop()
            await ctx.send(f"Vote passed ({votes}/{needed}) - skipped")
        else:
            await ctx.send(f"Vote skip: **{votes}/{needed}**")

    @commands.command(name='pause')
    async def pause_cmd(self, ctx: commands.Context):
        if not await self._check_dj(ctx):
            return
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("Paused")
        else:
            await ctx.send("Nothing playing")

    @commands.command(name='resume')
    async def resume_cmd(self, ctx: commands.Context):
        if not await self._check_dj(ctx):
            return
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("Resumed")
        else:
            await ctx.send("Nothing paused")

    @commands.command(name='stop')
    async def stop_cmd(self, ctx: commands.Context):
        if not await self._check_dj(ctx):
            return
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
        deleted = await state.cleanup_downloads()
        await ctx.send(f"Stopped (deleted **{deleted}** files)")

    @commands.command(name='loop')
    async def loop_cmd(self, ctx: commands.Context):
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

    @commands.command(name='filter', aliases=['filters', 'eq'])
    async def filter_cmd(self, ctx: commands.Context, name: str = ""):
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

    @commands.command(name='247', aliases=['stay'])
    async def toggle_247(self, ctx: commands.Context, mode: str = ""):
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
    async def dj_cmd(self, ctx: commands.Context, action: str = "", *, role_arg: str = ""):
        gid = ctx.guild.id
        action = action.lower()
        if action == 'set':
            if not is_admin(ctx):
                await ctx.send("Only admins can set the DJ role.")
                return
            if not ctx.message.role_mentions:
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

    @commands.command(name='save')
    async def save_cmd(self, ctx: commands.Context, *, name: str = ""):
        name = name.strip()
        if not name:
            await ctx.send("Usage: `!save <playlist_name>`")
            return
        state = get_guild_state(ctx.guild.id)
        urls = [s.get('webpage_url') or s.get('url') for s in state.queue_list
                if s.get('webpage_url') or s.get('source') == 'download']
        if not urls:
            await ctx.send("No downloadable tracks in queue to save.")
            return
        playlists = load_playlists()
        playlists[name] = {'tracks': urls, 'author': ctx.author.display_name, 'saved': time.time()}
        save_playlists(playlists)
        await ctx.send(f"Saved **{name}** ({len(urls)} tracks)")

    @commands.command(name='load')
    async def load_cmd(self, ctx: commands.Context, *, name: str = ""):
        name = name.strip()
        playlists = load_playlists()
        if name not in playlists:
            await ctx.send(f"Playlist `{name}` not found. Use `!playlists`.")
            return
        if not await self.ensure_voice(ctx):
            return
        tracks = playlists[name].get('tracks', [])
        if not tracks:
            await ctx.send("Playlist is empty")
            return
        await ctx.send(f"Loading **{name}** ({len(tracks)} tracks)...")
        state = get_guild_state(ctx.guild.id)
        entries = [{'webpage_url': u, 'id': u} for u in tracks]
        downloaded = await downloader.download_playlist_batch(
            entries, ctx.author.display_name, state=state
        )
        async with state.lock:
            for s in downloaded:
                await state.queue.put(s)
                state.queue_list.append(s)
        await ctx.send(f"Loaded **{len(downloaded)}** tracks from **{name}**")
        if not state.is_playing and downloaded:
            await state.start_playback_loop(ctx)

    @commands.command(name='playlists')
    async def playlists_cmd(self, ctx: commands.Context):
        playlists = load_playlists()
        if not playlists:
            await ctx.send("No saved playlists")
            return
        lines = ["**Saved Playlists:**"]
        for name, data in list(playlists.items())[:20]:
            lines.append(f"- `{name}` - {len(data.get('tracks', []))} tracks")
        await ctx.send("\n".join(lines))

    @commands.command(name='deleteplaylist', aliases=['delplaylist'])
    async def delete_playlist_cmd(self, ctx: commands.Context, *, name: str = ""):
        playlists = load_playlists()
        if name not in playlists:
            await ctx.send(f"Playlist `{name}` not found.")
            return
        del playlists[name]
        save_playlists(playlists)
        await ctx.send(f"Deleted playlist `{name}`")

    @commands.command(name='playlist_local')
    async def playlist_local(self, ctx: commands.Context, filename: str = ""):
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
            async with state.lock:
                for line in lines:
                    if os.path.exists(line):
                        song = {
                            'title': os.path.basename(line),
                            'url': os.path.abspath(line),
                            'requester': ctx.author.display_name,
                            'duration': 0,
                            'source': 'local',
                        }
                        await state.queue.put(song)
                        state.queue_list.append(song)
                        added += 1
                    else:
                        await ctx.send(f"Skipped (not found): `{line}`")
            await ctx.send(f"Added {added} local files")
            if not state.is_playing and added > 0:
                await state.start_playback_loop(ctx)
        except Exception as e:
            await ctx.send(f"Error: {e}")

    @commands.command(name='usage')
    async def usage_cmd(self, ctx: commands.Context):
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
            f"Tracked files: **{len(state.downloaded_files)}**"
        )

    @commands.command(name='cleanup')
    async def cleanup_cmd(self, ctx: commands.Context):
        if not await self._check_dj(ctx):
            return
        state = get_guild_state(ctx.guild.id)
        n = await state.cleanup_downloads()
        await ctx.send(f"Deleted **{n}** tracked download files")

    @commands.command(name='shutdown')
    async def shutdown_cmd(self, ctx: commands.Context):
        if not is_admin(ctx):
            await ctx.send("Admins only")
            return
        await ctx.send("Shutting down and cleaning up...")
        await cleanup_all_downloads()
        await self.bot.close()

    @commands.command(name='help')
    async def help_cmd(self, ctx: commands.Context):
        p = BOT_PREFIX
        text = (
            "**Folda Tunez v0.5.2**\n"
            f"`{p}join` / `{p}leave`\n"
            f"`{p}stream <url|search>` - play from URL or search YouTube\n"
            f"`{p}playnext <num|url|file>` - jump to front of queue\n"
            f"`{p}queue` / `{p}np` - view queue / now playing\n"
            f"`{p}move <from> <to>` - `{p}swap <a> <b>` - `{p}jump <n>`\n"
            f"`{p}remove <n>` / `{p}rm <n>` - remove from queue\n"
            f"`{p}shuffle` / `{p}random` - `{p}clear`\n"
            f"`{p}skip` - `{p}voteskip` - `{p}pause` / `{p}resume`\n"
            f"`{p}stop` - `{p}loop`\n"
            f"`{p}filter <name>` - bassboost / nightcore / 8d / vaporwave / treble / normalize\n"
            f"`{p}247 on|off` - auto-reconnect\n"
            f"`{p}dj set @role` - `{p}dj clear` - `{p}dj`\n"
            f"`{p}save <name>` - `{p}load <name>` - `{p}playlists` - `{p}deleteplaylist <name>`\n"
            f"`{p}playlist_local <file>` - `{p}usage` - `{p}cleanup` - `{p}shutdown`\n"
            "**Slash:** `/play` `/skip` `/pause` `/resume` `/np` `/queue` `/filter`"
        )
        await ctx.send(text)