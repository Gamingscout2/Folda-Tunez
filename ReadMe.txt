F-T CLI Discord Bot

https://github.com/Gamingscout2/Folda-Tunez

A powerful Discord music bot with CLI administration capabilities, supporting YouTube streaming, local playlists, and advanced queue management.

Quick Start

For First-Time Users:
1. Download all files to a folder on your computer (Preferably not just your downloads folder)
2. Run pre-requisites.bat (double-click it)
3. Choose Option 1 for Complete Auto-Setup
4. Follow the prompts - the script will install everything automatically
5. Replace the bot token in F-T_CLI_v0.3.1.py with your own Discord bot token
6. Run the bot by choosing option 2 from the main menu

NOTE:  You may view the contents of the batch scripts and the python scripts to determine your level of comfort with running this program.  I provide no warranty as this is an open-source project, as stated in the license: https://sirobivan.org/pcl1-1.html .  

For Returning Users:
- Run launch.bat and choose Option 2 (Run Bot Only)
- OR Run launch.bat for a quick menu

Detailed Manual

Table of Contents
1. Prerequisites
2. Installation Steps
3. Configuration
4. Running the Bot
5. Using the CLI
6. Troubleshooting
7. FAQ

Prerequisites

System Requirements:
- Windows 10/11 (64-bit)
- Administrator rights (for installing Python/FFmpeg)
- Internet connection (for downloading dependencies)
- At least 500MB free space (2GB is recommended)

Discord Requirements:
1. A Discord Account
2. A Discord Server where you have admin permissions
3. A Discord Bot Token (see Configuration section below)

Installation Steps

Step 1: Download Files
1. Create a new folder on your desktop called F-T_Bot
2. Download all provided files into this folder:
   - F-T_CLI_v0.3.1.py (main bot script)
   - pre-requisites.bat (main setup script)
   - launch.bat (optional quick launcher)

Step 2: Run the Setup
1. Double-click launch.bat
2. If Windows shows a security warning, click "More info" -> "Run anyway"
3. The terminal window will open with a colorful menu

Step 3: Complete Auto-Setup (Option 1)
1. Type 1 and press Enter
2. The script will:
   - Check/Install Python 3.11
   - Install FFmpeg (for audio processing)
   - Install all Python dependencies
   - Create necessary folders (logs/, downloads/, config/)
   - Create configuration file

3. During Python installation (if needed):
   - Check "Add Python to PATH"
   - Click "Install Now"
   - Wait for completion

4. Wait patiently - This can take 5-15 minutes depending on your internet speed

Step 4: Configure Bot Token
IMPORTANT: You MUST replace the bot token!

1. Open F-T_CLI_v0.3.1.py in Notepad or any text editor
2. Scroll to the very bottom (line 1773, Boston Tea Party)
3. Find this line:
   bot.run('YOUR_TOKEN_HERE')
4. Replace the token inside the quotes with your own bot token:
   bot.run('eXaMpLE_t0k3N_pOoL57%_!2AGh')
5. Save the file (ctrl + s)

Step 5: Run the Bot
1. Back in the setup script, choose Option 2 (Run Bot Only)
2. The bot will start and show connection status
3. Keep this window open while the bot is running
4. The terminal will show:
   - Connection status
   - Command usage
   - CLI interface (FoldaTunez> prompt)
   - Use the "help" command for more information

Configuration

Bot Token Setup
1. Go to https://discord.com/developers/applications
2. Click "New Application" -> Name it -> Create
3. Go to "Bot" section -> Click "Add Bot" -> Yes
4. Under "TOKEN" click "Copy" (never share this!)
5. Paste it in your Python file as shown above

Bot Permissions
1. In Discord Developer Portal, go to "OAuth2" -> "URL Generator"
2. Check "bot" under Scopes
3. Check these permissions:
   - General: View Channels, Send Messages, Embed Links
   - Voice: Connect, Speak, Use Voice Activity
4. Copy the generated URL and open it in browser
5. Add bot to your server

Configuration Files
The setup creates these folders:
- downloads/ - Audio files from YouTube
- logs/ - Log files with timestamps
- config/ - Configuration files (edit bot_config.txt)

Running the Bot

Method 1: Using the Setup Script (Recommended)
Double-click pre-requisites.bat -> Choose Option 2

Method 2: Quick Launcher
Double-click launch.bat -> Press R (Run Immediately)

Method 3: Manual Python
Open Command Prompt in the folder and run:
python F-T_CLI_v0.3.1.py

What to Expect When Running:
1. Terminal opens with bot status
2. "Logged in as [BotName]" appears when connected
3. CLI prompt appears: FoldaTunez>
4. Bot is now ready in your Discord server

Keeping the Bot Running:
- DO NOT close the terminal window
- Minimize it if needed
- Use Ctrl+C to stop the bot gracefully
- The setup script allows restarting without closing

Using the CLI

Discord Commands (Users)
Users can use these commands in Discord text channels:

Command: !join
Description: Join voice channel
Example: !join

Command: !stream [URL]
Description: Stream from YouTube
Example: !stream https://youtube.com/...

Command: !stream [search]
Description: Search YouTube
Example: !stream never gonna give you up

Command: !queue
Description: Show current queue
Example: !queue

Command: !skip
Description: Skip current song
Example: !skip

Command: !pause
Description: Pause playback
Example: !pause

Command: !resume
Description: Resume playback
Example: !resume

Command: !loop
Description: Toggle loop mode
Example: !loop

Command: !shuffle
Description: Shuffle queue
Example: !shuffle

Command: !clear
Description: Clear queue
Example: !clear

Command: !leave
Description: Leave voice channel
Example: !leave

