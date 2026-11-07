"""FFmpeg audio source with data-usage tracking, plus available filters."""

from typing import Dict, Optional

import discord

from config import FFMPEG_PATH
from runtime import DATA_USAGE


SONG_FILTERS: Dict[str, Optional[str]] = {
    'none':          None,
    'bassboost':     'bass=g=15',
    'bassboost_high':'bass=g=20',
    'nightcore':     'asetrate=48000*1.25,aresample=48000,atempo=1.06',
    'vaporwave':     'asetrate=48000*0.8,aresample=48000,atempo=0.9',
    '8d':            'apulsator=hz=0.08',
    'treble':        'treble=g=5',
    'normalize':     'loudnorm=I=-16:TP=-1.5:LRA=11',
}


class TrackedFFmpegPCMAudio(discord.FFmpegOpusAudio):
    """Opus-encoded FFmpeg source with per-guild byte tracking.

    Inherits from FFmpegOpusAudio (not FFmpegPCMAudio) so ffmpeg encodes
    audio in the format Discord's voice channel actually uses. This avoids
    the "ffmpeg process has not terminated" warning on skip/stop and cuts
    CPU/memory usage per stream.

    The class name is kept identical to the previous PCM version so no
    changes are needed in music.py or guild_state.py.
    """

    def __init__(self, source, guild_id, filter_name: Optional[str] = None, **kwargs):
        options = "-loglevel warning -analyzeduration 0 -bufsize 2048k"
        if filter_name and filter_name in SONG_FILTERS:
            fs = SONG_FILTERS[filter_name]
            if fs:
                options += f' -af "{fs}"'
        super().__init__(
            source,
            executable=FFMPEG_PATH,
            options=options,
            bitrate=192,
            **kwargs,
        )
        self.guild_id = guild_id

    def read(self):
        data = super().read()
        if data:
            DATA_USAGE[self.guild_id]['total_bytes'] += len(data)
        return data