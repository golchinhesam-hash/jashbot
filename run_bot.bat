@echo off
chcp 65001 >nul
echo ==========================================
echo   🤖 CRYPTO SIGNAL BOT - DEPLOY
echo   9 Systems Active
echo ==========================================
echo.

cd /d "C:\Users\Hesam\WorkBuddy AI\Claw\crypto-signal-bot"

:: Kill any existing python bot processes
taskkill /F /FI "WINDOWTITLE eq *signal*bot*" 2>nul
taskkill /F /FI "WINDOWTITLE eq *python*" 2>nul

echo 🛑 Stopped any existing bot instances
echo 🚀 Starting bot with all features...
echo.

python main.py

pause
