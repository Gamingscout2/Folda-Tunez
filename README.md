# Folda Tunez

**Current version: v0.5.3**

A Discord music bot written in Python. It streams audio from YouTube (and other yt-dlp sources),
plays local files, and ships with an interactive admin console for running the bot from the
terminal.

by Phaedra Parsons

See [changelog.md](changelog.md) for what changed in each release.

## What's in v0.5.3

- Fixes the "bot joins voice but is silent" problem (the voice encryption library `davey` is now
  pinned below 0.2, matching the legacy build that worked).
- New `requirements.txt` plus rebuilt `dependencies.sh` / `global_depends.sh`, with forced
  reinstall and an end-to-end audio self-test.
- Admin console: command history (Up/Down), Tab completion, guilds addressable by number, id or
  name, and right-click-drag copy.
- Startup voice checks and `FOLDA_DEBUG_VOICE=1` voice debugging.

## Requirements

- Linux (the install scripts support Debian/Ubuntu, Fedora/RHEL, Arch, openSUSE and Alpine)
- Python 3.10 or newer (tested on 3.14)
- A Discord bot token
- ffmpeg **with the libopus encoder**, libopus, libsodium (installed by `global_depends.sh`)

## Install

Run both scripts from `Bot-Files/`, in this order:

```bash
cd Bot-Files
chmod +x global_depends.sh dependencies.sh

./global_depends.sh        # 1. system packages, Deno, yt-dlp config, .env token. Run OUTSIDE the venv.
./dependencies.sh          # 2. Python packages in ./venv, then an audio self-test.
```

- `global_depends.sh` needs sudo for system packages. Run it as your normal user, not as root.
  It prompts for `DISCORD_BOT_TOKEN` if `.env` has none. `--force` reinstalls system packages.
- `dependencies.sh` uses the active venv, else `./venv` / `./.venv`, else creates `./venv`. It
  force-reinstalls everything in `requirements.txt` and ends with an audio self-test. Every line
  must show `[ OK ]` before you start the bot.
  - `./dependencies.sh --recreate` deletes and rebuilds the venv (use this if audio is silent)
  - `./dependencies.sh --no-force` does a normal upgrade instead of a forced reinstall

Do not install `davey` 0.2 or newer by hand. discord.py 2.7.x is not compatible with it and voice
will be completely silent.

## Run

```bash
cd Bot-Files
source venv/bin/activate
python main.py
```

On startup check `bot.log` for:

```
Loaded libopus from '...'
Voice stack OK (discord.py 2.7.1, ffmpeg libopus present)
```

Any `CRITICAL` line there names the missing piece of the voice pipeline and how to fix it.

## Configuration (`.env` in `Bot-Files/`)

| Variable | Default | Purpose |
|---|---|---|
| `DISCORD_BOT_TOKEN` | required | Bot token from the Discord Developer Portal |
| `FFMPEG_PATH` | `ffmpeg` | Path to the ffmpeg binary |
| `MAX_CONCURRENT_DOWNLOADS` | `8` | Parallel downloads |
| `DOWNLOAD_TIMEOUT` | `300` | Download socket timeout (seconds) |
| `VOICE_TIMEOUT` | `60` | Voice connect timeout (seconds) |
| `MAX_PLAYLIST_ITEMS` | `200` | Max tracks taken from a playlist |
| `DOWNLOADS_DIR` | `downloads` | Where tracks are downloaded |
| `PLAYLISTS_DIR` | `playlists` | Saved playlists |
| `FOLDA_HISTORY_FILE` | `Bot-Files/botbash.history` | Console command history file |
| `FOLDA_DEBUG_VOICE` | unset | Set to `1` for voice debug lines in `bot.log` |

The bot needs the **Connect** and **Speak** permissions in the voice channel, and the Message
Content, Server Members and Voice States intents enabled in the Developer Portal.

## Discord commands

Prefix `!` (also `/play /skip /pause /resume /np /queue /filter`). Send `!help` in Discord for the
full list.

