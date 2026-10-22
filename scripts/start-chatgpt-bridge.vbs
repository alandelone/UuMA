' UuMA ChatGPT Bridge - 100% Silent Windowless Background Launcher
Option Explicit
Dim WshShell, objEnv
Set WshShell = CreateObject("WScript.Shell")
Set objEnv = WshShell.Environment("PROCESS")

objEnv("PYTHONPATH") = "C:\Users\Alandelone\CodeSpace_Local\UuMA\src"
WshShell.CurrentDirectory = "C:\Users\Alandelone\CodeSpace_Local\UuMA"

WshShell.Run """C:\Users\Alandelone\CodeSpace_Local\UuMA\.venv\Scripts\pythonw.exe"" ""C:\Users\Alandelone\CodeSpace_Local\UuMA\scripts\start-distributed-workstation.py"" --profile ""C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\workstation-node-production-20261022""", 0, False
