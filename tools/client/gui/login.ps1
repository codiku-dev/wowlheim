# login.ps1 : ecran de connexion -> (assistant royaume si present) -> choix du personnage -> Enter World.
# Le mot de passe est lu dans C:\Wowlheim\run\test_account2.txt, ecrit dans un fichier temporaire supprime aussitot, jamais affiche.
param([string]$Shots = "$PSScriptRoot\shots", [string]$Tag = 'x')
$py = "$PSScriptRoot\..\.venv\Scripts\python.exe"; $t = "$PSScriptRoot\type.py"
$tmp = Join-Path $env:TEMP 'wl_pw.tmp'
$l = Get-Content C:\Wowlheim\run\test_account2.txt
$pw = ($l | Where-Object { $_ -like 'password*' }) -replace '^password\s*[:=]?\s*', ''
[IO.File]::WriteAllText($tmp, $pw)
try {
  & $py $t --click 520,402 --text WLTEST2 --key tab --textfile $tmp --key enter --sleep 6 --shot "$Shots\${Tag}_a_after_login.png"
} finally { Remove-Item $tmp -ErrorAction SilentlyContinue }
