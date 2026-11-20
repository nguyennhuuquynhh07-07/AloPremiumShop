@echo off
chcp 65001 > nul
title Telegram Bot - Kích Hoạt Locket Gold & Spotify
echo ========================================================
echo   BOT TELEGRAM KÍCH HOẠT LOCKET GOLD + SPOTIFY PREMIUM
echo ========================================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [LỖI] Chưa tìm thấy Python trên máy tính.
    echo Vui lòng cài đặt Python từ https://www.python.org/
    pause
    exit /b
)

echo Đang kiểm tra thư viện...
pip install -r requirements.txt >nul 2>&1

echo Đang khởi chạy Bot...
python bot.py
pause

