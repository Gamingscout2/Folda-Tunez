#!/bin/bash

# F-T CLI Discord Bot - Linux Launcher
# Version: 0.3.1
# Quick launcher for the F-T CLI Discord Bot

cd "$(dirname "$0")"  # Change to script directory

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Display header
clear
echo "==============================================="
echo "        F-T CLI DISCORD BOT LAUNCHER"
echo "==============================================="
echo
echo "Quick Access Options:"
echo
echo "[R] Run Bot Immediately"
echo "[S] Setup & Run (First Time)"
echo "[M] Open Main Menu"
echo "[X] Exit"
echo
echo "==============================================="

read -p "Choose option (R/S/M/X): " quick_choice

case $quick_choice in
    [Rr])
        clear
        echo "Starting bot now..."
        sleep 2
        
        # Check if Python script exists
        if [ ! -f "F-T_CLI_v0.3.1.py" ]; then
            echo "ERROR: F-T_CLI_v0.3.1.py not found!"
            echo "Please make sure the Python file is in the same directory."
            read -p "Press Enter to exit..."
            exit 1
        fi
        
        # Run the bot
        python3 F-T_CLI_v0.3.1.py
        ;;
    [Ss])
        clear
        echo "Starting complete setup..."
        sleep 2
        
        # Check if pre-requisites script exists
        if [ ! -f "pre-requisites.sh" ]; then
            echo "ERROR: pre-requisites.sh not found!"
            echo "Make sure pre-requisites.sh is in the same folder"
            read -p "Press Enter to exit..."
            exit 1
        fi
        
        # Make executable if needed
        if [ ! -x "pre-requisites.sh" ]; then
            chmod +x pre-requisites.sh
        fi
        
        # Run setup
        ./pre-requisites.sh
        ;;
    [Mm])
        # Check if pre-requisites script exists
        if [ -f "pre-requisites.sh" ]; then
            # Make executable if needed
            if [ ! -x "pre-requisites.sh" ]; then
                chmod +x pre-requisites.sh
            fi
            ./pre-requisites.sh
        else
            echo "ERROR: Main setup script not found"
            read -p "Press Enter to exit..."
            exit 1
        fi
        ;;
    [Xx])
        exit 0
        ;;
    *)
        echo "Invalid option. Exiting..."
        exit 1
        ;;
esac