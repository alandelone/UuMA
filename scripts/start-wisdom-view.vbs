' UuMA Wisdom Document View - Silent Background Launcher (Hermes Style)
Option Explicit
Dim fso, sh, scriptDir, psScript, dataDir, pythonExe, projectRoot, port
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
psScript = scriptDir & "\start-wisdom-view.ps1"
dataDir = fso.BuildPath(sh.ExpandEnvironmentStrings("%USERPROFILE%"), "AppData\Local\UuMA")
If WScript.Arguments.Count > 0 Then dataDir = WScript.Arguments(0)
projectRoot = fso.GetParentFolderName(scriptDir)
If WScript.Arguments.Count > 2 Then projectRoot = WScript.Arguments(2)
pythonExe = fso.BuildPath(projectRoot, ".venv\Scripts\python.exe")
If WScript.Arguments.Count > 1 Then pythonExe = WScript.Arguments(1)
port = "8767"
If WScript.Arguments.Count > 3 Then port = WScript.Arguments(3)

' 0 = vbHide (no terminal window), False = run detached in background
sh.Run "powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File """ & psScript & """ -DataDir """ & dataDir & """ -PythonExe """ & pythonExe & """ -ProjectRoot """ & projectRoot & """ -Port " & port, 0, False
