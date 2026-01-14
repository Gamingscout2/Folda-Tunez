F-T CLI Discord Bot - Linux Edition

https://github.com/Gamingscout2/Folda-Tunez

A powerful Discord music bot with CLI administration capabilities, supporting YouTube streaming, local playlists, and advanced queue management.

Linux Quick Start

For First-Time Linux Users:
1. Download all files to a directory (e.g., ~/ft-bot)
2. Open terminal and navigate to the directory:
   cd ~/ft-bot
3. Make the setup scripts executable:
   chmod +x pre-requisites.sh launch.sh
4. Run the launcher:
   ./launch.sh
5. Choose Option S for Setup & Run (First Time)
6. Follow the prompts - the script will detect your Linux distribution or let you select it manually
7. Replace the bot token in F-T_CLI_v0.3.1.py with your own Discord bot token
8. Run the bot by choosing option R from the launcher menu

NOTE: You may view the contents of the shell scripts and the python scripts to determine your level of comfort with running this program. I provide no warranty as this is an open-source project, as stated in the license: https://sirobivan.org/pcl1-1.html.

For Returning Linux Users:
- Run launch.sh and choose Option R (Run Bot Immediately)
- OR run directly: python3 F-T_CLI_v0.3.1.py

Linux-Specific Manual

Table of Contents
1. Linux Prerequisites
2. Installation Steps for Linux
3. Linux Configuration
4. Running on Linux Systems
5. Using the CLI on Linux
6. Linux Troubleshooting
7. Linux FAQ

Linux Prerequisites

System Requirements:
- Linux distribution (Ubuntu 20.04+, Debian 10+, Fedora 32+, CentOS 8+, Arch Linux, openSUSE, or other Linux distributions)
- Python 3.8 or higher
- FFmpeg 4.0 or higher
- pip (Python package manager)
- Terminal access with sudo privileges for installation
- At least 1GB free space (2GB is recommended)

Discord Requirements (same as Windows):
1. A Discord Account
2. A Discord Server where you have admin permissions
3. A Discord Bot Token (see Configuration section below)

Linux Installation Steps

Step 1: Download Files
1. Open terminal
2. Create a directory for the bot:
   mkdir ~/ft-bot && cd ~/ft-bot
3. Download all provided files into this directory

Step 2: Run the Linux Setup
1. Make the scripts executable:
   chmod +x pre-requisites.sh launch.sh
2. Run the launcher:
   ./launch.sh
3. Choose S for Setup & Run

Step 3: Complete Auto-Setup (Option 1 in main menu)
1. The script will:
   - Detect your Linux distribution automatically
   - If auto-detection fails, it will prompt you to select your distribution manually
   - Install system packages using your package manager (apt, dnf, yum, pacman, or zypper)
   - Install Python and pip if needed
   - Install FFmpeg for audio processing
   - Install all Python dependencies
   - Create necessary directories (logs/, downloads/, config/)
   - Create configuration file

2. During installation:
   - You may be prompted for your sudo password
   - The script supports multiple Linux distributions
   - Wait patiently - This can take 5-15 minutes depending on your internet speed

Step 4: Configure Bot Token
IMPORTANT: You MUST replace the bot token!

1. Open F-T_CLI_v0.3.1.py in a text editor:
   nano F-T_CLI_v0.3.1.py
   OR
   vim F-T_CLI_v0.3.1.py
   OR
   gedit F-T_CLI_v0.3.1.py

2. Scroll to the very bottom
3. Find this line:
   bot.run('YOUR_TOKEN_HERE')
4. Replace the token inside the quotes with your own bot token:
   bot.run('eXaMpLE_t0k3N_pOoL57%_!2AGh')
5. Save the file (Ctrl+O then Ctrl+X in nano, :wq in vim, Ctrl+S in gedit)

Step 5: Run the Bot
1. Back in the launcher, choose Option R (Run Bot Immediately)
2. The bot will start and show connection status
3. Keep this terminal window open while the bot is running
4. The terminal will show:
   - Connection status
   - Command usage
   - CLI interface (FoldaTunez> prompt)
   - Use the "help" command for more information

Linux Configuration

Bot Token Setup (same as Windows):
1. Go to https://discord.com/developers/applications
2. Click "New Application" -> Name it -> Create
3. Go to "Bot" section -> Click "Add Bot" -> Yes
4. Under "TOKEN" click "Copy" (never share this!)
5. Paste it in your Python file as shown above

