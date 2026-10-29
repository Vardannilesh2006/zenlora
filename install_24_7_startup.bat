@echo off
set SCRIPT_PATH=E:\Zenlora\gateway\start_gateway_silent.vbs
set STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set SHORTCUT_PATH=%STARTUP_DIR%\ZenOS_WhatsApp_Gateway.lnk

echo Creating 24/7 Windows Startup Shortcut...
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath = 'wscript.exe'; $s.Arguments = '\"%SCRIPT_PATH%\"'; $s.WorkingDirectory = 'E:\Zenlora\gateway'; $s.WindowStyle = 7; $s.Save()"

if exist "%SHORTCUT_PATH%" (
    echo [SUCCESS] ZenOS WhatsApp Gateway will now automatically launch 24/7 on Windows boot!
) else (
    echo [ERROR] Failed to create startup shortcut.
)
pause
