' UuMA ChatGPT Bridge - 100% Silent Windowless Background Launcher
Option Explicit
Dim WshShell, objEnv
Set WshShell = CreateObject("WScript.Shell")
Set objEnv = WshShell.Environment("PROCESS")

objEnv("PYTHONPATH") = "C:\Users\Alandelone\CodeSpace_Local\UuMA\src"
WshShell.CurrentDirectory = "C:\Users\Alandelone\CodeSpace_Local\UuMA"

WshShell.Run """C:\Users\Alandelone\CodeSpace_Local\UuMA\.venv\Scripts\pythonw.exe"" -m uuma.chatgpt_cli --data-dir ""C:\Users\Alandelone\AppData\Local\UuMA"" --port 8787 serve", 0, False
