"""Hyperthreaded audio downloader and YouTube search helper."""
import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

import yt_dlp as youtube_dl

from config import DOWNLOADS_DIR, DOWNLOAD_TIMEOUT, MAX_CONCURRENT_DL, MAX_PLAYLIST_ITEMS, SUPPORTED_AUDIO_EXTENSIONS
from guild_state import GuildState
from loggers import bot_logger, yt_logger
from runtime import ALL_DOWNLOADED_FILES


class Downloader:
    """Hyperthreaded audio downloader with yt-dlp."""

    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_DL, thread_name_prefix='dl')
        self.ydl_opts_base = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(DOWNLOADS_DIR, '%(title).150B [%(id)s].%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'socket_timeout': DOWNLOAD_TIMEOUT,
            'retries': 3,
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'logger': yt_logger,
        }

    async def extract_info(self, url: str, download: bool = False, process: bool = True) -> dict:
        opts = self.ydl_opts_base.copy()
        if not download:
            opts['extract_flat'] = 'in_playlist'

        def _extract():
            with youtube_dl.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=download, process=process)

        return await asyncio.get_event_loop().run_in_executor(self.executor, _extract)

    async def download_single(self, url: str) -> Optional[Dict[str, Any]]:
        try:
            info = await self.extract_info(url, download=True)
            if not info:
                return None
            filepath = youtube_dl.YoutubeDL(self.ydl_opts_base).prepare_filename(info)
            base = os.path.splitext(filepath)[0]
            for ext in SUPPORTED_AUDIO_EXTENSIONS:
                test = base + ext
                if os.path.exists(test):
                    filepath = test
                    break
            abs_path = os.path.abspath(filepath)
            ALL_DOWNLOADED_FILES.add(abs_path)
            return {
                'title': info.get('title', 'Unknown Track'),
                'url': abs_path,
                'webpage_url': info.get('webpage_url', url),
                'duration': info.get('duration', 0),
                'source': 'download',
            }
        except Exception as e:
            bot_logger.error(f"Download failed for {url}: {e}")
            return None

    async def download_playlist_batch(
        self, entries: List[Dict], requester: str,
        progress_callback=None, state: Optional[GuildState] = None,
    ) -> List[Dict]:
        """Hyperthreaded playlist download with semaphore control."""
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_DL)
        capped = entries[:MAX_PLAYLIST_ITEMS]

        async def download_one(entry):
            async with semaphore:
                video_url = (entry.get('webpage_url')
                             or entry.get('url')
                             or f"https://youtu.be/{entry['id']}")
                song = await self.download_single(video_url)
                if song:
                    song['requester'] = requester
                    if state is not None:
                        state.downloaded_files.add(song['url'])
                    if progress_callback:
                        try:
                            await progress_callback(song)
                        except Exception:
                            pass
                return song

        tasks = [download_one(e) for e in capped if e]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if isinstance(r, dict)]


downloader = Downloader()


async def search_youtube(query: str, limit: int = 5) -> List[dict]:
    """Robust YouTube search returning validated entries."""
    query = query.strip()
    if not query or len(query) > 200:
        return []
    try:
        info = await downloader.extract_info(f"ytsearch{limit}:{query}", download=False)
        if not info or 'entries' not in info:
            return []
        return [e for e in info['entries']
                if e and e.get('id') and e.get('title')]
    except Exception as e:
        bot_logger.error(f"Search failed for '{query}': {e}")
        return []