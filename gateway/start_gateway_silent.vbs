Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c """ & "E:\Zenlora\gateway\start_gateway_permanent.bat" & """", 0, False
