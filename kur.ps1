# HARMAN kurulum (yeni bilgisayar ya da bu bilgisayar). Tekrar çalıştırmak güvenlidir.
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root
$CodexVersion = "0.160.0"

Write-Host "1/5 Python ortami..." -ForegroundColor Cyan
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    if (Get-Command py -ErrorAction SilentlyContinue) { py -3.12 -m venv .venv } else { python -m venv .venv }
}
& .venv\Scripts\python.exe -m pip install -q --upgrade pip
& .venv\Scripts\python.exe -m pip install -q -r requirements.txt

Write-Host "2/5 Sabit Codex surumu ($CodexVersion)..." -ForegroundColor Cyan
$codexDir = Join-Path $Root "tools\codex-$CodexVersion"
$codexExe = Join-Path $codexDir "node_modules\@openai\codex-win32-x64\vendor\x86_64-pc-windows-msvc\bin\codex.exe"
if (-not (Test-Path $codexExe)) {
    New-Item -ItemType Directory -Force $codexDir | Out-Null
    Push-Location $codexDir; npm install --no-audit --no-fund --silent "@openai/codex@$CodexVersion"; Pop-Location
}

Write-Host "3/5 Son veri yedegi GitHub'dan..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force (Join-Path $Root "data"), (Join-Path $Root "logs") | Out-Null
if (-not (Test-Path "data\harman.db")) { & .venv\Scripts\python.exe scripts\yedekle.py --geri-al }

Write-Host "4/5 Testler..." -ForegroundColor Cyan
& .venv\Scripts\python.exe -m pytest -q

Write-Host "5/5 15 dakikalik otomatik gorev..." -ForegroundColor Cyan
$action = New-ScheduledTaskAction -Execute (Join-Path $Root ".venv\Scripts\pythonw.exe") -Argument "scripts\harman_tur.py" -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes 15)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 25)
Register-ScheduledTask -TaskName "HARMAN Bot" -Action $action -Trigger $trigger -Settings $settings -Description "HARMAN kagit-para kopya trader botu (15 dk). Gercek emir yok." -Force | Out-Null

Write-Host ""
Write-Host "TAMAM." -ForegroundColor Green
if (-not (Test-Path ".env")) { Write-Host "UNUTMA: .env dosyasina TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID yaz." -ForegroundColor Yellow }
Write-Host "AI girisleri (bir kez): 'claude' yazip giris yap; ChatGPT icin:" -ForegroundColor Yellow
Write-Host "  & `"$codexExe`" login"
