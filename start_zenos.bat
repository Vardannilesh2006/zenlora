@echo off
title ZenOS Founder Cockpit - Zenlora
cd /d "%~dp0"
echo ========================================================
echo 🛡️ Starting ZenOS Founder Cockpit on Port 5000...
echo 🔐 Admin Password: Nilesh@2006
echo 🌐 Opening: http://localhost:5000/login
echo ========================================================
start http://localhost:5000/login
python app.py
pause
