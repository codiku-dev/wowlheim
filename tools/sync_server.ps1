# Copie les sources Wowlheim dans l'arbre CMaNGOS local et exporte le patch du cœur.
# usage : powershell -File tools\sync_server.ps1 [-Build]
param([switch]$Build)
$repo = Split-Path $PSScriptRoot -Parent
$core = 'C:\Wowlheim\src\mangos-classic'
$dest = Join-Path $core 'src\game\Wowlheim'
New-Item -ItemType Directory -Force $dest | Out-Null
Copy-Item (Join-Path $repo 'server\Wowlheim\*') $dest -Force
Push-Location $core
git diff --binary -- src | Out-File -Encoding ascii (Join-Path $repo 'server\core.patch')
Pop-Location
if ($Build) {
    Set-Location C:\Wowlheim
    cmake -S src\mangos-classic -B build | Out-Null     # re-glob des nouvelles sources
    cmake --build build --config Release --target mangosd --parallel 8
}
