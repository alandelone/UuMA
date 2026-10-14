' UuMA Question Orbit Runner - 100% Silent Windowless Background Launcher
Option Explicit
Dim WshShell, objEnv
Set WshShell = CreateObject("WScript.Shell")
Set objEnv = WshShell.Environment("PROCESS")

objEnv("UUMA_DATA_DIR") = "C:\Users\Alandelone\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\UuMA"
objEnv("PYTHONPATH") = "C:\Users\Alandelone\CodeSpace_Local\UuMA\src"
WshShell.CurrentDirectory = "C:\Users\Alandelone\CodeSpace_Local\UuMA"

WshShell.Run """C:\Users\Alandelone\CodeSpace_Local\UuMA\.venv\Scripts\pythonw.exe"" -m uuma.orbit_runner --profile-home ""C:\Users\Alandelone\AppData\Local\hermes\profiles\wisdom-oldman""", 0, False
