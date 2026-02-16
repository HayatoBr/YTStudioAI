# tools/daily_backup.ps1
# Backup ZIP local do YTStudioAI (sem pastas/arquivos gerados comuns)
# Recomendado: rodar 1x por dia (Task Scheduler)

$ErrorActionPreference = "Stop"

$RepoPath   = "C:\YTStudioAI"
$BackupDir  = "C:\YTStudioAI_backups"

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

$date = Get-Date -Format "yyyy-MM-dd"
$zipPath = Join-Path $BackupDir ("YTStudioAI_" + $date + ".zip")

# Lista de exclusoes (ajuste se necessario)
$exclude = @(
  ".git",
  "output",
  "__pycache__",
  ".venv",
  "venv",
  "env",
  ".pytest_cache",
  ".mypy_cache",
  ".ruff_cache"
)

# Cria lista temporaria de arquivos a incluir
$tmp = Join-Path $env:TEMP ("ytstudioai_backup_list_" + [guid]::NewGuid().ToString() + ".txt")

Get-ChildItem -Path $RepoPath -Recurse -File | ForEach-Object {
  $full = $_.FullName
  $rel  = $full.Substring($RepoPath.Length).TrimStart("\")
  foreach ($ex in $exclude) {
    if ($rel -like "$ex\*" -or $rel -eq $ex) { return }
  }
  # exclui midias grandes por padrao (geradas)
  if ($rel -match "\.(mp4|mov|mkv|webm|mp3|wav|m4a|png|jpg|jpeg|webp|ass|srt)$") { return }
  $full | Out-File -FilePath $tmp -Append -Encoding utf8
}

if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::Open($zipPath, "Create")

Get-Content $tmp | ForEach-Object {
  $file = $_
  if (Test-Path $file) {
    $entry = $file.Substring($RepoPath.Length).TrimStart("\") -replace "\\","/"
    [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $file, $entry) | Out-Null
  }
}

$zip.Dispose()
Remove-Item $tmp -Force

Write-Host "OK: backup criado em $zipPath"
