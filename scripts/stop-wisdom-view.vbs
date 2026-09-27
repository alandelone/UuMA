' UuMA Wisdom Document View - Silent Stopper
Option Explicit
Dim fso, sh, scriptDir, psScript
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
psScript = scriptDir & "\stop-wisdom-view.ps1"

sh.Run "powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File """ & psScript & """", 0, True
