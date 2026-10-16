' UuMA All-in-One Observatory - Silent Background Launcher
Option Explicit
Dim fso, sh, scriptDir, psScript, projectRoot, port
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
psScript = scriptDir & "\run-observatory-service.ps1"
projectRoot = fso.GetParentFolderName(scriptDir)

port = "8790"
If WScript.Arguments.Count > 0 Then port = WScript.Arguments(0)

' 0 = vbHide (no terminal window), False = run detached
sh.Run "powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File """ & psScript & """ -ProjectRoot """ & projectRoot & """ -Port " & port, 0, False
