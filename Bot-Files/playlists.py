"""Folder-based playlist storage and paginated browser view.

Each playlist is a plain .txt file inside PLAYLISTS_DIR containing one
URL per line. Because playlists store only URLs, !qload re-downloads
every track and can perfectly recreate any saved queue.
"""

import os
import re
from typing import List, Optional

import discord
from discord.ui import View, Button

from config import PLAYLISTS_DIR
from loggers import bot_logger


def _sanitize(name: str) -> str:
    """Turn a user-provided name into a safe filename."""
    cleaned = re.sub(r'[^\w\- ]', '_', name).strip()
    return cleaned[:100] or "unnamed"


def _path(name: str) -> str:
    return os.path.join(PLAYLISTS_DIR, f"{_sanitize(name)}.txt")


def list_playlists() -> List[str]:
    """Return the sorted list of saved playlist names (no extension)."""
    os.makedirs(PLAYLISTS_DIR, exist_ok=True)
    try:
        return sorted(
            f[:-4] for f in os.listdir(PLAYLISTS_DIR) if f.endswith('.txt')
        )
    except Exception as e:
        bot_logger.error(f"Failed to list playlists: {e}")
        return []


def save_playlist(name: str, urls: List[str]) -> bool:
    """Write urls to <name>.txt, one per line."""
    if not urls:
        return False
    try:
        with open(_path(name), 'w', encoding='utf-8') as f:
            f.write('\n'.join(urls))
        return True
    except Exception as e:
        bot_logger.error(f"Failed to save playlist {name}: {e}")
        return False


def load_playlist(name: str) -> Optional[List[str]]:
    """Return list of URLs, or None if the playlist does not exist."""
    path = _path(name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        bot_logger.error(f"Failed to load playlist {name}: {e}")
        return None


def delete_playlist(name: str) -> bool:
    path = _path(name)
    if not os.path.exists(path):
        return False
    try:
        os.remove(path)
        return True
    except Exception as e:
        bot_logger.error(f"Failed to delete playlist {name}: {e}")
        return False


class PlaylistBrowser(View):
    """Paginated view of available playlists (10 per page, < / > buttons)."""

    PER_PAGE = 10

    def __init__(self, ctx, playlists: List[str], page: int = 0):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.playlists = playlists
        self.page = page
        self.message = None
        self._sync_buttons()

    @property
    def total_pages(self) -> int:
        return max(1, (len(self.playlists) + self.PER_PAGE - 1) // self.PER_PAGE)

    def _sync_buttons(self):
        self.prev_btn.disabled = self.page <= 0
        self.next_btn.disabled = self.page >= self.total_pages - 1

    def format_page(self) -> str:
        start = self.page * self.PER_PAGE
        end = start + self.PER_PAGE
        lines = [
            f"**Playlists (page {self.page + 1}/{self.total_pages} - "
            f"{len(self.playlists)} total):**"
        ]
        for i, name in enumerate(self.playlists[start:end], start + 1):
            lines.append(f"`{i}.` {name}")
        lines.append("\nUse `!qload <name>` to load a playlist.")
        return "\n".join(lines)

    @discord.ui.button(label="<", style=discord.ButtonStyle.primary)
    async def prev_btn(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("Not your browser.", ephemeral=True)
            return
        if self.page > 0:
            self.page -= 1
        self._sync_buttons()
        await interaction.response.edit_message(content=self.format_page(), view=self)

    @discord.ui.button(label=">", style=discord.ButtonStyle.primary)
    async def next_btn(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("Not your browser.", ephemeral=True)
            return
        if self.page < self.total_pages - 1:
            self.page += 1
        self._sync_buttons()
        await interaction.response.edit_message(content=self.format_page(), view=self)