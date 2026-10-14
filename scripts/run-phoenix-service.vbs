' UuMA Phoenix - 100% Silent Windowless Background Launcher
Option Explicit
Dim WshShell, objEnv
Set WshShell = CreateObject("WScript.Shell")
Set objEnv = WshShell.Environment("PROCESS")

objEnv("PHOENIX_WORKING_DIR") = "C:\Users\Alandelone\AppData\Local\UuMA\phoenix-runtime\data"
objEnv("PHOENIX_ALLOW_EXTERNAL_RESOURCES") = "false"
objEnv("PHOENIX_HOST") = "127.0.0.1"
objEnv("PYTHONUTF8") = "1"
WshShell.CurrentDirectory = "C:\Users\Alandelone\AppData\Local\UuMA\phoenix-runtime\data"

WshShell.Run """C:\Users\Alandelone\AppData\Local\UuMA\phoenix-runtime\venv\Scripts\phoenix.exe"" serve", 0, False
