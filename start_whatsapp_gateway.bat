@echo off
title OpenWA WhatsApp Gateway - ZenOS
cd /d "%~dp0gateway"
echo ========================================================
echo ⚡ Starting OpenWA WhatsApp Gateway for ZenOS...
echo 📱 Open your browser: http://localhost:2785
echo ========================================================
start http://localhost:2785
node server.js
pause
