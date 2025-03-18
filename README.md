# Folda-Tunez
The Python implementation of my new discord bot, Folda Tunez which has the ability to play audio from your local machine or stream the audio from a link!
Folda Tunez Discord Bot
by Preston Parsons
01/07/2024

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
Copyright 2025 Preston Parsons and Parsons Computing 
