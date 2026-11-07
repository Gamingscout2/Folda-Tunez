# Changelog

## v0.5.3 (current)

Fixes the "bot joins voice but nothing is audible" problem, rebuilds the dependency scripts around
a pinned `requirements.txt`, and upgrades the admin console. Upgrading an existing install:

```bash
deactivate 2>/dev/null
cd Bot-Files
./global_depends.sh          # outside the venv; add --force to reinstall system packages
./dependencies.sh --recreate # rebuilds the venv and runs the audio self-test
```

### Fixed: no audio

- **Root cause: `davey 0.2.0`.** The installer left `davey` (Discord's DAVE voice end-to-end
  encryption library) unpinned, so it pulled 0.2.0, a breaking release. discord.py 2.7.x still
  uses the 0.1.x API (`process_welcome(msg)`, no `prepare_transition`/`execute_transition`), so
  the encryption key never became usable. The bot connected, ffmpeg ran and the log looked
  healthy, but Discord received nothing it could play. The legacy build (`old/`) worked because
  its venv had `davey 0.1.7`, `PyNaCl 1.6.2` and `discord.py 2.7.1`. `requirements.txt` now pins
  `davey>=0.1.7,<0.2` and resolves to those same versions.
- **Stale voice client.** `InteractionContext` and `MockContext` (`contexts.py`) copied
  `guild.voice_client` when created, so a bot that joined afterwards looked disconnected. The
  playback loop then tried to reconnect and failed with "Already connected to a voice channel".
  `voice_client` is now a live property on both. `guild_state.py` resolves the client from the
  guild at play time; a half-dead client gets a few seconds to recover, then is reset.
- **Audio source back to PCM.** `audio.py` `TrackedFFmpegPCMAudio` is `discord.FFmpegPCMAudio`
  again (as in the legacy build): ffmpeg emits raw PCM and discord.py encodes it with libopus.
  An `FFmpegOpusAudio` pass-through had been introduced earlier and was silent on the server.
  Filters (`-af`) and per-guild byte tracking still work.
- **yt-dlp JavaScript runtime.** yt-dlp's Python API ignores `~/.config/yt-dlp/config`, so
  `downloader.py` now passes the Deno path and `ejs:github` remote components directly. This
  removes the "No supported JavaScript runtime" warnings and failed signature solving.

### Added: voice safety nets and diagnostics

- Startup voice check (`main.py`, `_check_voice_stack`) logs CRITICAL if PyNaCl or `davey` is
  missing, if `davey` is 0.2 or newer, or if ffmpeg lacks the libopus encoder. It logs
  `Voice stack OK` when everything is fine.
- `_load_opus` also tries `ctypes.util.find_library` and aarch64 library paths.
- Before each track the bot warns in the log and in chat if it lacks the Speak permission, is
  server-muted, or is suppressed in a stage channel (the connection works but nobody hears it).
- `bot.log` records each track start, and when it ends with the duration and any error.
- `FOLDA_DEBUG_VOICE=1` writes discord.py voice/player debug lines to `bot.log` (gateway
  logging is excluded because its debug output contains secrets).

### Changed: dependency scripts

- **`requirements.txt` (new)**: single source of truth for Python packages. `davey` must stay
  below 0.2 until discord.py supports it.
- **`dependencies.sh`** (run inside/with the venv):
  - uses the active venv, else an existing `venv` / `.venv`, else creates `venv`; only `python -m pip`
    after activation (no more pip or Deno installs outside the venv)
  - force-reinstalls every package from `requirements.txt` (`--force-reinstall --no-cache-dir`) on
    every run, then runs `pip check` and lists the installed versions
  - `--recreate` deletes and rebuilds the venv (only if it has a `pyvenv.cfg`); `--no-force` does
    a normal upgrade instead; refuses `--recreate` while the venv is active
  - ends with an audio self-test that exits non-zero on failure: version checks (rejects
    `davey>=0.2`), a DAVE session and key package, libopus load and encode, and
    ffmpeg -> PCM -> libopus on a generated tone
- **`global_depends.sh`** (run outside the venv):
  - refuses to run inside a venv; installs system packages (ffmpeg, libopus, libsodium, libffi,
    Python venv and dev headers, build tools) for apt, dnf, pacman, zypper and apk
  - verifies ffmpeg has the libopus encoder and libopus is loadable
  - installs Deno and writes the yt-dlp CLI config; checks or prompts for `DISCORD_BOT_TOKEN`
    without aborting when there is no terminal
  - falls back to `ffmpeg-free` on dnf; no longer hardcodes `python3.14`
  - `--force` reinstalls system packages (apt `--reinstall`, dnf `reinstall`, pacman without `--needed`)
- `.gitattributes` forces LF on `*.sh` so scripts edited on Windows still run on Linux.

### Added: CLI console

- **History:** Up/Down arrows walk through command history, saved in `Bot-Files/botbash.history`
  (created by the bot on first start with mode 600, capped at 1000 entries, git-ignored).
  Override the path with `FOLDA_HISTORY_FILE`.
- **Tab completion:** command names, guilds, `filter` names, `status` types and `guildlog`
  subcommands. Several matches extend the common prefix, then list the options.
- **Guild lookup:** `<guild>` accepts the bot id, the real guild id, or the guild name
  (case-insensitive, exact or unique prefix; quote names with spaces, e.g. `"My Server"`; unquoted
  full names also work). Ambiguous names print the matches instead of guessing, and a mistyped
  guild now prints an error instead of failing silently.
- **Right-click copy:** hold the right mouse button and drag over the log area to select text; on
  release it is copied to the clipboard. A right click without dragging copies everything
  visible. Uses OSC 52 (Windows Terminal, iTerm2, kitty, WezTerm, tmux, ...) plus
  `wl-copy`/`xclip`/`xsel`/`pbcopy` when installed. Shift+drag still uses the terminal's own selection.
- The escape-sequence reader now reads one sequence at a time, so fast mouse drags no longer
  swallow arrow keys.

### Repository

- `.gitignore`: added `old/`, `old.py`, `botbash.history`, `__pycache__/` and `*.py[cod]`;
  tracked `__pycache__` files were removed from the index.
