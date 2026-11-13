Option Explicit
Dim WshShell
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\Alandelone\CodeSpace_Local\UuMA"
WshShell.Run "powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File ""C:\Users\Alandelone\CodeSpace_Local\UuMA\scripts\run-antigravity-gateway-service.ps1"" -ProjectRoot ""C:\Users\Alandelone\CodeSpace_Local\UuMA""", 0, False
