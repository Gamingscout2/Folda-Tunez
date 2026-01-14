@echo off
setlocal enabledelayedexpansion
title F-T CLI Discord Bot v0.3.1 - Complete Setup & Runner
color 0A

echo ===============================================
echo        F-T CLI DISCORD BOT - COMPLETE SETUP
echo ===============================================
echo.
echo This script will:
echo 1. Install Python 3.11 if needed
echo 2. Install all required pip packages
echo 3. Install FFmpeg for audio
echo 4. Set up necessary folders
echo 5. Run the bot with persistent terminal
echo.
echo Terminal will remain open to show all output
echo ===============================================

:: Check if running as admin (needed for some installations)
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo INFO: Not running as administrator
    echo Some installations may require admin rights
    echo.
) else (
    echo ✓ Running with administrator privileges
)

:MAIN_MENU
cls
echo ===============================================
echo        MAIN MENU - F-T CLI BOT
echo ===============================================
echo.
echo 1. Complete Auto-Setup (Recommended for first time)
echo 2. Run Bot Only (Skip installations)
echo 3. Install/Update Dependencies Only
echo 4. Install FFmpeg Only
echo 5. Create Virtual Environment (Advanced)
echo 6. Open Logs Directory
echo 7. Edit Configuration
echo 8. Exit
echo.
echo ===============================================
set /p choice="Select option (1-8): "

if "!choice!"=="1" goto AUTO_SETUP
if "!choice!"=="2" goto RUN_BOT
if "!choice!"=="3" goto INSTALL_DEPS
if "!choice!"=="4" goto INSTALL_FFMPEG
if "!choice!"=="5" goto CREATE_VENV
if "!choice!"=="6" goto OPEN_LOGS
if "!choice!"=="7" goto EDIT_CONFIG
if "!choice!"=="8" goto EXIT

echo Invalid choice. Press any key to try again...
pause >nul
goto MAIN_MENU

:AUTO_SETUP
cls
echo ===============================================
echo        COMPLETE AUTO-SETUP
echo ===============================================
echo.
echo Starting complete setup process...
echo This may take several minutes.
echo.
echo ===============================================
echo.
echo Step 1: Checking system requirements...
echo.

:: Step 1: Check/Install Python
echo [1/6] Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python not found. Installing Python 3.11...
    echo.
    echo Downloading Python 3.11 installer...
    
    set PYTHON_URL=https://www.python.org/ftp/python/3.11.0/python-3.11.0-amd64.exe
    set PYTHON_INSTALLER=%TEMP%\python_installer.exe
    
    powershell -Command "& {
        try {
            Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_INSTALLER%'
            Write-Host '✓ Download complete' -ForegroundColor Green
        } catch {
            Write-Host '✗ Download failed' -ForegroundColor Red
            Write-Host 'Please download Python manually from: https://python.org'
            exit 1
        }
    }"
    
    if exist "%PYTHON_INSTALLER%" (
        echo.
        echo IMPORTANT: Python Installer will now open.
        echo Please make sure to:
        echo 1. Check "Add Python to PATH"
        echo 2. Click "Install Now"
        echo 3. Wait for installation to complete
        echo.
        echo The script will continue after installation...
        echo.
        pause
        start /wait "" "%PYTHON_INSTALLER%"
        del "%PYTHON_INSTALLER%" 2>nul
    )
) else (
    python --version
    echo ✓ Python is installed
)

:: Step 2: Update pip
echo.
echo [2/6] Updating pip...
python -m pip install --upgrade pip --no-warn-script-location
if %errorlevel% neq 0 (
    echo Warning: Failed to update pip. Trying with --user flag...
    python -m pip install --upgrade pip --user --no-warn-script-location
)

:: Step 3: Install FFmpeg
echo.
echo [3/6] Installing FFmpeg...
call :INSTALL_FFMPEG_SILENT
if %errorlevel% equ 0 (
    echo ✓ FFmpeg installed/verified
) else (
    echo ✗ FFmpeg installation failed
    echo Audio playback may not work without FFmpeg
)

