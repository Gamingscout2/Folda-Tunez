"""Configuration constants and environment bootstrap."""
import os
from dotenv import load_dotenv
 
load_dotenv()

TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if not TOKEN:
    raise ValueError(
        "No Discord bot token found. Set DISCORD_BOT_TOKEN environment variable. "
        "If you ever committed a token to source control, revoke it in the "
        "Developer Portal -> Bot -> Reset Token."
    )

BOT_PREFIX          = "!"
FFMPEG_PATH         = os.getenv('FFMPEG_PATH', "ffmpeg")
MAX_CONCURRENT_DL   = int(os.getenv('MAX_CONCURRENT_DOWNLOADS', '8'))
DOWNLOAD_TIMEOUT    = int(os.getenv('DOWNLOAD_TIMEOUT', '300'))
VOICE_TIMEOUT       = int(os.getenv('VOICE_TIMEOUT', '60'))
MAX_PLAYLIST_ITEMS  = int(os.getenv('MAX_PLAYLIST_ITEMS', '200'))
DOWNLOADS_DIR       = os.getenv('DOWNLOADS_DIR', 'downloads')
PLAYLISTS_FILE      = os.getenv('PLAYLISTS_FILE', 'playlists.json')

os.makedirs(DOWNLOADS_DIR, exist_ok=True)

SUPPORTED_AUDIO_EXTENSIONS = {'.mp3', '.m4a', '.mp4', '.wav', '.flac', '.ogg', '.aac', '.webm'}