#!/bin/bash

# F-T CLI Discord Bot - Linux Complete Setup & Runner
# Version: 0.3.1
# Compatible with: Ubuntu, Debian, Fedora, CentOS, Arch, openSUSE, and other Linux distributions

set -e  # Exit on error
cd "$(dirname "$0")"  # Change to script directory

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if running as root (needed for some installations)
check_root() {
    if [ "$EUID" -eq 0 ]; then 
        echo "✓ Running with root privileges"
    else
        warning "Not running as root"
        warning "Some installations may require sudo rights"
    fi
}

# Detect Linux distribution
detect_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        DISTRO=$ID
        VERSION=$VERSION_ID
        log "Detected distribution: $DISTRO $VERSION"
        return 0
    elif command -v lsb_release &> /dev/null; then
        DISTRO=$(lsb_release -si | tr '[:upper:]' '[:lower:]')
        VERSION=$(lsb_release -sr)
        log "Detected distribution: $DISTRO $VERSION"
        return 0
    else
        warning "Could not detect Linux distribution automatically."
        return 1
    fi
}

# Manual distribution selection
manual_distro_select() {
    echo "==============================================="
    echo "        SELECT YOUR LINUX DISTRIBUTION"
    echo "==============================================="
    echo
    echo "1. Ubuntu / Debian / Linux Mint / Pop!_OS"
    echo "2. Fedora / Red Hat / CentOS"
    echo "3. Arch Linux / Manjaro"
    echo "4. openSUSE"
    echo "5. Other (Manual installation required)"
    echo
    echo "==============================================="
    
    while true; do
        read -p "Select option (1-5): " distro_choice
        
        case $distro_choice in
            1)
                DISTRO="debian"
                echo "Using Debian/Ubuntu package manager (apt)"
                return 0
                ;;
            2)
                DISTRO="fedora"
                echo "Using Fedora/RHEL package manager (dnf/yum)"
                return 0
                ;;
            3)
                DISTRO="arch"
                echo "Using Arch Linux package manager (pacman)"
                return 0
                ;;
            4)
                DISTRO="opensuse"
                echo "Using openSUSE package manager (zypper)"
                return 0
                ;;
            5)
                DISTRO="other"
                echo "Manual installation required"
                return 1
                ;;
            *)
                echo "Invalid choice. Please try again."
                ;;
        esac
    done
}

# Install system packages based on distribution
install_system_packages() {
    case $DISTRO in
        ubuntu|debian|linuxmint|pop|debian)
            log "Installing packages for Debian-based system..."
            sudo apt-get update
            sudo apt-get install -y python3 python3-pip python3-venv ffmpeg \
                git curl wget build-essential python3-dev
            ;;
        fedora|rhel|centos|fedora)
            log "Installing packages for Red Hat-based system..."
            if command -v dnf &> /dev/null; then
                sudo dnf install -y python3 python3-pip python3-virtualenv \
                    ffmpeg git curl wget python3-devel gcc
            elif command -v yum &> /dev/null; then
                sudo yum install -y python3 python3-pip ffmpeg git curl wget \
                    python3-devel gcc
            fi
            ;;
        arch|manjaro|endeavouros|arch)
            log "Installing packages for Arch-based system..."
            sudo pacman -Sy --noconfirm python python-pip python-virtualenv \
                ffmpeg git curl wget base-devel
            ;;
        opensuse|opensuse-tumbleweed|opensuse)
            log "Installing packages for openSUSE..."
            sudo zypper install -y python3 python3-pip python3-virtualenv \
                ffmpeg git curl wget gcc python3-devel
            ;;
        other)
            warning "Unsupported distribution. Manual installation required."
            echo "Please install the following packages manually:"
            echo "- Python 3.8 or higher"
            echo "- pip (Python package manager)"
            echo "- ffmpeg"
            echo "- git, curl, wget"
            echo "- Python development headers (python3-dev/python3-devel)"
            echo "- GCC/build-essential for compilation"
            echo
            read -p "Press Enter after manual installation or Ctrl+C to abort..."
            return 1
            ;;
        *)
            error "Unknown distribution: $DISTRO"
            return 1
            ;;
    esac
    return 0
}

