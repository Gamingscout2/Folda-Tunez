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

# Get original user (if sudo was used)
if [ -n "$SUDO_USER" ]; then
    ORIGINAL_USER="$SUDO_USER"
else
    ORIGINAL_USER=$(whoami)
fi
CURRENT_USER=$(whoami)

# Function to check if we can write to a directory
can_write() {
    [ -w "$1" ] 2>/dev/null || return 1
    return 0
}

# Function to create directories with user permissions
create_dirs_if_needed() {
    local dirs=("downloads" "logs" "config")

    echo "Checking directory permissions..."
    echo "Current directory: $(pwd)"
    echo "Current user: $CURRENT_USER"
    if [ -n "$ORIGINAL_USER" ] && [ "$ORIGINAL_USER" != "$CURRENT_USER" ]; then
        echo "Original user: $ORIGINAL_USER"
    fi
    echo

    # Check if we need to fix ownership
    if [ "$CURRENT_USER" = "root" ] && [ -n "$ORIGINAL_USER" ]; then
        echo -e "${YELLOW}Running as root. Directories will be owned by: $ORIGINAL_USER${NC}"
        echo
    fi

    for dir in "${dirs[@]}"; do
        if [ ! -d "$dir" ]; then
            echo -e "${YELLOW}Directory '$dir' doesn't exist.${NC}"

            if [ "$CURRENT_USER" = "root" ] && [ -n "$ORIGINAL_USER" ]; then
                # Running as root, create and set ownership to original user
                sudo mkdir -p "$dir"
                sudo chown "$ORIGINAL_USER:$ORIGINAL_USER" "$dir"
                echo -e "${GREEN}Created '$dir' owned by $ORIGINAL_USER${NC}"
            elif can_write "."; then
                mkdir -p "$dir" && echo -e "${GREEN}Created '$dir'${NC}"
            else
                echo -e "${RED}Cannot create '$dir' - no write permission${NC}"
                echo "Please run: sudo mkdir -p $dir && sudo chown $(whoami):$(whoami) $dir"
                return 1
            fi
        elif [ "$CURRENT_USER" = "root" ] && [ -n "$ORIGINAL_USER" ]; then
            # Check ownership and fix if needed
            current_owner=$(stat -c '%U' "$dir" 2>/dev/null || echo "unknown")
            if [ "$current_owner" != "$ORIGINAL_USER" ]; then
                echo -e "${YELLOW}Directory '$dir' owned by $current_owner, changing to $ORIGINAL_USER${NC}"
                sudo chown -R "$ORIGINAL_USER:$ORIGINAL_USER" "$dir" 2>/dev/null || true
            fi
            echo -e "${GREEN}Directory '$dir' exists and is owned by $ORIGINAL_USER${NC}"
        elif ! can_write "$dir"; then
            echo -e "${YELLOW}Warning: No write permission in '$dir'${NC}"
            echo "Please run: sudo chown -R $(whoami):$(whoami) $dir"
            return 1
        else
            echo -e "${GREEN}Directory '$dir' exists and is writable${NC}"
        fi
    done

    return 0
}

# Function to check Python packages
check_python_packages() {
    echo -e "${YELLOW}Checking Python packages...${NC}"

    # Check virtual environment first
    if [ -d "venv" ] && [ -f "venv/bin/activate" ]; then
        echo -e "${GREEN}Virtual environment found${NC}"
        return 0
    fi

    # Check if packages are installed for current user
    if python3 -c "import discord" 2>/dev/null; then
        echo -e "${GREEN}Python packages found for $CURRENT_USER${NC}"
        return 0
    fi

    # If running as root, check for original user packages
    if [ "$CURRENT_USER" = "root" ] && [ -n "$ORIGINAL_USER" ]; then
        if sudo -u "$ORIGINAL_USER" python3 -c "import discord" 2>/dev/null; then
            echo -e "${GREEN}Python packages found for $ORIGINAL_USER${NC}"
            return 0
        fi
    fi

    echo -e "${RED}Python packages not found!${NC}"
    return 1
}

# Display header
clear
echo "==============================================="
echo "        F-T CLI DISCORD BOT LAUNCHER"
echo "==============================================="
echo
echo "Current directory: $(pwd)"
echo "Current user: $CURRENT_USER"
if [ -n "$ORIGINAL_USER" ] && [ "$ORIGINAL_USER" != "$CURRENT_USER" ]; then
    echo "Original user: $ORIGINAL_USER"
fi
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

        # Check Python packages
        if ! check_python_packages; then
            echo -e "${RED}Cannot run bot - Python packages not installed${NC}"
            echo "Please run option S (Setup) first"
            read -p "Press Enter to exit..."
            exit 1
        fi

        # Check and create directories if needed
        if ! create_dirs_if_needed; then
            read -p "Press Enter to exit..."
            exit 1
        fi

        sleep 2

        # Check if Python script exists
        if [ ! -f "F-T_CLI_v0.3.1.py" ]; then
            echo "ERROR: F-T_CLI_v0.3.1.py not found!"
            echo "Please make sure the Python file is in the same directory."
            read -p "Press Enter to exit..."
            exit 1
        fi

        # Check if we can read the Python file
        if [ ! -r "F-T_CLI_v0.3.1.py" ]; then
            echo "ERROR: Cannot read F-T_CLI_v0.3.1.py!"
            echo "Please check file permissions."
            read -p "Press Enter to exit..."
            exit 1
        fi

        # Run the bot with proper user
        if [ -d "venv" ] && [ -f "venv/bin/activate" ]; then
            # Use virtual environment
            source venv/bin/activate
            python F-T_CLI_v0.3.1.py
            deactivate
        elif [ "$CURRENT_USER" = "root" ] && [ -n "$ORIGINAL_USER" ]; then
            # Ask which user to run as
            echo -e "${YELLOW}Running as root. Choose user to run bot:${NC}"
            echo "1. Run as root (system Python)"
            echo "2. Run as $ORIGINAL_USER (user Python)"
            echo
            read -p "Choose (1/2): " user_choice

            if [ "$user_choice" = "2" ]; then
                sudo -u "$ORIGINAL_USER" python3 F-T_CLI_v0.3.1.py
            else
                python3 F-T_CLI_v0.3.1.py
            fi
        else
            python3 F-T_CLI_v0.3.1.py
        fi
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
            if can_write "."; then
                chmod +x pre-requisites.sh
            else
                echo "No write permission to make script executable"
                echo "Please run: sudo chmod +x pre-requisites.sh"
                exit 1
            fi
        fi

        # Run setup
        ./pre-requisites.sh
        ;;
    [Mm])
        # Check if pre-requisites script exists
        if [ -f "pre-requisites.sh" ]; then
            # Make executable if needed
            if [ ! -x "pre-requisites.sh" ]; then
                if can_write "."; then
                    chmod +x pre-requisites.sh
                else
                    echo "No write permission to make script executable"
                    echo "Please run: sudo chmod +x pre-requisites.sh"
                    exit 1
                fi
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