Bot Permissions (same as Windows):
1. In Discord Developer Portal, go to "OAuth2" -> "URL Generator"
2. Check "bot" under Scopes
3. Check these permissions:
   - General: View Channels, Send Messages, Embed Links
   - Voice: Connect, Speak, Use Voice Activity
4. Copy the generated URL and open it in browser
5. Add bot to your server

Linux Configuration Files
The setup creates these folders:
- downloads/ - Audio files from YouTube
- logs/ - Log files with timestamps
- config/ - Configuration files (edit bot_config.txt)

Linux Audio System Notes:
- The bot supports PulseAudio (default on most desktop Linux)
- For headless servers, you may need to configure audio differently
- Check config/bot_config.txt for audio driver settings

Running on Linux Systems

Method 1: Using the Launcher Script (Recommended)
./launch.sh -> Press R (Run Immediately)

Method 2: Using the Setup Script
./pre-requisites.sh -> Choose Option 2 (Run Bot Only)

Method 3: Direct Python Execution
python3 F-T_CLI_v0.3.1.py

Method 4: With Virtual Environment (if created)
source venv/bin/activate
python3 F-T_CLI_v0.3.1.py

Method 5: As a Background Service (Advanced)
For 24/7 operation, you can create a systemd service:
1. Create a service file: sudo nano /etc/systemd/system/ft-bot.service
2. Add configuration:
   [Unit]
   Description=F-T CLI Discord Bot
   After=network.target
   
   [Service]
   Type=simple
   User=yourusername
   WorkingDirectory=/path/to/ft-bot
   ExecStart=/usr/bin/python3 /path/to/ft-bot/F-T_CLI_v0.3.1.py
   Restart=always
   RestartSec=10
   
   [Install]
   WantedBy=multi-user.target
3. Enable and start the service:
   sudo systemctl enable ft-bot.service
   sudo systemctl start ft-bot.service

What to Expect When Running:
1. Terminal opens with bot status
2. "Logged in as [BotName]" appears when connected
3. CLI prompt appears: FoldaTunez>
4. Bot is now ready in your Discord server

Keeping the Bot Running on Linux:
- For temporary sessions: Keep terminal open, use Ctrl+C to stop
- For background operation: Use screen or tmux:
  screen -S ft-bot
  ./launch.sh
  Press Ctrl+A then D to detach
  screen -r ft-bot to reattach
- For permanent operation: Set up as a systemd service (see above)
- The setup script allows restarting without closing

Linux-Specific CLI Usage

All Discord commands and Admin CLI commands work the same as on Windows.

Finding Server/Channel IDs:
1. Use servers command to see all servers
2. Note the "BOT ID" (first number) for each server
3. Use channels [BOT_ID] to see channels in that server
4. Use the "BOT ID" for channels in other commands

Linux Troubleshooting

Common Linux Issues & Solutions:

Issue: "Permission denied" when running scripts
Solution:
1. Make scripts executable: chmod +x pre-requisites.sh launch.sh
2. If still issues, run with bash: bash pre-requisites.sh

Issue: "Python not found" error
Solution:
1. Run ./pre-requisites.sh -> Option 1 (Auto-Setup)
2. It will install Python automatically for your distribution
3. If manual install needed:
   Ubuntu/Debian: sudo apt-get install python3 python3-pip
   Fedora: sudo dnf install python3 python3-pip
   Arch: sudo pacman -S python python-pip
   openSUSE: sudo zypper install python3 python3-pip

Issue: "ModuleNotFoundError" (discord.py, yt-dlp, etc.)
Solution:
1. Run ./pre-requisites.sh -> Option 3 (Install Dependencies)
2. Or manually: pip3 install discord.py[voice] yt-dlp pynacl tabulate pyyaml
3. Use sudo if permission errors: sudo pip3 install ...

Issue: Bot connects but can't play audio
Solution:
1. ./pre-requisites.sh -> Option 4 (Install FFmpeg)
2. Verify: Open terminal, type ffmpeg -version
3. If not found, install manually:
   Ubuntu/Debian: sudo apt-get install ffmpeg
   Fedora: sudo dnf install ffmpeg
   Arch: sudo pacman -S ffmpeg
   openSUSE: sudo zypper install ffmpeg

Issue: "No module named 'nacl'" or PyNaCl issues
Solution:
1. Some systems need development libraries:
   Ubuntu/Debian: sudo apt-get install libffi-dev python3-dev
   Fedora: sudo dnf install libffi-devel python3-devel
   Arch: sudo pacman -S libffi python
2. Reinstall: pip3 install pynacl --force-reinstall