Command: !help
Description: Show all commands
Example: !help

Admin CLI Commands
In the terminal window (FoldaTunez> prompt):

Command: servers
Description: List all servers
Example: servers

Command: channels [ID]
Description: List channels in server
Example: channels 1

Command: join [ID] [ID]
Description: Join voice channel
Example: join 1 3

Command: stream [ID] [URL]
Description: Stream in server
Example: stream 1 https://...

Command: sendmsg [ID] [ID] [msg]
Description: Send message
Example: sendmsg 1 2 Hello!

Command: clear [ID]
Description: Clear queue in server
Example: clear 1

Command: leave [ID]
Description: Leave voice in server
Example: leave 1

Command: queue [ID] [ID]
Description: Send queue to channel
Example: queue 1 2

Command: exit
Description: Exit CLI (bot keeps running)
Example: exit

Command: kill
Description: Shutdown bot completely
Example: kill

Finding Server/Channel IDs:
1. Use servers command to see all servers
2. Note the "BOT ID" (first number) for each server
3. Use channels [BOT_ID] to see channels in that server
4. Use the "BOT ID" for channels in other commands

Troubleshooting

Common Issues & Solutions:

Issue: "Python not found" error
Solution:
1. Run pre-requisites.bat -> Option 1 (Auto-Setup)
2. It will install Python automatically
3. If manual install needed: https://python.org/downloads

Issue: "ModuleNotFoundError" (discord.py, yt-dlp, etc.)
Solution:
1. Run pre-requisites.bat -> Option 3 (Install Dependencies)
2. Or manually: pip install discord.py[voice] yt-dlp pynacl tabulate pyyaml
3. Run as Administrator if permission errors

Issue: Bot connects but can't play audio
Solution:
1. pre-requisites.bat -> Option 4 (Install FFmpeg)
2. Verify: Open CMD, type ffmpeg -version
3. If not found, download manually: https://ffmpeg.org
4. Extract to C:\ffmpeg\bin and add to PATH

Issue: "4006 Voice Connection Error"
Solution:
1. This is a Discord regional server issue
2. Try changing Discord server region:
   - Server Settings -> Overview -> Region
   - Try "US East", "Europe", or "Brazil"
3. Wait 5 minutes and restart bot

Issue: Bot doesn't respond to commands
Solution:
1. Check bot has proper permissions in Discord
2. Ensure bot is online (green dot in member list)
3. Verify command prefix is !
4. Check bot can see/send in the text channel

Issue: "Can't join voice channel"
Solution:
1. Make sure you're in a voice channel first
2. Check bot has "Connect" and "Speak" permissions
3. Try !leave then !join again
4. Restart bot completely

Issue: Downloads folder gets too large
Solution:
1. Bot saves all played songs to downloads/
2. Manually delete files periodically
3. Or set up a scheduled task to clean old files

Log Files & Debugging:

Where to find logs:
- logs/ folder in bot directory
- Files named: bot_YYYY-MM-DD_HH-MM-SS.log
- bot.log and cli.log (main logs)

What logs contain:
- Bot startup/shutdown times
- Command executions
- Voice connection status
- Download progress
- Error messages with tracebacks

How to use logs for debugging:
1. Stop the bot (Ctrl+C)
2. Open latest log file in logs/ folder
3. Look for "ERROR" or "CRITICAL" lines
4. Copy error message for troubleshooting
5. Or share with support (remove token first!)

FAQ

Q: Can I run this 24/7?
A: Yes, but you need a dedicated computer or VPS. The terminal must stay open.

Q: How many servers can it handle?
A: Unlimited, but performance depends on your computer. Each server gets its own queue.

Q: Is YouTube downloading legal?
A: For personal use with content you have rights to. Respect copyright laws.

Q: Can I add more features?
A: Yes! Edit F-T_CLI_v0.3.1.py with Python knowledge or request features.

Q: Why not use Docker/Containers?
A: This setup is optimized for Windows users. Docker versions may become available.

Q: My antivirus flagged the .bat files!
A: They're safe batch scripts. Add exception or check file contents yourself.  If I made a mistake, please point it out on GitHub and I will correct it with crediting                       
   the person that catches it.

Q: Can I change the command prefix?
A: Yes, edit line 89 in F-T_CLI_v0.3.1.py:
   BOT_PREFIX = "!"  # Change to "$", "?", etc.

Q: How to update the bot?
A: Replace F-T_CLI_v0.3.1.py with new version, then run dependencies install.  You can either rename the new file (i.e "F-T_CLI_v.0.3.2.py" --> "F-T_CLI_v.0.3.1.py") or     
   you can edit the launch.bat file and pre-requisites.bat file to reflect the new version in their calls to the file.

Support

Quick Help:
1. Read this README thoroughly
2. Check logs for error messages
3. Google error messages or try running pre-requisites.py again, checking the terminal output for errors.

If Still Stuck:
1. Take screenshot of error
2. Check logs / folder for details
3. Ask in Discord bot communities
4. Contact me via GitHub: https://github.com/Gamingscout2/

Important Notes:
- Never share your bot token
- Backup your configuration if modifying
- Test in a private server first
- Regularly update dependencies: pip install --upgrade ...
- Check GitHub for new updates to the core project: https://github.com/Gamingscout2/Folda-Tunez

Credits & License

Bot by: Preston Parsons
Version: 0.3.1 (Updated 11/17/2025)
Dependencies: discord.py, yt-dlp, FFmpeg

Disclaimer: This bot is for educational purposes. Users are responsible for complying with Discord ToS and copyright laws.

Last Updated: January 2026 (quick undocumented fix in a commit)
For updates and support, check the original source repository.