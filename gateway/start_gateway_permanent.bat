@echo off
title ZenOS OpenWA 24/7 WhatsApp Gateway
cd /d "%~dp0"

echo ========================================================
echo  ZenOS 24/7 WhatsApp Gateway (OpenWA + Cloudflare Bridge)
echo ========================================================
echo.

:: 1. Launch Node.js OpenWA Server
start /b node server.js

:: Wait 3 seconds
timeout /t 3 /nobreak >nul

:: 2. Launch Cloudflare Tunnel
start /b "" "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:2785

echo [OK] OpenWA Gateway and Cloudflare Tunnel started successfully!
