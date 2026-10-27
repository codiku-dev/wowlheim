# Lance tout ce qu'il faut pour jouer avec les bots (serveur de TEST), puis le client WoW.
# Ne relance que ce qui ne tourne pas deja. Raccourci bureau : « Wowlheim - test bots ».
#   1. serveur de test (realmd 3725 + mangosd_bots 8086)   2. modele Gemma 4 12B dans LM Studio (seul)
#   3. pont LLM (127.0.0.1:5005)                             4. client WoW (C:\Wowlheim\bots\client, fenetre)
$ErrorActionPreference = 'Continue'
$repo = Split-Path $PSScriptRoot -Parent
$run = 'C:\Wowlheim\bots\run'
$client = 'C:\Wowlheim\bots\client'
$lms = Join-Path $env:USERPROFILE '.lmstudio\bin\lms.exe'
$model = 'google/gemma-4-12b-qat'
$Host.UI.RawUI.WindowTitle = 'Wowlheim - test bots'

function Etape($t) { Write-Host "`n== $t" -ForegroundColor Cyan }

Etape 'MySQL'
if (-not (Get-Process mysqld -ErrorAction SilentlyContinue)) {
    Write-Host 'MySQL ne tourne pas : lance-le d''abord (mysqld --defaults-file=C:\Wowlheim\mysql\my.ini).' -ForegroundColor Red
    Read-Host 'Entree pour fermer'; exit 1
}
Write-Host 'OK'

Etape 'Serveur de test des bots'
$demarre = $false
if (Get-Process mangosd_bots -ErrorAction SilentlyContinue) { Write-Host 'deja en marche' }
else {
    Start-Process python -ArgumentList '-I', 'bots/server/run_server.py' -WorkingDirectory $repo -WindowStyle Minimized
    $demarre = $true
    Write-Host 'demarrage (fenetre reduite « python »)...'
}

Etape "Modele LLM ($model, seul en memoire)"
if (Test-Path $lms) {
    $ps = & $lms ps 2>&1 | Out-String
    if ($ps -notmatch [regex]::Escape($model)) {
        & $lms unload --all 2>&1 | Out-Null
        & $lms load $model -y --context-length 8192 2>&1 | Select-Object -Last 1
    } else { Write-Host 'deja charge' }
} else { Write-Host 'lms introuvable : charge le modele a la main dans LM Studio' -ForegroundColor Yellow }

Etape 'Pont LLM (127.0.0.1:5005)'
try { Invoke-RestMethod http://127.0.0.1:5005/health -TimeoutSec 2 | Out-Null; Write-Host 'deja en marche' }
catch {
    Start-Process python -ArgumentList '-I', 'bots/llm_bridge/bridge.py' -WorkingDirectory $repo -WindowStyle Minimized
    Write-Host 'demarre (fenetre reduite « python »)'
}

if ($demarre) {
    Etape 'Attente du monde (1 a 2 min)'
    $out = Join-Path $run 'mangosd.out'
    for ($i = 0; $i -lt 300; $i += 5) {
        Start-Sleep -Seconds 5
        if ((Test-Path $out) -and (Select-String -Path $out -Pattern 'World initialized' -Quiet)) { break }
        if (-not (Get-Process mangosd_bots -ErrorAction SilentlyContinue)) { Write-Host 'le serveur s''est arrete, voir C:\Wowlheim\bots\run\mangosd.err' -ForegroundColor Red; Read-Host 'Entree pour fermer'; exit 1 }
        Write-Host -NoNewline '.'
    }
    Write-Host ' pret (les bots se connectent dans la minute qui suit)'
}

Etape 'Client WoW'
# Modeles et icones Valheim (bois, marteau...) : patch-3.MPQ suit celui du client de la session Valheim.
$mpqSrc = 'C:\Wowlheim\client_test\Data\patch-3.MPQ'
$mpqDst = Join-Path $client 'Data\patch-3.MPQ'
if ((Test-Path $mpqSrc) -and (-not (Test-Path $mpqDst) -or (Get-Item $mpqSrc).LastWriteTime -gt (Get-Item $mpqDst).LastWriteTime)) {
    if (Get-Process WoW -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$client*" }) {
        Write-Host 'patch-3.MPQ plus recent disponible : ferme le client des bots puis relance ce raccourci' -ForegroundColor Yellow
    } else { Copy-Item $mpqSrc $mpqDst -Force; Write-Host 'patch-3.MPQ (Valheim) mis a jour' }
}
Start-Process (Join-Path $client 'WoW.exe') -WorkingDirectory $client
Write-Host 'Royaume « Wowlheim Bots (test) », compte admin / admin.' -ForegroundColor Green
Write-Host 'Les bots tournent en arriere-plan (fenetres « python » reduites) ; tu peux fermer cette fenetre.'
Start-Sleep -Seconds 8