# Install Python dependencies
install_python_deps() {
    log "Installing/updating Python dependencies..."
    
    echo "1. discord.py[voice] (Discord API library)"
    echo "2. yt-dlp (YouTube audio downloader)"
    echo "3. PyNaCl (Audio encryption)"
    echo "4. tabulate (CLI tables)"
    echo "5. PyYAML (Configuration files)"
    echo
    echo "This may take a few minutes..."
    echo

    # Upgrade pip first
    python3 -m pip install --upgrade pip
    
    # Install packages
    local packages=("discord.py[voice]" "yt-dlp" "pynacl" "tabulate" "pyyaml")
    local install_failed=0
    
    for package in "${packages[@]}"; do
        log "Installing $package..."
        if python3 -m pip install "$package" --upgrade; then
            echo "✓ $package installed/updated"
        else
            error "Failed to install $package"
            install_failed=1
        fi
        echo
    done

    echo "Verifying installations..."
    echo
    python3 -c "import discord; print('✓ discord.py version:', discord.__version__)" 2>/dev/null || echo "✗ discord.py failed"
    python3 -c "import yt_dlp; print('✓ yt-dlp version:', yt_dlp.version.__version__)" 2>/dev/null || echo "✗ yt-dlp failed"
    python3 -c "import nacl.secret; print('✓ PyNaCl imported')" 2>/dev/null || echo "✗ PyNaCl failed"
    python3 -c "from tabulate import tabulate; print('✓ tabulate imported')" 2>/dev/null || echo "✗ tabulate failed"
    python3 -c "import yaml; print('✓ PyYAML imported')" 2>/dev/null || echo "✗ PyYAML failed"

    if [ $install_failed -eq 0 ]; then
        success "All dependencies installed successfully"
    else
        warning "Some dependencies failed to install"
        echo "Try running with sudo or install manually"
    fi
    
    return $install_failed
}

# Install FFmpeg
install_ffmpeg() {
    log "Checking FFmpeg installation..."
    
    if command -v ffmpeg &> /dev/null; then
        ffmpeg -version | head -n1
        success "FFmpeg is already installed"
        return 0
    fi

    warning "FFmpeg not found. Installing..."
    echo

    case $DISTRO in
        ubuntu|debian|linuxmint|pop|debian)
            sudo apt-get install -y ffmpeg
            ;;
        fedora|rhel|centos|fedora)
            if command -v dnf &> /dev/null; then
                sudo dnf install -y ffmpeg
            else
                sudo yum install -y ffmpeg
            fi
            ;;
        arch|manjaro|endeavouros|arch)
            sudo pacman -S --noconfirm ffmpeg
            ;;
        opensuse|opensuse-tumbleweed|opensuse)
            sudo zypper install -y ffmpeg
            ;;
        other)
            error "Cannot auto-install FFmpeg on this distribution"
            echo "Please install FFmpeg manually from: https://ffmpeg.org/download.html"
            return 1
            ;;
    esac

    if command -v ffmpeg &> /dev/null; then
        success "FFmpeg installed successfully"
        return 0
    else
        error "FFmpeg installation failed"
        return 1
    fi
}

# Create necessary directories
create_directories() {
    log "Creating necessary directories..."
    
    local dirs=("downloads" "logs" "config")
    
    for dir in "${dirs[@]}"; do
        if [ ! -d "$dir" ]; then
            mkdir -p "$dir"
            log "Created directory: $dir"
        fi
    done
    
    # Create default config file if it doesn't exist
    if [ ! -f "config/bot_config.txt" ]; then
        cat > "config/bot_config.txt" << EOF
# F-T CLI Bot Configuration
# Generated on $(date)

# Bot Settings
# Replace with your bot token (or leave as is to use hardcoded one)
#bot_token=YOUR_BOT_TOKEN_HERE

# Audio Settings
#ffmpeg_path=/usr/bin/ffmpeg
#max_volume=100

# Logging
#log_level=INFO
#max_log_size=10MB

# Linux-specific settings
#use_pulseaudio=true
#audio_driver=pulse
EOF
        success "Created configuration file"
    fi
}

# Verify Python installation
verify_python() {
    if ! command -v python3 &> /dev/null; then
        error "Python 3 not found!"
        return 1
    fi
    
    local python_version=$(python3 --version 2>&1 | cut -d' ' -f2)
    local major=$(echo $python_version | cut -d. -f1)
    local minor=$(echo $python_version | cut -d. -f2)
    
    if [ "$major" -lt 3 ] || ([ "$major" -eq 3 ] && [ "$minor" -lt 8 ]); then
        warning "Python version $python_version detected. Python 3.8+ is recommended."
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        [[ ! $REPLY =~ ^[Yy]$ ]] && return 1
    fi
    
    success "Python $python_version verified"
    return 0
}

