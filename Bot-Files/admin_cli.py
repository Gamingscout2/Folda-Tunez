"""Interactive CLI with full bot control, per-guild log buffer, and task inspection."""

import asyncio
import importlib
import sys
import time
import traceback
from typing import Dict, Optional

import discord
from discord.ext import commands

from contexts import MockContext
from guild_state import cleanup_all_downloads, get_guild_state
from loggers import cli_logger
import playlists as playlist_mod


class AdminCLI:
    def __init__(self, bot: commands.Bot, console):
        self.bot = bot
        self.console = console
        self.running = True
        self.guild_ids: Dict[int, int] = {}
        self.channel_ids: Dict[int, int] = {}
        self.next_guild_id = 1
        self.next_channel_id = 1
        self.start_time = time.time()
        self.loop = None
        self.command_queue: Optional[asyncio.Queue] = None

    # ---------- input ----------
    def safe_input(self, prompt: str) -> str:
        try:
            return input(prompt)
        except UnicodeDecodeError:
            try:
                return sys.stdin.buffer.readline().decode('utf-8', errors='replace').rstrip('\n')
            except Exception:
                return ""

    async def run_async(self):
        self._refresh_guild_ids()

        if self.console._enabled:
            # Split-screen mode: reader thread -> asyncio queue -> here
            self.loop = asyncio.get_running_loop()
            self.command_queue = asyncio.Queue()
            self.console.start(self.loop, self._enqueue_command)
            asyncio.create_task(self._status_updater(), name="cli-status")
            self.console.update_status()
            print("Folda Tunez CLI ready. Type 'help' for commands.")
            while self.running:
                try:
                    line = await self.command_queue.get()
                    if line.strip():
                        await self.process_command(line.strip())
                except Exception:
                    cli_logger.error(f"CLI error: {traceback.format_exc()}")
        else:
            # Fallback: plain blocking input in an executor
            print("Folda Tunez CLI ready. Type 'help' for commands.")
            while self.running:
                try:
                    cmd = await asyncio.get_event_loop().run_in_executor(
                        None, self.safe_input, "\nFoldaTunez> "
                    )
                    if not cmd:
                        continue
                    await self.process_command(cmd.strip())
                except EOFError:
                    break
                except Exception:
                    cli_logger.error(f"CLI error: {traceback.format_exc()}")

    def _enqueue_command(self, line: str):
        if self.command_queue:
            try:
                self.loop.call_soon_threadsafe(self.command_queue.put_nowait, line)
            except Exception:
                pass

    async def _status_updater(self):
        while self.running:
            try:
                self.console.update_status()
            except Exception:
                pass
            await asyncio.sleep(2)

    def _refresh_guild_ids(self):
        for guild in self.bot.guilds:
            if guild.id not in self.guild_ids.values():
                self.guild_ids[self.next_guild_id] = guild.id
                self.next_guild_id += 1

    # ---------- dispatch ----------
    async def process_command(self, cmd_line: str):
        parts = cmd_line.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        handlers = {
            'help':           self.cmd_help,
            'servers':        self.cmd_servers,
            'guilds':         self.cmd_servers,
            'channels':       self.cmd_channels,
            'voice_channels': self.cmd_voice_channels,
            'text_channels':  self.cmd_text_channels,
            'members':        self.cmd_members,
            'guildinfo':      self.cmd_guildinfo,
            'botinfo':        self.cmd_botinfo,
            'sendmsg':        self.cmd_sendmsg,
            'sendall':        self.cmd_sendall,
            'join':           self.cmd_join,
            'leave':          self.cmd_leave,
            'stream':         self.cmd_stream,
            'queue':          self.cmd_queue,
            'clear':          self.cmd_clear,
            'shuffle':        self.cmd_shuffle,
            'loop':           self.cmd_loop,
            'pause':          self.cmd_pause,
            'resume':         self.cmd_resume,
            'skip':           self.cmd_skip,
            'stop':           self.cmd_stop,
            'filter':         self.cmd_filter,
            'status':         self.cmd_status,
            'sync':           self.cmd_sync,
            'reload':         self.cmd_reload,
            'cleanup':        self.cmd_cleanup,
            'usage':          self.cmd_usage,
            'playlists':      self.cmd_playlists,
            'guildlog':       self.cmd_guildlog,
            'threads':        self.cmd_threads,
            'kill':           self.cmd_kill,
            'shutdown':       self.cmd_kill,
            'exit':           self.cmd_exit,
            'quit':           self.cmd_exit,
        }
        if cmd in handlers:
            await handlers[cmd](args)
        else:
            print(f"Unknown command: {cmd}. Type 'help' for the command list.")

    # ---------- helpers ----------
    def _get_guild(self, bot_id: str) -> Optional[discord.Guild]:
        try:
            gid = self.guild_ids.get(int(bot_id))
            return self.bot.get_guild(gid) if gid else None
        except Exception:
            return None

    def _get_channel(self, guild, bot_id):
        try:
            cid = self.channel_ids.get(int(bot_id))
            return guild.get_channel(cid) if cid else None
        except Exception:
            return None

    async def _call(self, cmd_name, guild, **kwargs):
        ctx = MockContext(guild)
        await self.bot.get_command(cmd_name).callback(ctx, **kwargs)

    # ---------- help ----------
    async def cmd_help(self, args):
        print(
            "\n"
            "Folda Tunez CLI commands:\n"
            "\n"
            "Introspection:\n"
            "  servers / guilds                 - list all guilds (bot id, real id, status)\n"
            "  channels <guild>                 - all channels in a guild\n"
            "  voice_channels <guild>           - voice channels only\n"
            "  text_channels <guild>            - text channels only\n"
            "  members <guild>                  - list members\n"
            "  guildinfo <guild>                - detailed guild + playback state\n"
            "  botinfo                          - bot stats (latency, guilds, uptime)\n"
            "\n"
            "Messaging:\n"
            "  sendmsg <guild> <chan> <msg>     - send a message\n"
            "  sendall <msg>                    - send to every guild's system channel\n"
            "\n"
            "Voice / playback:\n"
            "  join <guild> <channel>           - join a voice channel\n"
            "  leave <guild>                    - leave voice + clear queue\n"
            "  stream <guild> <url>             - stream a URL\n"
            "  queue <guild>                    - show queue\n"
            "  clear <guild>                    - clear queue\n"
            "  shuffle <guild>                  - shuffle queue\n"
            "  loop <guild>                     - cycle loop mode\n"
            "  pause <guild> / resume <guild>   - pause/resume\n"
            "  skip <guild>                     - skip current track\n"
            "  stop <guild>                     - stop playback\n"
            "  filter <guild> [name]            - set / show audio filter\n"
            "\n"
            "Debug:\n"
            "  guildlog <guild>                 - show buffered logs for a guild\n"
            "  guildlog <guild> follow          - live-tail that guild's logs\n"
            "  guildlog off                     - stop filtering (show all)\n"
            "  guildlog clear [<guild>]         - clear buffer\n"
            "  threads                          - dump all asyncio tasks + stacks\n"
            "\n"
            "Bot control:\n"
            "  status <type> [text]             - set presence (playing/watching/listening/competing/clear)\n"
            "  sync                             - re-sync slash commands\n"
            "  reload                           - reload Music cog\n"
            "  cleanup [guild]                  - delete tracked downloads\n"
            "  usage <guild>                    - data usage stats\n"
            "  playlists                        - list saved playlists\n"
            "\n"
            "Lifecycle:\n"
            "  kill / shutdown                  - shut the bot down\n"
            "  exit / quit                      - exit CLI (bot keeps running)\n"
            "  help                             - this list\n"
        )

    # ---------- introspection ----------
    async def cmd_servers(self, args):
        self._refresh_guild_ids()
        if not self.bot.guilds:
            print("Bot is not in any guilds.")
            return
        print(f"{'BOT ID':<8} {'REAL ID':<22} {'NAME':<30} {'VOICE':<12} {'Q':<4} STATUS")
        print("-" * 100)
        for guild in self.bot.guilds:
            bid = next(k for k, v in self.guild_ids.items() if v == guild.id)
            state = get_guild_state(guild.id)
            vc = "Connected" if guild.voice_client else "Disconnected"
            pb = "Playing" if state.is_playing else "Idle"
            print(f"{bid:<8} {guild.id:<22} {guild.name[:28]:<30} {vc:<12} {len(state.queue_list):<4} {pb}")

    async def cmd_channels(self, args):
        guild = self._get_guild(args)
        if not guild:
            print("Invalid guild ID"); return
        for ch in guild.channels:
            if ch.id not in self.channel_ids.values():
                self.channel_ids[self.next_channel_id] = ch.id
                self.next_channel_id += 1
            bid = next(k for k, v in self.channel_ids.items() if v == ch.id)
            print(f"{bid:<6} {type(ch).__name__:<18} {ch.name} (id={ch.id})")

    async def cmd_voice_channels(self, args):
        guild = self._get_guild(args)
        if not guild:
            print("Invalid guild ID"); return
        for ch in guild.voice_channels:
            if ch.id not in self.channel_ids.values():
                self.channel_ids[self.next_channel_id] = ch.id
                self.next_channel_id += 1
            bid = next(k for k, v in self.channel_ids.items() if v == ch.id)
            print(f"{bid:<6} {ch.name} (id={ch.id})")

    async def cmd_text_channels(self, args):
        guild = self._get_guild(args)
        if not guild:
            print("Invalid guild ID"); return
        for ch in guild.text_channels:
            if ch.id not in self.channel_ids.values():
                self.channel_ids[self.next_channel_id] = ch.id
                self.next_channel_id += 1
            bid = next(k for k, v in self.channel_ids.items() if v == ch.id)
            print(f"{bid:<6} #{ch.name} (id={ch.id})")

    async def cmd_members(self, args):
        guild = self._get_guild(args)
        if not guild:
            print("Invalid guild ID"); return
        print(f"{len(guild.members)} members in {guild.name}:")
        for m in guild.members:
            tag = "BOT " if m.bot else "USER"
            print(f"{tag} {m.display_name:<24} ({m.name}) id={m.id}")

    async def cmd_guildinfo(self, args):
        guild = self._get_guild(args)
        if not guild:
            print("Invalid guild ID"); return
        state = get_guild_state(guild.id)
        print(f"Name:          {guild.name}")
        print(f"ID:            {guild.id}")
        print(f"Owner:         {guild.owner.display_name if guild.owner else '?'} ({guild.owner_id})")
        print(f"Members:       {guild.member_count}")
        print(f"Channels:      {len(guild.channels)} total")
        print(f"  Voice:       {len(guild.voice_channels)}")
        print(f"  Text:        {len(guild.text_channels)}")
        print(f"Roles:         {len(guild.roles)}")
        print(f"Boost level:   {guild.premium_tier}")
        print(f"Created:       {guild.created_at}")
        vc = guild.voice_client
        print(f"Voice client:  {vc.channel.name if vc and vc.channel else 'Not connected'}")
        print(f"--- Playback state ---")
        print(f"Queue length:  {len(state.queue_list)}")
        print(f"Current index: {state.current_index}")
        print(f"Current song:  {state.current_song['title'] if state.current_song else '(none)'}")
        print(f"Is playing:    {state.is_playing}")
        print(f"Loop type:     {state.loop_type or 'off'}")
        print(f"Filter:        {state.audio_filter or 'none'}")
        print(f"Tracked files: {len(state.downloaded_files)}")
        pt = state.playback_task
        if pt:
            try:
                print(f"Playback task: {pt.get_name()} | {'done' if pt.done() else 'running'}")
            except Exception:
                print(f"Playback task: {pt}")
        else:
            print(f"Playback task: (none)")

    async def cmd_botinfo(self, args):
        print(f"Bot:      {self.bot.user} (id={self.bot.user.id})")
        print(f"Latency:  {self.bot.latency * 1000:.1f} ms")
        print(f"Guilds:   {len(self.bot.guilds)}")
        print(f"Users:    {sum(g.member_count for g in self.bot.guilds)}")
        print(f"Uptime:   {int(time.time() - self.start_time)}s")
        print(f"Tasks:    {len(asyncio.all_tasks())}")

    # ---------- messaging ----------
    async def cmd_sendmsg(self, args):
        parts = args.split(maxsplit=2)
        if len(parts) < 3:
            print("Usage: sendmsg <guild> <channel> <message>"); return
        guild = self._get_guild(parts[0])
        ch = self._get_channel(guild, parts[1]) if guild else None
        if not guild or not isinstance(ch, discord.TextChannel):
            print("Invalid guild or channel"); return
        try:
            await ch.send(parts[2])
            print("Sent")
        except Exception as e:
            print(f"Failed: {e}")

    async def cmd_sendall(self, args):
        if not args:
            print("Usage: sendall <message>"); return
        sent = 0
        for guild in self.bot.guilds:
            ch = guild.system_channel
            if ch and ch.permissions_for(guild.me).send_messages:
                try:
                    await ch.send(args)
                    sent += 1
                except Exception:
                    pass
        print(f"Sent to {sent} guild system channels")

    # ---------- voice / playback ----------
    async def cmd_join(self, args):
        parts = args.split()
        if len(parts) < 2:
            print("Usage: join <guild> <channel>"); return
        guild = self._get_guild(parts[0])
        ch = self._get_channel(guild, parts[1]) if guild else None
        if not guild or not isinstance(ch, discord.VoiceChannel):
            print("Invalid guild or voice channel"); return
        try:
            if guild.voice_client:
                await guild.voice_client.move_to(ch)
            else:
                await ch.connect()
            print(f"Joined {ch.name}")
        except Exception as e:
            print(f"Failed: {e}")

    async def cmd_leave(self, args):
        g = self._get_guild(args)
        if g: await self._call('leave', g)

    async def cmd_stream(self, args):
        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            print("Usage: stream <guild> <url>"); return
        guild = self._get_guild(parts[0])
        if not guild:
            print("Invalid guild"); return
        await self._call('stream', guild, query=parts[1])

    async def cmd_queue(self, args):
        g = self._get_guild(args)
        if g: await self._call('queue', g)

    async def cmd_clear(self, args):
        g = self._get_guild(args)
        if g: await self._call('clear', g)

    async def cmd_shuffle(self, args):
        g = self._get_guild(args)
        if g: await self._call('shuffle', g)

    async def cmd_loop(self, args):
        g = self._get_guild(args)
        if g: await self._call('loop', g)

    async def cmd_pause(self, args):
        g = self._get_guild(args)
        if g: await self._call('pause', g)

    async def cmd_resume(self, args):
        g = self._get_guild(args)
        if g: await self._call('resume', g)

    async def cmd_skip(self, args):
        g = self._get_guild(args)
        if g: await self._call('skip', g)

    async def cmd_stop(self, args):
        g = self._get_guild(args)
        if g: await self._call('stop', g)

    async def cmd_filter(self, args):
        parts = args.split(maxsplit=1)
        if not parts:
            print("Usage: filter <guild> [name]"); return
        g = self._get_guild(parts[0])
        if not g:
            print("Invalid guild"); return
        name = parts[1] if len(parts) > 1 else ""
        await self._call('filter', g, name=name)

    # ---------- bot control ----------
    async def cmd_status(self, args):
        parts = args.split(maxsplit=1)
        act = parts[0].lower() if parts else ""
        text = parts[1] if len(parts) > 1 else ""
        types = {
            'playing':   discord.ActivityType.playing,
            'watching':  discord.ActivityType.watching,
            'listening': discord.ActivityType.listening,
            'competing': discord.ActivityType.competing,
        }
        if act == 'clear':
            await self.bot.change_presence(activity=None)
            print("Cleared status")
        elif act in types:
            await self.bot.change_presence(activity=discord.Activity(type=types[act], name=text))
            print(f"Set status: {act} {text}")
        else:
            print("Usage: status <playing|watching|listening|competing|clear> [text]")

    async def cmd_sync(self, args):
        try:
            await self.bot.tree.sync()
            print("Slash commands synced")
        except Exception as e:
            print(f"Sync failed: {e}")

    async def cmd_reload(self, args):
        try:
            old = self.bot.get_cog('Music')
            if old:
                await self.bot.remove_cog('Music')
            import music
            importlib.reload(music)
            await self.bot.add_cog(music.Music(self.bot))
            print("Reloaded Music cog")
        except Exception as e:
            print(f"Reload failed: {e}")

    # ---------- data ----------
    async def cmd_cleanup(self, args):
        if not args:
            await cleanup_all_downloads()
            print("Cleaned up all tracked files")
            return
        g = self._get_guild(args)
        if not g:
            print("Invalid guild"); return
        state = get_guild_state(g.id)
        n = await state.cleanup_downloads()
        print(f"Cleaned {n} files")

    async def cmd_usage(self, args):
        g = self._get_guild(args)
        if g: await self._call('usage', g)

    async def cmd_playlists(self, args):
        names = playlist_mod.list_playlists()
        if not names:
            print("No playlists saved")
            return
        print(f"{len(names)} playlists:")
        for name in names:
            urls = playlist_mod.load_playlist(name)
            print(f"  {name} ({len(urls or [])} tracks)")

    # ---------- debug ----------
    async def cmd_guildlog(self, args):
        parts = args.split()
        if not parts:
            self._print_guildlog_help(); return

        sub = parts[0].lower()
        if sub == 'off':
            self.console.guild_filter = None
            self.console.update_status()
            print("Log filter disabled - showing all logs.")
            return

        if sub == 'clear':
            if len(parts) > 1:
                g = self._get_guild(parts[1])
                if g:
                    self.console.guild_logs[g.id].clear()
                    print(f"Cleared log buffer for guild {parts[1]}")
                else:
                    print("Invalid guild ID")
            else:
                for buf in self.console.guild_logs.values():
                    buf.clear()
                print("Cleared all guild log buffers.")
            return

        g = self._get_guild(parts[0])
        if not g:
            print("Invalid guild ID"); return

        if len(parts) > 1 and parts[1].lower() == 'follow':
            self.console.guild_filter = g.id
            self.console.update_status()
            print(f"Following logs for guild {g.name} (id={g.id}). 'guildlog off' to stop.")
            return

        buf = self.console.guild_logs.get(g.id)
        if not buf:
            print(f"No logs buffered for guild {g.name} yet.")
            return
        print(f"Last {len(buf)} log lines for guild {g.name}:")
        for line in buf:
            print(f"  {line}")

    def _print_guildlog_help(self):
        print("Usage:")
        print("  guildlog <guild>          - show buffered logs")
        print("  guildlog <guild> follow   - live-tail guild logs")
        print("  guildlog off              - stop filtering")
        print("  guildlog clear [<guild>]  - clear buffer")

    async def cmd_threads(self, args):
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        print(f"{len(tasks)} active asyncio task(s):")
        for task in tasks:
            try:
                name = task.get_name()
            except Exception:
                name = '?'
            coro = task.get_coro()
            coro_name = getattr(coro, '__name__', str(coro))
            if task.done():
                if task.cancelled():
                    state = 'cancelled'
                elif task.exception():
                    state = f"error({type(task.exception()).__name__})"
                else:
                    state = 'done'
            else:
                state = 'running'
            gid = None
            try:
                frame = coro.cr_frame if hasattr(coro, 'cr_frame') else None
                if frame:
                    self_obj = frame.f_locals.get('self')
                    if hasattr(self_obj, 'guild_id'):
                        gid = self_obj.guild_id
            except Exception:
                pass
            extra = f" guild={gid}" if gid else ""
            print(f"  [{state:<12}] {name} | {coro_name}{extra}")
            if state == 'running':
                try:
                    stack = task.get_stack(limit=3)
                    for frame in stack or []:
                        print(f"      {frame.f_code.co_filename}:{frame.f_lineno} in {frame.f_code.co_name}")
                except Exception:
                    pass

    # ---------- lifecycle ----------
    async def cmd_kill(self, args):
        print("Shutting down...")
        await cleanup_all_downloads()
        await self.bot.close()
        self.running = False

    async def cmd_exit(self, args):
        self.running = False
        print("Exiting CLI. Bot continues running.")