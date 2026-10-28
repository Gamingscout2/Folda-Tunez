# Folda-Tunez
The Python implementation of my new discord bot, Folda Tunez which has the ability to play audio from your local machine or stream the audio from a link!
Folda Tunez Discord Bot
by Phaedra Parsons
01/07/2024

File structure:
folda_tunez/
-- config.py           # Env vars, constants, DOWNLOADS_DIR bootstrap
-- loggers.py          # setup_logger, bot/cli/yt loggers
-- runtime.py          # Global mutable state dicts (usage, votes, DJ roles, etc.)
-- audio.py            # SONG_FILTERS, TrackedFFmpegPCMAudio
-- persistence.py      # save_playlists / load_playlists
-- helpers.py          # is_dj, is_admin, delete_song_file
-- guild_state.py      # GuildState, get_guild_state, rebuild_queue, cleanup_all_downloads
-- contexts.py         # MockContext, InteractionContext
-- downloader.py       # Downloader, downloader instance, search_youtube
-- search_view.py      # SearchView
-- music.py            # Music cog
-- admin_cli.py        # AdminCLI
-- main.py             # Bot setup, events, slash commands, entry point


Version 2.4 Updated 03/18/2025
    Added a comprehensive logging system with:
        Separate log files for bot (bot.log) and CLI (cli.log) (not every CLI command is logged yet)
        Log rotation (5MB per file, 3 backups)
        Both console and file logging
        Standardized log format with timestamps
    Added the !leave command back in:
        Disconnects from voice
        Clears the queue
        Resets playback state
        Provides user feedback
    Added extensive logging throughout:
        Command invocations
        Critical operations
        Errors and exceptions
        System events
    Modified CLI to log all operations
        The logging system will track:
             All user commands with user/server info
        System operations (voice connections, queue changes)
        Errors with full tracebacks
        CLI command execution
        Resource usage (voice client connections, memory)
        Playback status changes
    Logs can be found in:
        bot.log: All bot-related activity\
        cli.log: All CLI interactions and admin commands


Subject to the license terms found at: https://sirobivan.org/pcl1-1.html
Copyright 2025 Phaedra Parsons