# Create virtual environment
create_venv() {
    log "Creating Python virtual environment..."
    
    if [ -d "venv" ]; then
        read -p "Virtual environment already exists. Recreate? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            return 0
        fi
        rm -rf venv
    fi
    
    python3 -m venv venv
    if [ $? -eq 0 ]; then
        success "Virtual environment created"
        
        # Create venv launcher script
        cat > "run_venv.sh" << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "ERROR: Virtual environment not found"
    echo "Run option 5 from main menu to create it"
    exit 1
fi

echo "Activating virtual environment..."
source venv/bin/activate

echo
echo "Python: $(python --version)"
echo

echo "Installing dependencies in virtual environment..."
pip install discord.py[voice] yt-dlp pynacl tabulate pyyaml

echo
echo "Starting bot..."
echo
python F-T_CLI_v0.3.1.py

echo
echo "Deactivating virtual environment..."
deactivate
EOF
        chmod +x run_venv.sh
        echo "Created 'run_venv.sh' to run bot in virtual environment"
    else
        error "Failed to create virtual environment"
        return 1
    fi
}

# Run the bot
run_bot() {
    log "Starting F-T CLI Bot..."
    
    # Check if main script exists
    if [ ! -f "F-T_CLI_v0.3.1.py" ]; then
        error "Main bot script F-T_CLI_v0.3.1.py not found!"
        return 1
    fi
    
    # Activate virtual environment if using one
    if [ -d "venv" ] && [ -f "venv/bin/activate" ]; then
        log "Activating virtual environment..."
        source venv/bin/activate
    fi
    
    # Set Python environment variables
    export PYTHONIOENCODING=utf-8
    export PYTHONUNBUFFERED=1
    export PYTHONFAULTHANDLER=1
    
    # Create log directory if it doesn't exist
    if [ ! -d "logs" ]; then
        mkdir -p logs
    fi
    
    local timestamp=$(date '+%Y-%m-%d_%H-%M-%S')
    local log_file="logs/bot_$timestamp.log"
    
    echo "==============================================="
    echo "        RUNNING F-T CLI BOT"
    echo "==============================================="
    echo
    echo "Starting Discord bot..."
    echo
    echo "IMPORTANT: Keep this window open while bot is running"
    echo "Press Ctrl+C to stop the bot"
    echo
    echo "Log files will be saved to 'logs/' folder"
    echo "Downloaded audio will be saved to 'downloads/' folder"
    echo
    echo "Log file: $log_file"
    echo "Python: $(python3 --version)"
    echo
    echo "==============================================="
    echo
    
    # Run bot with logging
    python3 F-T_CLI_v0.3.1.py 2>&1 | tee "$log_file"
    
    local exit_code=${PIPESTATUS[0]}
    
    echo "==============================================="
    log "Bot stopped with exit code: $exit_code"
    
    return $exit_code
}

# Open logs directory
open_logs() {
    if [ -d "logs" ]; then
        echo "Opening logs folder..."
        ls -la logs/
        echo
        read -p "View a specific log file? (Enter filename or press Enter to skip): " logfile
        if [ -n "$logfile" ]; then
            if [ -f "logs/$logfile" ]; then
                less "logs/$logfile"
            else
                error "File not found: logs/$logfile"
            fi
        fi
    else
        warning "Logs directory doesn't exist yet."
        echo "It will be created when the bot runs."
    fi
}

# Edit configuration
edit_config() {
    if [ -f "config/bot_config.txt" ]; then
        ${EDITOR:-nano} "config/bot_config.txt"
    else
        warning "No configuration file found."
        echo "One will be created when you run auto-setup."
    fi
}

# Show system information
system_info() {
    echo "System Information:"
    echo "-------------------"
    echo "Distribution: $(lsb_release -ds 2>/dev/null || cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"')"
    echo "Kernel: $(uname -r)"
    echo "Architecture: $(uname -m)"
    echo
    echo "Python: $(python3 --version 2>/dev/null || echo 'Not found')"
    echo "Pip: $(python3 -m pip --version 2>/dev/null | cut -d' ' -f2 || echo 'Not found')"
    echo "FFmpeg: $(ffmpeg -version 2>/dev/null | head -n1 | cut -d' ' -f1-3 || echo 'Not found')"
    echo
    echo "Disk space in current directory:"
    df -h .
    echo
}