Issue: "4006 Voice Connection Error" on Linux
Solution:
1. This is a Discord regional server issue
2. Try changing Discord server region:
   - Server Settings -> Overview -> Region
   - Try "US East", "Europe", or "Brazil"
3. For Linux servers, ensure proper network connectivity
4. Check firewall: sudo ufw allow out 443/tcp (for HTTPS)

Issue: Bot doesn't respond to commands on Linux
Solution:
1. Check bot has proper permissions in Discord
2. Ensure bot is online (green dot in member list)
3. Verify command prefix is !
4. Check bot can see/send in the text channel
5. For Linux servers, check SELinux/AppArmor is not blocking

Issue: "Can't join voice channel" on Linux
Solution:
1. Make sure you're in a voice channel first
2. Check bot has "Connect" and "Speak" permissions
3. Try !leave then !join again
4. Restart bot completely
5. For headless Linux servers, ensure audio dummy module is loaded:
   sudo modprobe snd-dummy

Issue: Downloads folder gets too large
Solution:
1. Bot saves all played songs to downloads/
2. Manually delete files periodically
3. Or set up a cron job to clean old files:
   0 2 * * * find /path/to/ft-bot/downloads -type f -mtime +7 -delete

Linux Log Files & Debugging:

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

How to use logs for debugging on Linux:
1. Stop the bot (Ctrl+C)
2. Open latest log file in logs/ folder:
   less logs/bot_$(ls -t logs/*.log | head -1)
3. Look for "ERROR" or "CRITICAL" lines
4. Copy error message for troubleshooting
5. Or share with support (remove token first!)

Linux FAQ

Q: Can I run this 24/7 on Linux?
A: Yes, Linux is ideal for 24/7 operation. Use systemd service or screen/tmux.

Q: Which Linux distributions are supported?
A: Ubuntu, Debian, Fedora, CentOS, Arch Linux, openSUSE, and most other distributions. The script auto-detects or lets you select manually.

Q: Is YouTube downloading legal on Linux?
A: Same as Windows - for personal use with content you have rights to. Respect copyright laws.

Q: Can I add more features on Linux?
A: Yes! Edit F-T_CLI_v0.3.1.py with Python knowledge or request features.

Q: Why use these scripts instead of Docker?
A: These scripts are optimized for direct Linux installation without Docker complexity.

Q: My Linux distribution isn't auto-detected!
A: The script will prompt you to manually select from supported distributions or choose "Other" for manual installation.

Q: Can I change the command prefix on Linux?
A: Yes, edit line 89 in F-T_CLI_v0.3.1.py:
   BOT_PREFIX = "!"  # Change to "$", "?", etc.

Q: How to update the bot on Linux?
A: Replace F-T_CLI_v0.3.1.py with new version, then run dependencies install. You can either rename the new file or edit the launch.sh and pre-requisites.sh files to reflect the new version in their calls to the file.

Linux Support

Quick Help for Linux:
1. Read this README thoroughly
2. Check logs for error messages
3. Use the distribution-specific package manager commands

If Still Stuck on Linux:
1. Take screenshot of error
2. Check logs/ folder for details
3. Run: ./pre-requisites.sh -> Option 8 (System Information) and share details
4. Ask in Linux or Discord bot communities
5. Contact me via GitHub: https://github.com/Gamingscout2/

Important Linux Notes:
- Never share your bot token
- Backup your configuration if modifying
- Test in a private server first
- Regularly update dependencies: pip3 install --upgrade ...
- Check GitHub for new updates to the core project: https://github.com/Gamingscout2/Folda-Tunez
- For headless servers, you may need audio dummy drivers

Linux Performance Tips:
1. Use virtual environment for isolated dependencies
2. Consider using systemd for automatic restarts
3. Monitor disk usage in downloads/ folder
4. Use log rotation if logs get too large
5. Consider running on a VPS for 24/7 availability

Credits & License (same as Windows)

Bot by: Preston Parsons
Version: 0.3.1 (Updated 11/17/2025)
Dependencies: discord.py, yt-dlp, FFmpeg

Disclaimer: This bot is for educational purposes. Users are responsible for complying with Discord ToS and copyright laws.

Last Updated: January 2026 (quick undocumented fix in a commit)
For updates and support, check the original source repository.

Additional Linux Files:
- pre-requisites.sh: Complete setup script for Linux
- launch.sh: Quick launcher for Linux
- run_venv.sh: Virtual environment launcher (created during setup)

To make scripts executable: chmod +x *.sh