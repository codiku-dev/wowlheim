# launch_wow.ps1 : lance WoW.exe de la COPIE client_test (jamais l'original), eventuellement avec la DLL.
# usage: .\launch_wow.ps1 [-Dll]   ; arret propre : .\stop_wow.ps1
param([switch]$Dll)
$dir = 'C:\Wowlheim\client_test'
if (-not (Test-Path "$dir\WoW.exe")) { throw 'client_test absent' }
if (Get-Process WoW -ErrorAction SilentlyContinue) { throw 'WoW.exe tourne deja' }
if ($Dll) {
  & "$PSScriptRoot\launch_play.exe" "$dir\WoW.exe" "$dir\wowlheim_client.dll" 0
} else {
  Start-Process "$dir\WoW.exe" -WorkingDirectory $dir
}