:: Step 4: Install Python dependencies
echo.
echo [4/6] Installing Python dependencies...
call :INSTALL_DEPENDENCIES
if %errorlevel% equ 0 (
    echo ✓ Dependencies installed successfully
) else (
    echo ✗ Some dependencies failed to install
)

:: Step 5: Create directories
echo.
echo [5/6] Creating necessary directories...
if not exist "downloads" mkdir downloads
if not exist "logs" mkdir logs
if not exist "config" mkdir config
echo ✓ Directories created

:: Step 6: Create configuration file if not exists
echo.
echo [6/6] Setting up configuration...
if not exist "config\bot_config.txt" (
    (
    echo # F-T CLI Bot Configuration
    echo # Generated on %date% %time%
    echo.
    echo # Bot Settings
    echo # Replace with your bot token (or leave as is to use hardcoded one)
    echo #bot_token=YOUR_BOT_TOKEN_HERE
    echo.
    echo # Audio Settings
    echo #ffmpeg_path=C:\ffmpeg\bin\ffmpeg.exe
    echo #max_volume=100
    echo.
    echo # Logging
    echo #log_level=INFO
    echo #max_log_size=10MB
    ) > config\bot_config.txt
    echo ✓ Configuration file created
) else (
    echo ✓ Configuration file exists
)

echo.
echo ===============================================
echo SETUP COMPLETE!
echo ===============================================
echo.
echo Press any key to run the bot...
pause >nul
goto RUN_BOT

:RUN_BOT
cls
echo ===============================================
echo        RUNNING F-T CLI BOT
echo ===============================================
echo.
echo Starting Discord bot...
echo.
echo IMPORTANT: Keep this window open while bot is running
echo Press Ctrl+C to stop the bot
echo.
echo Log files will be saved to 'logs\' folder
echo Downloaded audio will be saved to 'downloads\' folder
echo.
echo ===============================================
echo.

:: Set environment variables for better performance
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set PYTHONFAULTHANDLER=1

:: Check if Python script exists
if not exist "F-T_CLI_v0.3.1.py" (
    echo ERROR: F-T_CLI_v0.3.1.py not found!
    echo Please make sure the Python file is in the same directory.
    pause
    goto MAIN_MENU
)

:: Create timestamp for log file
set timestamp=%date:~10,4%-%date:~4,2%-%date:~7,2%_%time:~0,2%-%time:~3,2%-%time:~6,2%
set timestamp=%timestamp: =0%

:: Create log directory if it doesn't exist
if not exist "logs" mkdir logs
set LOG_FILE=logs\bot_%timestamp%.log

echo [%time%] Starting F-T CLI Bot v0.3.1...
echo [%time%] Log file: %LOG_FILE%
echo [%time%] Python: !python --version!
echo.

