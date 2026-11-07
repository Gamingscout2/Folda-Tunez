"""Context shims for the CLI admin tool and slash commands."""
from typing import Optional

import discord


class MockContext:
    def __init__(self, guild: discord.Guild, channel: Optional[discord.TextChannel] = None):
        self.guild = guild
        self.voice_client = guild.voice_client
        self.author = type('MockAuthor', (), {
            'display_name': 'CLI Admin',
            'id': 0,
            'guild_permissions': discord.Permissions.all(),
            'voice': type('MockVoice', (), {
                'channel': guild.voice_client.channel if guild.voice_client else None
            })()
        })()
        self.bot = guild.me
        self.channel = channel
        self.message = type('MockMessage', (), {
            'guild': guild, 'author': self.author,
            'channel': channel, 'content': '', 'role_mentions': []
        })()

    async def send(self, content, **kwargs):
        if self.channel:
            try:
                return await self.channel.send(content, **kwargs)
            except Exception as e:
                print(f"[Bot Error] Failed to send message: {e}")
                return None
        else:
            print(f"[Bot] {content}")
            return None


class InteractionContext:
    def __init__(self, interaction: discord.Interaction):
        self.interaction = interaction
        self.guild = interaction.guild
        self.author = interaction.user
        self.voice_client = interaction.guild.voice_client if interaction.guild else None
        self.channel = interaction.channel
        self.message = None

    async def send(self, content, **kwargs):
        return await self.interaction.followup.send(content, **kwargs)