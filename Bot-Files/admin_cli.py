"""Interactive CLI for remote administration."""
import asyncio
import sys
import traceback
from typing import Dict, Optional

import discord
from discord.ext import commands

from contexts import MockContext
from guild_state import get_guild_state, cleanup_all_downloads
from loggers import cli_logger


class AdminCLI:
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.running = True
        self.guild_ids: Dict[int, int] = {}
        self.channel_ids: Dict[int, int] = {}
        self.next_guild_id = 1
        self.next_channel_id = 1

    def safe_input(self, prompt: str) -> str:
        try:
            return input(prompt)
        except UnicodeDecodeError:
            try:
                return sys.stdin.buffer.readline().decode('utf-8', errors='replace').rstrip('\n')
            except Exception:
                return ""

    async def run_async(self):
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

    async def process_command(self, cmd_line: str):
        parts = cmd_line.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        handlers = {
            'servers': self.cmd_servers, 'channels': self.cmd_channels,
            'sendmsg': self.cmd_sendmsg, 'join': self.cmd_join,
            'stream': self.cmd_stream, 'clear': self.cmd_clear,
            'leave': self.cmd_leave, 'pause': self.cmd_pause,
            'resume': self.cmd_resume, 'queue': self.cmd_queue,
            'shuffle': self.cmd_shuffle, 'loop': self.cmd_loop,
            'usage': self.cmd_usage, 'kill': self.cmd_kill,
            'exit': self.cmd_exit, 'cleanup': self.cmd_cleanup,
        }
        if cmd in handlers:
            await handlers[cmd](args)
        else:
            print(f"Unknown command: {cmd}")

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

    async def cmd_servers(self, args):
        for guild in self.bot.guilds:
            if guild.id not in self.guild_ids.values():
                self.guild_ids[self.next_guild_id] = guild.id
                self.next_guild_id += 1
            bid = next(k for k, v in self.guild_ids.items() if v == guild.id)
            state = get_guild_state(guild.id)
            vc = "Connected" if guild.voice_client else "Disconnected"
            pb = "Playing" if state.is_playing else "Idle"
            cur = (state.current_song['title'][:20] + '...') if state.current_song else 'None'
            print(f"{guild.name} | BOT ID: {bid} | {vc} | {pb} | {cur} | Q: {state.queue.qsize()}")

    async def cmd_channels(self, args):
        guild = self._get_guild(args)
        if not guild:
            print("Invalid guild ID"); return
        for ch in guild.channels:
            if ch.id not in self.channel_ids.values():
                self.channel_ids[self.next_channel_id] = ch.id
                self.next_channel_id += 1
            bid = next(k for k, v in self.channel_ids.items() if v == ch.id)
            print(f"{ch.name} | BOT ID: {bid} | {type(ch).__name__}")

    async def cmd_sendmsg(self, args):
        parts = args.split(maxsplit=2)
        if len(parts) < 3:
            print("Usage: sendmsg <guild_id> <channel_id> <message>"); return
        guild = self._get_guild(parts[0])
        ch = self._get_channel(guild, parts[1]) if guild else None
        if not guild or not isinstance(ch, discord.TextChannel):
            print("Invalid"); return
        await ch.send(parts[2])
        print("Sent")

    async def cmd_join(self, args):
        parts = args.split()
        if len(parts) < 2:
            print("Usage: join <guild_id> <channel_id>"); return
        guild = self._get_guild(parts[0])
        ch = self._get_channel(guild, parts[1]) if guild else None
        if not guild or not isinstance(ch, discord.VoiceChannel):
            print("Invalid"); return
        if guild.voice_client:
            await guild.voice_client.move_to(ch)
        else:
            await ch.connect()
        print(f"Joined {ch.name}")

    async def _call(self, cmd_name, guild, **kwargs):
        ctx = MockContext(guild)
        await self.bot.get_command(cmd_name).callback(ctx, **kwargs)

    async def cmd_stream(self, args):
        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            print("Usage: stream <guild_id> <url>"); return
        guild = self._get_guild(parts[0])
        if not guild: print("Invalid"); return
        await self._call('stream', guild, query=parts[1])

    async def cmd_clear(self, args):
        g = self._get_guild(args)
        if g: await self._call('clear', g)

    async def cmd_leave(self, args):
        g = self._get_guild(args)
        if g: await self._call('leave', g)

    async def cmd_pause(self, args):
        g = self._get_guild(args)
        if g: await self._call('pause', g)

    async def cmd_resume(self, args):
        g = self._get_guild(args)
        if g: await self._call('resume', g)

    async def cmd_queue(self, args):
        g = self._get_guild(args)
        if g: await self._call('queue', g)

    async def cmd_shuffle(self, args):
        g = self._get_guild(args)
        if g: await self._call('shuffle', g)

    async def cmd_loop(self, args):
        g = self._get_guild(args)
        if g: await self._call('loop', g)

    async def cmd_usage(self, args):
        g = self._get_guild(args)
        if g: await self._call('usage', g)

    async def cmd_cleanup(self, args):
        g = self._get_guild(args)
        if not g: print("Invalid"); return
        state = get_guild_state(g.id)
        n = await state.cleanup_downloads()
        print(f"Cleaned {n} files")

    async def cmd_kill(self, args):
        print("Shutting down...")
        await cleanup_all_downloads()
        await self.bot.close()
        self.running = False

    async def cmd_exit(self, args):
        self.running = False
        print("Exiting CLI. Bot continues running.")