# tools/auto_push.ps1
# Auto-sync seguro do YTStudioAI para o GitHub (branch dev)
# - TRAVA EXTRA: NÃO roda se detectar render/FFmpeg em execução
# - Comita primeiro se houver mudanças
# - Depois faz pull --rebase e push

$ErrorActionPreference = "Stop"

$RepoPath = "C:\YTStudioAI"
$Branch   = "dev"

function Test-RenderRunning {
    param(
        [string]$RepoPath,
        [int]$ProgressFreshSeconds = 300
    )

    $now = Get-Date

    # Verifica arquivos de progresso do FFmpeg
    $patterns = @(
        "$RepoPath\output\shorts\.ffmpeg_progress_*.txt",
        "$RepoPath\output\longs\.ffmpeg_progress_*.txt",
        "$RepoPath\output\.ffmpeg_progress_*.txt"
    )

    foreach ($pattern in $patterns) {
        $files = Get-ChildItem -Path $pattern -ErrorAction SilentlyContinue
        foreach ($f in $files) {
            $age = ($now - $f.LastWriteTime).TotalSeconds
            if ($age -lt $ProgressFreshSeconds) {
                return $true
            }
        }
    }

    # Verifica ffmpeg rodando
    if (Get-Process -Name "ffmpeg" -ErrorAction SilentlyContinue) {
        return $true
    }

    # Verifica python rodando com projeto
    try {
        $py = Get-CimInstance Win32_Process -Filter "name='python.exe' OR name='pythonw.exe'" -ErrorAction SilentlyContinue
        foreach ($p in $py) {
            $cmd = ($p.CommandLine | Out-String).ToLower()
            if ($cmd -match "c:\\ytstudioai\\main\.py" -or
                $cmd -match "scripts\\src\\renderer\.py" -or
                $cmd -match "scripts\\src\\orchestrator\.py") {
                return $true
            }
        }
    } catch {}

    return $false
}

if (Test-RenderRunning -RepoPath $RepoPath) {
    Write-Host "TRAVA: render/FFmpeg detectado. Auto-push cancelado."
    exit 0
}

Set-Location $RepoPath

if (-not (Test-Path ".git")) {
    Write-Host "ERRO: .git nao encontrado."
    exit 2
}

if (-not (git remote | Select-String "^origin$")) {
    Write-Host "ERRO: remote 'origin' nao configurado."
    exit 3
}

$branches = git branch --list $Branch
if (-not $branches) {
    git checkout -b $Branch | Out-Null
} else {
    git checkout $Branch | Out-Null
}

$status = git status --porcelain
if (-not [string]::IsNullOrWhiteSpace($status)) {
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    git add -A
    git commit -m "auto: sync $stamp" | Out-Null
    Write-Host "OK: commit criado em $stamp"
} else {
    Write-Host "OK: sem mudancas locais."
}

try {
    git fetch origin | Out-Null
    git pull --rebase origin $Branch | Out-Null
} catch {
    Write-Host "AVISO: pull/rebase falhou. Continuando..."
}

git push origin $Branch | Out-Null
Write-Host "OK: push concluido para origin/$Branch"
