"""Saved-playlist JSON persistence."""
import json
import os

from config import PLAYLISTS_FILE
from loggers import bot_logger


def save_playlists(data: dict) -> None:
    try:
        with open(PLAYLISTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        bot_logger.error(f"Failed to save playlists: {e}")


def load_playlists() -> dict:
    if not os.path.exists(PLAYLISTS_FILE):
        return {}
    try:
        with open(PLAYLISTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        bot_logger.error(f"Failed to load playlists: {e}")
        return {}