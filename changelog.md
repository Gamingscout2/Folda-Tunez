# Changelog

## Voice playback fix and dependency script refactor

### Fixed
- No audio after joining voice: `InteractionContext` and `MockContext` (`contexts.py`) cached
  `guild.voice_client` when created, so a bot that joined afterwards looked disconnected.
  The playback loop then tried to reconnect and failed with "Already connected to a voice
  channel." `voice_client` is now a live property on both.
- `guild_state.py`: playback now resolves the voice client from the guild at play time. A
  half-dead client gets a few seconds to recover, then is reset instead of blocking reconnects.
  Each track start is logged.
- `downloader.py`: yt-dlp's Python API ignores `~/.config/yt-dlp/config`, so the Deno path and
  `ejs:github` remote components are now passed directly. This removes the "No supported
  JavaScript runtime" warnings.

### Added
- `main.py`: startup voice check (`_check_voice_stack`) logs CRITICAL if PyNaCl or `davey`
  (Discord's DAVE voice encryption) is missing, or if ffmpeg lacks the libopus encoder. These
  cause "connects but silent". `_load_opus` also tries `ctypes.util.find_library` and aarch64 paths.
- `.gitattributes`: forces LF on `*.sh` so scripts edited on Windows still run on Linux.

### Changed
- `global_depends.sh` (run OUTSIDE the venv): refuses to run inside a venv; installs system
  packages, including Python venv/dev headers; verifies ffmpeg has libopus and libopus is
  loadable; installs Deno and writes the yt-dlp CLI config; and checks or prompts for the token.
  Falls back to `ffmpeg-free` on dnf. It no longer hardcodes `python3.14`, and a missing token no
  longer aborts the script when there is no terminal.
- `dependencies.sh` (run INSIDE the venv): uses the active venv, else an existing `venv`/`.venv`,
  else creates `venv`. Installs with `python -m pip` only after activation. Requires
  `discord.py[voice]>=2.7` (with `davey`), and verifies versions and imports. It no longer runs
  pip or the Deno installer outside the venv, and no longer writes a template `.env`.

### After updating
1. `./global_depends.sh` (outside the venv), then `./dependencies.sh`.
2. Start the bot and confirm `bot.log` shows `Voice stack OK`.
3. Restart the bot and re-run `/play`.
