# tools/auto_push.ps1
# Auto-sync seguro do YTStudioAI para o GitHub (branch dev)
# - Só comita se houver mudanças
# - Faz pull --rebase antes de comitar (evita divergência)
# - Trabalha APENAS na branch de trabalho (dev)
# Requisitos: Git instalado e 'origin' configurado

$ErrorActionPreference = "Stop"

# Ajuste se seu projeto estiver em outro caminho:
$RepoPath = "C:\YTStudioAI"
$Branch   = "dev"

Set-Location $RepoPath

# Garante que a pasta é um repositório git
if (-not (Test-Path ".git")) {
  Write-Host "ERRO: .git nao encontrado em $RepoPath"
  exit 2
}

# Garante que o remote origin existe
$origin = git remote | Select-String -Pattern "^origin$"
if (-not $origin) {
  Write-Host "ERRO: remote 'origin' nao configurado. Rode: git remote add origin <URL>"
  exit 3
}

# Troca para a branch de trabalho (cria se nao existir localmente)
$branches = git branch --list $Branch
if (-not $branches) {
  git checkout -b $Branch
} else {
  git checkout $Branch | Out-Null
}

# Atualiza com o remoto antes de comitar (melhor pratica)
try {
  git fetch origin | Out-Null
  git pull --rebase origin $Branch | Out-Null
} catch {
  Write-Host "AVISO: pull/rebase falhou. Continuando mesmo assim..."
}

# Se nao houver mudancas, sai
$status = git status --porcelain
if ([string]::IsNullOrWhiteSpace($status)) {
  Write-Host "OK: sem mudancas para enviar."
  exit 0
}

# Commit automatico com timestamp
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
git add -A

try {
  git commit -m "auto: sync $stamp" | Out-Null
} catch {
  # Caso nada para commitar (corrida rara), sai com sucesso
  Write-Host "OK: nada novo para commitar."
  exit 0
}

# Push
git push origin $Branch
Write-Host "OK: enviado para origin/$Branch em $stamp"
