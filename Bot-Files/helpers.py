"""Permission checks and file-deletion helpers."""
import os

import discord

from loggers import bot_logger
from runtime import ALL_DOWNLOADED_FILES, guild_dj_roles


def delete_song_file(song: dict) -> None:
    """Delete a song's backing file if it was auto-downloaded (never local user files)."""
    if song.get('source') != 'download':
        return
    path = song.get('url')
    if not path:
        return
    try:
        if os.path.exists(path):
            os.remove(path)
            bot_logger.info(f"Deleted download: {path}")
        ALL_DOWNLOADED_FILES.discard(path)
    except Exception as e:
        bot_logger.error(f"Failed to delete {path}: {e}")


def is_dj(ctx, guild_id: int) -> bool:
    """Return True if the caller has DJ privileges for this guild."""
    author = getattr(ctx, 'author', None)
    if author is None or not isinstance(author, discord.Member):
        return True  # DMs / mocks
    if author.guild_permissions.administrator or author.guild_permissions.manage_guild:
        return True
    role_id = guild_dj_roles.get(guild_id)
    if not role_id:
        return True  # no DJ role set -> everyone is DJ (backwards compatible)
    dj_role = ctx.guild.get_role(role_id) if getattr(ctx, 'guild', None) else None
    return dj_role is not None and dj_role in author.roles


def is_admin(ctx) -> bool:
    author = getattr(ctx, 'author', None)
    return isinstance(author, discord.Member) and author.guild_permissions.administrator