# Post-run menu
post_run_menu() {
    echo
    echo "==============================================="
    echo "BOT SESSION ENDED"
    echo "==============================================="
    echo
    echo "Options:"
    echo "1. Restart bot"
    echo "2. View latest log"
    echo "3. Return to main menu"
    echo "4. Exit"
    echo
    
    while true; do
        read -p "Select option (1-4): " post_choice
        
        case $post_choice in
            1)
                echo
                echo "Restarting bot..."
                sleep 2
                run_bot
                break
                ;;
            2)
                echo
                echo "Opening latest log file..."
                if [ -d "logs" ]; then
                    latest_log=$(ls -t logs/*.log 2>/dev/null | head -n1)
                    if [ -n "$latest_log" ]; then
                        less "$latest_log"
                    else
                        echo "No log files found."
                    fi
                else
                    echo "Logs directory doesn't exist."
                fi
                post_run_menu
                break
                ;;
            3)
                break
                ;;
            4)
                exit 0
                ;;
            *)
                echo "Invalid choice."
                ;;
        esac
    done
}

# Main menu
main_menu() {
    clear
    echo "==============================================="
    echo "        MAIN MENU - F-T CLI BOT"
    echo "==============================================="
    echo
    echo "1. Complete Auto-Setup (Recommended for first time)"
    echo "2. Run Bot Only (Skip installations)"
    echo "3. Install/Update Dependencies Only"
    echo "4. Install FFmpeg Only"
    echo "5. Create Virtual Environment (Advanced)"
    echo "6. Open Logs Directory"
    echo "7. Edit Configuration"
    echo "8. System Information"
    echo "9. Exit"
    echo
    echo "==============================================="
}

# Main function
main() {
    # Display header
    clear
    echo "==============================================="
    echo "        F-T CLI DISCORD BOT - COMPLETE SETUP"
    echo "==============================================="
    echo
    echo "This script will:"
    echo "1. Install Python 3.11 if needed"
    echo "2. Install all required pip packages"
    echo "3. Install FFmpeg for audio"
    echo "4. Set up necessary folders"
    echo "5. Run the bot with persistent terminal"
    echo
    echo "Terminal will remain open to show all output"
    echo "==============================================="
    echo
    
    # Check root
    check_root
    
    # Detect distribution
    if ! detect_distro; then
        warning "Auto-detection failed"
        if ! manual_distro_select; then
            error "Cannot proceed without distribution information"
            exit 1
        fi
    fi
    
    # Main loop
    while true; do
        main_menu
        read -p "Select option (1-9): " choice
        
        case $choice in
            1)
                # Complete auto-setup
                clear
                echo "==============================================="
                echo "        COMPLETE AUTO-SETUP"
                echo "==============================================="
                echo
                echo "Starting complete setup process..."
                echo "This may take several minutes."
                echo
                
                # Step 1: Check/Install Python
                echo "Step 1: Checking Python installation..."
                if ! verify_python; then
                    install_system_packages
                    verify_python || continue
                fi
                
                # Step 2: Update pip
                echo
                echo "Step 2: Updating pip..."
                python3 -m pip install --upgrade pip
                
                # Step 3: Install FFmpeg
                echo
                echo "Step 3: Installing FFmpeg..."
                install_ffmpeg
                
                # Step 4: Install Python dependencies
                echo
                echo "Step 4: Installing Python dependencies..."
                install_python_deps
                
                # Step 5: Create directories
                echo
                echo "Step 5: Creating necessary directories..."
                create_directories
                
                # Step 6: Create configuration file
                echo
                echo "Step 6: Setting up configuration..."
                echo "✓ Configuration complete"
                
                echo
                echo "==============================================="
                echo "SETUP COMPLETE!"
                echo "==============================================="
                echo
                read -p "Press Enter to run the bot..."
                run_bot
                post_run_menu
                ;;
            2)
                run_bot
                post_run_menu
                ;;
            3)
                clear
                install_python_deps
                echo
                read -p "Press Enter to return to main menu..."
                ;;
            4)
                clear
                install_ffmpeg
                echo
                read -p "Press Enter to return to main menu..."
                ;;
            5)
                clear
                create_venv
                echo
                read -p "Press Enter to return to main menu..."
                ;;
            6)
                clear
                open_logs
                echo
                read -p "Press Enter to return to main menu..."
                ;;
            7)
                clear
                edit_config
                ;;
            8)
                clear
                system_info
                echo
                read -p "Press Enter to continue..."
                ;;
            9)
                echo
                echo "==============================================="
                echo "        THANK YOU FOR USING F-T CLI BOT"
                echo "==============================================="
                echo
                echo "Files created:"
                [ -d "logs" ] && echo "- logs/ (Log files)"
                [ -d "downloads" ] && echo "- downloads/ (Audio downloads)"
                [ -d "config" ] && echo "- config/ (Configuration)"
                [ -f "run_venv.sh" ] && echo "- run_venv.sh (Virtual environment launcher)"
                echo
                echo "To run again, execute: ./pre-requisites.sh or ./launch.sh"
                echo
                echo "==============================================="
                sleep 3
                exit 0
                ;;
            *)
                echo "Invalid choice. Please try again."
                sleep 2
                ;;
        esac
    done
}

# Check if running in terminal
if [ -t 0 ]; then
    # Run main function
    main
else
    echo "This script must be run in a terminal."
    exit 1
fi
