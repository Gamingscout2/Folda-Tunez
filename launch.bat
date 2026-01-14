@echo off
title F-T CLI Bot Launcher
color 0A
mode con: cols=80 lines=25

echo ===============================================
echo        F-T CLI DISCORD BOT LAUNCHER
echo ===============================================
echo.
echo Quick Access Options:
echo.
echo [R] Run Bot Immediately
echo [S] Setup & Run (First Time)
echo [M] Open Main Menu
echo [X] Exit
echo.
echo ===============================================
set /p quick_choice="Choose option (R/S/M/X): "

if /i "!quick_choice!"=="R" goto RUN_NOW
if /i "!quick_choice!"=="S" goto SETUP_RUN
if /i "!quick_choice!"=="M" goto MAIN
if /i "!quick_choice!"=="X" exit /b

:RUN_NOW
cls
echo Starting bot now...
timeout /t 2 /nobreak >nul
python F-T_CLI_v0.3.1.py
pause
exit /b

:SETUP_RUN
cls
echo Starting complete setup...
timeout /t 2 /nobreak >nul
:: If you saved the main script as "ft_bot_setup.bat"
if exist "ft_bot_setup.bat" (
    call ft_bot_setup.bat
) else (
    echo ERROR: Main setup script not found
    echo Make sure ft_bot_setup.bat is in the same folder
    pause
)
exit /b

:MAIN
:: If you saved the main script as "ft_bot_setup.bat"
if exist "ft_bot_setup.bat" (
    start ft_bot_setup.bat
) else (
    echo ERROR: Main setup script not found
    pause
)
exit /b