:: Create a Python wrapper for better logging and error handling
(
import sys
import os
import subprocess
import threading
import time
from datetime import datetime
import signal

def signal_handler(sig, frame):
    print(f"\n[{datetime.now().strftime('%%H:%%M:%%S')}] Received shutdown signal")
    sys.exit(0)

def read_output(pipe, log_file, prefix):
    """Read output from pipe and write to log file"""
    try:
        with open(log_file, 'a', encoding='utf-8', errors='replace') as f:
            while True:
                line = pipe.readline()
                if not line:
                    break
                if line.strip():
                    timestamp = datetime.now().strftime('%%H:%%M:%%S')
                    log_line = f'[{timestamp}] {prefix}: {line.rstrip()}'
                    print(log_line)
                    f.write(log_line + '\n')
                    f.flush()
    except Exception as e:
        print(f"Logging error: {e}")

def main():
    # Setup signal handling for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    # Get log file path
    log_file = os.path.join('logs', f'bot_{datetime.now().strftime("%%Y-%%m-%%d_%%H-%%M-%%S")}.log')
    
    print(f'[{datetime.now().strftime("%%H:%%M:%%S")}] Logging to: {log_file}')
    print(f'[{datetime.now().strftime("%%H:%%M:%%S")}] Starting F-T CLI Bot...')
    print('=' * 80)
    
    # Create log header
    with open(log_file, 'w', encoding='utf-8') as f:
        f.write(f'F-T CLI Bot Log - Started at {datetime.now()}\n')
        f.write(f'Python: {sys.version}\n')
        f.write(f'Working Directory: {os.getcwd()}\n')
        f.write('=' * 80 + '\n\n')
    
    # Start the bot process
    try:
        process = subprocess.Popen(
            [sys.executable, 'F-T_CLI_v0.3.1.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1,
            universal_newlines=True,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        )
    except FileNotFoundError:
        print(f"[{datetime.now().strftime('%%H:%%M:%%S')}] ERROR: Python not found or F-T_CLI_v0.3.1.py missing")
        return 1
    except Exception as e:
        print(f"[{datetime.now().strftime('%%H:%%M:%%S')}] ERROR: Failed to start bot: {e}")
        return 1
    
    # Start threads to read output
    stdout_thread = threading.Thread(
        target=read_output,
        args=(process.stdout, log_file, 'OUT'),
        daemon=True
    )
    stderr_thread = threading.Thread(
        target=read_output,
        args=(process.stderr, log_file, 'ERR'),
        daemon=True
    )
    
    stdout_thread.start()
    stderr_thread.start()
    
    print(f'[{datetime.now().strftime("%%H:%%M:%%S")}] Bot started with PID: {process.pid}')
    print(f'[{datetime.now().strftime("%%H:%%M:%%S")}] Press Ctrl+C to stop the bot')
    print('=' * 80)
    
    try:
        # Wait for process to complete
        return_code = process.wait()
        print(f'[{datetime.now().strftime("%%H:%%M:%%S")}] Bot stopped with exit code: {return_code}')
        
    except KeyboardInterrupt:
        print(f'\n[{datetime.now().strftime("%%H:%%M:%%S")}] Stopping bot...')
        try:
            # Try graceful shutdown
            process.terminate()
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            print(f'[{datetime.now().strftime("%%H:%%M:%%S")}] Force killing bot...')
            process.kill()
            process.wait()
        
        return_code = process.returncode
        print(f'[{datetime.now().strftime("%%H:%%M:%%S")}] Bot stopped with exit code: {return_code}')
    
    except Exception as e:
        print(f'[{datetime.now().strftime("%%H:%%M:%%S")}] Unexpected error: {e}')
        return_code = 1
    
    # Wait a bit for output threads to finish
    time.sleep(1)
    
    return return_code

if __name__ == '__main__':
    sys.exit(main())
) > run_bot_wrapper.py

:: Run the bot with the wrapper
python run_bot_wrapper.py
set BOT_EXIT_CODE=%errorlevel%

:: Clean up wrapper
del run_bot_wrapper.py 2>nul

echo.
echo ===============================================
echo BOT SESSION ENDED
echo ===============================================
echo Exit Code: %BOT_EXIT_CODE%
echo.
echo Options:
echo 1. Restart bot
echo 2. View latest log
echo 3. Return to main menu
echo 4. Exit
echo.

:POST_RUN_MENU
set /p post_choice="Select option (1-4): "

if "!post_choice!"=="1" (
    echo.
    echo Restarting bot...
    timeout /t 2 /nobreak >nul
    goto RUN_BOT
)
if "!post_choice!"=="2" (
    echo.
    echo Opening latest log file...
    for /f "delims=" %%f in ('dir /b /od /a-d logs\*.log 2^>nul') do set "latest_log=%%f"
    if defined latest_log (
        notepad "logs\!latest_log!"
    ) else (
        echo No log files found.
    )
    goto POST_RUN_MENU
)
if "!post_choice!"=="3" (
    goto MAIN_MENU
)
if "!post_choice!"=="4" (
    goto EXIT
)
echo Invalid choice.
goto POST_RUN_MENU

:INSTALL_DEPS
cls
echo ===============================================
echo        INSTALLING/UPDATE DEPENDENCIES
echo ===============================================
echo.
call :INSTALL_DEPENDENCIES
echo.
echo Press any key to return to main menu...
pause >nul
goto MAIN_MENU

:INSTALL_DEPENDENCIES
echo Installing/updating Python dependencies...
echo.
echo 1. discord.py[voice] (Discord API library)
echo 2. yt-dlp (YouTube audio downloader)
echo 3. PyNaCl (Audio encryption)
echo 4. tabulate (CLI tables)
echo 5. PyYAML (Configuration files)
echo.
echo This may take a few minutes...
echo.

set DEPENDENCIES=discord.py[voice] yt-dlp pynacl tabulate pyyaml
set INSTALL_FAILED=0

for %%p in (%DEPENDENCIES%) do (
    echo Installing %%p...
    python -m pip install %%p --upgrade --no-warn-script-location 2>&1 | findstr /v "Requirement already satisfied"
    if !errorlevel! neq 0 (
        echo Warning: Failed to install %%p. Trying with --user flag...
        python -m pip install %%p --upgrade --user --no-warn-script-location >nul 2>&1
        if !errorlevel! neq 0 (
            echo ERROR: Failed to install %%p
            set INSTALL_FAILED=1
        ) else (
            echo ✓ %%p installed with --user flag
        )
    ) else (
        echo ✓ %%p installed/updated
    )
    echo.
)

echo Verifying installations...
echo.
python -c "import discord; print('✓ discord.py version:', discord.__version__)" 2>nul || echo ✗ discord.py failed
python -c "import yt_dlp; print('✓ yt-dlp version:', yt_dlp.version.__version__)" 2>nul || echo ✗ yt-dlp failed
python -c "import nacl.secret; print('✓ PyNaCl imported')" 2>nul || echo ✗ PyNaCl failed
python -c "from tabulate import tabulate; print('✓ tabulate imported')" 2>nul || echo ✗ tabulate failed
python -c "import yaml; print('✓ PyYAML imported')" 2>nul || echo ✗ PyYAML failed

if %INSTALL_FAILED% equ 0 (
    echo.
    echo ✓ All dependencies installed successfully
) else (
    echo.
    echo ⚠ Some dependencies failed to install
    echo Try running as administrator or install manually
)

exit /b %INSTALL_FAILED%

:INSTALL_FFMPEG
cls
echo ===============================================
echo        INSTALLING FFMPEG
echo ===============================================
echo FFmpeg is required for audio processing
echo.
call :INSTALL_FFMPEG_SILENT
echo.
echo Press any key to return to main menu...
pause >nul
goto MAIN_MENU

:INSTALL_FFMPEG_SILENT
echo Checking FFmpeg installation...
ffmpeg -version >nul 2>&1
if %errorlevel% equ 0 (
    ffmpeg -version | findstr "version"
    echo ✓ FFmpeg is already installed
    exit /b 0
)

echo FFmpeg not found. Installing...
echo.

:: Method 1: Try downloading from official site
echo Downloading FFmpeg...
set FFMPEG_URL=https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip
set FFMPEG_ZIP=%TEMP%\ffmpeg.zip
set FFMPEG_EXTRACT=%TEMP%\ffmpeg_extract

powershell -Command "& {
    try {
        Invoke-WebRequest -Uri '%FFMPEG_URL%' -OutFile '%FFMPEG_ZIP%'
        Write-Host '✓ Download successful' -ForegroundColor Green
    } catch {
        Write-Host '✗ Download failed' -ForegroundColor Red
        exit 1
    }
}" 2>nul

