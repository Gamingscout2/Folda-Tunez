"""Process-wide mutable state shared across modules."""
import time
from collections import defaultdict
from typing import Any, Dict, Set

import discord

DATA_USAGE: Dict[int, Dict[str, Any]] = defaultdict(
    lambda: {'total_bytes': 0, 'start_time': time.time()}
)
last_join_channels: Dict[int, discord.VoiceChannel] = {}
guild_dj_roles:     Dict[int, int] = {}
vote_skips:         Dict[int, Set[int]] = defaultdict(set)
stay_247:           Dict[int, bool] = defaultdict(bool)

# Every auto-downloaded file in existence, for shutdown cleanup
ALL_DOWNLOADED_FILES: Set[str] = set()