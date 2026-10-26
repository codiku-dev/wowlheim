# Arret propre : WM_CLOSE puis taskkill. Note : Path de WoW.exe est illisible (acces refuse) ; on ne cible que le nom WoW
# (le client d'origine n'est jamais lance par ces outils).
foreach ($x in Get-Process WoW -ErrorAction SilentlyContinue) { [void]$x.CloseMainWindow() }
Start-Sleep 5
foreach ($x in Get-Process WoW -ErrorAction SilentlyContinue) { taskkill /PID $x.Id /F }
Get-Process WoW -ErrorAction SilentlyContinue | Select-Object Id