if not exist "%FFMPEG_ZIP%" (
    echo Failed to download FFmpeg.
    echo Please download manually from: https://ffmpeg.org/download.html
    echo Extract to: C:\ffmpeg\bin
    exit /b 1
)

:: Extract FFmpeg
echo Extracting FFmpeg...
if not exist "%FFMPEG_EXTRACT%" mkdir "%FFMPEG_EXTRACT%"
powershell -Command "Expand-Archive -Path '%FFMPEG_ZIP%' -DestinationPath '%FFMPEG_EXTRACT%' -Force" 2>nul

:: Find and copy ffmpeg.exe
echo Installing FFmpeg to C:\ffmpeg\bin...
if not exist "C:\ffmpeg\bin" mkdir "C:\ffmpeg\bin"

for /r "%FFMPEG_EXTRACT%" %%i in (ffmpeg.exe) do (
    if exist "%%i" (
        copy "%%i" "C:\ffmpeg\bin\" >nul
        echo Found ffmpeg.exe
        goto FOUND_FFMPEG
    )
)

:FOUND_FFMPEG
for /r "%FFMPEG_EXTRACT%" %%i in (ffprobe.exe) do (
    if exist "%%i" (
        copy "%%i" "C:\ffmpeg\bin\" >nul
    )
)