| Area | Commands |
|---|---|
| Playback | `join`, `leave`, `play <query\|url>` (`stream`), `playnext`, `pause`, `resume`, `skip`, `voteskip`, `stop`, `loop` |
| Queue | `queue`, `np`, `remove`, `move`, `swap`, `jump`, `shuffle`, `clear` |
| Playlists | `qlist <name>`, `qload <name>`, `qsearch`, `deleteplaylist <name>` |
| Audio | `filter [name]`: bassboost, bassboost_high, nightcore, vaporwave, 8d, treble, normalize, none |
| Config | `dj set @Role`, `247 on\|off` |
| Info/Admin | `usage`, `cleanup`, `playlist_local <file>`, `shutdown`, `help` |

## Admin console

The terminal running the bot is an interactive console (type `help` for all commands, e.g.
`servers`, `guildinfo`, `stream`, `skip`, `guildlog`).

- **`<guild>` can be the bot id, the real guild id, or the name.** Names are case-insensitive and
  accept a unique prefix. Quote names with spaces: `skip "My Server"`.
- **Tab** completes commands, guild names/ids, filters and status types.
- **Up / Down** walk through command history, saved in `Bot-Files/botbash.history` (created
  automatically, git-ignored).
- **Mouse wheel / PageUp / PageDown** scroll the log. `Ctrl+Home` / `Ctrl+End` jump to top/bottom.
- **Hold the right mouse button and drag** over the log to copy text to the clipboard. A plain
  right click copies the whole visible log. This uses the OSC 52 clipboard escape (Windows
  Terminal, iTerm2, kitty, WezTerm, tmux) and `wl-copy`/`xclip`/`xsel`/`pbcopy` if installed.
  Hold Shift while dragging to use your terminal's own selection instead.

## Troubleshooting: bot joins but there is no audio

1. Re-run `./dependencies.sh --recreate`. Every self-test line must be `[ OK ]`.
2. Check `bot.log` for `CRITICAL` lines after startup (missing PyNaCl/`davey`, `davey` 0.2+,
   ffmpeg without libopus, libopus not loadable).
3. Check the bot has the **Speak** permission and is not server-muted or suppressed. The bot warns
   in chat when it detects this.
4. Run with `FOLDA_DEBUG_VOICE=1 python main.py` and read the voice lines in `bot.log`.

## Project layout

```
Bot-Files/
  main.py            Entry point: bot setup, events, slash commands, startup voice checks
  config.py          Env vars, constants, DOWNLOADS_DIR / PLAYLISTS_DIR bootstrap
  loggers.py         bot / cli / yt-dlp rotating file loggers
  runtime.py         Shared mutable state (usage, votes, DJ roles, 24/7)
  audio.py           SONG_FILTERS, TrackedFFmpegPCMAudio (ffmpeg -> PCM -> libopus)
  guild_state.py     Per-guild queue and playback loop
  contexts.py        MockContext (CLI) and InteractionContext (slash commands)
  downloader.py      yt-dlp downloader and YouTube search
  music.py           Music cog (all Discord commands)
  search_view.py     Search result picker UI
  playlists.py       Saved playlists
  persistence.py     Playlist save/load
  helpers.py         DJ/admin checks, file cleanup
  admin_cli.py       Admin console commands
  console.py         Split-screen terminal, history, completion, mouse copy
  requirements.txt   Pinned Python dependencies
  dependencies.sh    Python dependency installer + audio self-test (venv)
  global_depends.sh  System dependency installer (outside the venv)
```

## Version history

- **v0.5.3**: voice fix (`davey` pin), pinned requirements, rebuilt install scripts, admin console
  history / completion / copy. See [changelog.md](changelog.md).
- **v0.5.2**: legacy build kept in `old/` for emergency reference (token via env var, DJ roles,
  vote skip, audio filters, 24/7 mode, saved playlists, slash commands).
- **v2.4 (03/18/2025)**: logging system (`bot.log`, `cli.log`, 5 MB rotation, 3 backups), `!leave`
  command restored, CLI operations logged.

## License

Subject to the license terms found at: https://sirobivan.org/pcl1-1.html

Copyright 2025 Phaedra Parsons
