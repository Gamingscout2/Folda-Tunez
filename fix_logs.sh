#!/bin/bash

# Fix log file path in F-T_CLI_v0.3.1.py

cd "$(dirname "$0")"

# Check if Python file exists
if [ ! -f "F-T_CLI_v0.3.1.py" ]; then
    echo "ERROR: F-T_CLI_v0.3.1.py not found!"
    exit 1
fi

echo "Fixing log file paths in F-T_CLI_v0.3.1.py..."
echo

# Make backup first
sudo cp F-T_CLI_v0.3.1.py F-T_CLI_v0.3.1.py.backup

# Fix the log file path in setup_logger calls
# Look for setup_logger('bot', 'bot.log') and change to setup_logger('bot', 'logs/bot.log')
sed -i "s/setup_logger('bot', 'bot.log')/setup_logger('bot', 'logs\/bot.log')/g" F-T_CLI_v0.3.1.py
sed -i 's/setup_logger("bot", "bot.log")/setup_logger("bot", "logs\/bot.log")/g' F-T_CLI_v0.3.1.py

# Also fix any other potential log file paths
sed -i "s/'bot.log'/'logs\/bot.log'/g" F-T_CLI_v0.3.1.py
sed -i 's/"bot.log"/"logs\/bot.log"/g' F-T_CLI_v0.3.1.py

echo "Checking for log file path references:"
echo "---------------------------------------"
grep -n "\.log" F-T_CLI_v0.3.1.py | head -10
echo

echo "Done! Backup saved as F-T_CLI_v0.3.1.py.backup"