:: Add to PATH if not already
echo %PATH% | find /i "C:\ffmpeg\bin" >nul
if %errorlevel% neq 0 (
    echo Adding FFmpeg to system PATH...
    setx PATH "%PATH%;C:\ffmpeg\bin" >nul 2>&1
)

:: Verify installation
ffmpeg -version >nul 2>&1
if %errorlevel% equ 0 (
    echo ✓ FFmpeg installed successfully
    echo You may need to restart for PATH changes to take effect
) else (
    echo ✗ FFmpeg installation failed
    echo Please add C:\ffmpeg\bin to your PATH manually
)

:: Cleanup
del "%FFMPEG_ZIP%" 2>nul
rmdir /s /q "%FFMPEG_EXTRACT%" 2>nul

exit /b 0

:CREATE_VENV
cls
echo ===============================================
echo        CREATING VIRTUAL ENVIRONMENT
echo ===============================================
echo.
echo Creating Python virtual environment...
echo This isolates bot dependencies from system Python
echo.

python -m venv venv
if %errorlevel% neq 0 (
    echo ERROR: Failed to create virtual environment
    echo Make sure Python is installed correctly
    pause
    goto MAIN_MENU
)

echo ✓ Virtual environment created
echo.
echo To activate and use the virtual environment:
echo 1. Run: venv\Scripts\activate
echo 2. Install dependencies: pip install discord.py[voice] yt-dlp pynacl tabulate pyyaml
echo 3. Run bot: python F-T_CLI_v0.3.1.py
echo.
echo Or use the batch file 'run_venv.bat' that will be created
echo.

:: Create venv launcher
(
@echo off
setlocal enabledelayedexpansion
title F-T CLI Bot (Virtual Environment)
color 0A

echo ===============================================
echo        F-T CLI BOT - VIRTUAL ENVIRONMENT
echo ===============================================
echo.

if not exist "venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found
    echo Run option 5 from main menu to create it
    pause
    exit /b 1
)

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo.
echo Python: !python --version!
echo.

echo Installing dependencies in virtual environment...
pip install discord.py[voice] yt-dlp pynacl tabulate pyyaml

echo.
echo Starting bot...
echo.
python F-T_CLI_v0.3.1.py

echo.
echo Deactivating virtual environment...
deactivate
pause
) > run_venv.bat

echo Created 'run_venv.bat' to run bot in virtual environment
echo.
pause
goto MAIN_MENU

:OPEN_LOGS
cls
echo ===============================================
echo        LOGS DIRECTORY
echo ===============================================
echo.
if exist "logs" (
    echo Opening logs folder...
    explorer "logs"
) else (
    echo Logs directory doesn't exist yet.
    echo It will be created when the bot runs.
)
echo.
pause
goto MAIN_MENU

:EDIT_CONFIG
cls
echo ===============================================
echo        EDIT CONFIGURATION
echo ===============================================
echo.
if not exist "config\bot_config.txt" (
    echo No configuration file found.
    echo One will be created when you run auto-setup.
) else (
    echo Opening configuration file...
    notepad "config\bot_config.txt"
)
echo.
pause
goto MAIN_MENU

:EXIT
cls
echo ===============================================
echo        THANK YOU FOR USING F-T CLI BOT
echo ===============================================
echo.
echo Files created:
if exist "logs" echo - logs\ (Log files)
if exist "downloads" echo - downloads\ (Audio downloads)
if exist "config" echo - config\ (Configuration)
if exist "run_venv.bat" echo - run_venv.bat (Virtual environment launcher)
echo.
echo To run again, double-click this batch file or 'launcher.bat'
echo.
echo ===============================================
timeout /t 5
exit /b 0