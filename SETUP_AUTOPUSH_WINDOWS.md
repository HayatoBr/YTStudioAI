# YTStudioAI — Auto-push seguro para GitHub (Windows)

Este pacote cria 2 scripts:
- `tools/auto_push.ps1`: envia automaticamente alterações para a branch `dev`
- `tools/daily_backup.ps1`: cria um ZIP diário local como backup extra

## 1) Pré-requisitos
- Git instalado (git no PATH)
- Você já tem o repositório com `origin` configurado
- Você já fez login no GitHub (Token / Git Credential Manager / GitHub Desktop)

## 2) Copiar scripts para o projeto
Copie a pasta `tools/` para:
`C:\YTStudioAI\tools\`

## 3) Criar a branch dev e subir
No PowerShell:
```powershell
cd C:\YTStudioAI
git checkout -b dev
git push -u origin dev
```

Se a branch `dev` já existir:
```powershell
git checkout dev
git push -u origin dev
```

## 4) Teste manual do auto-push
1. Faça uma pequena alteração em qualquer arquivo (ex: README.md)
2. Rode:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\YTStudioAI\tools\auto_push.ps1"
```

Se estiver tudo OK, ele vai:
- detectar mudanças
- commitar com mensagem `auto: sync <data>`
- fazer push para `origin/dev`

## 5) Agendar no Task Scheduler (a cada 10 min)
Abra: **Agendador de Tarefas** → **Criar Tarefa...**

### Aba Geral
- Nome: `YTStudioAI Auto Push (dev)`
- Marque: **Executar somente quando o usuário estiver conectado** (mais simples)
  > Se marcar "Executar estando o usuário logado ou não", pode pedir senha do Windows.

### Aba Disparadores (Triggers)
- Novo... → Iniciar a tarefa: **Em um agendamento**
- Configurar: **Diariamente**
- Repetir a tarefa a cada: **10 minutos**
- Por uma duração de: **Indefinidamente**

### Aba Ações
- Novo... → Ação: **Iniciar um programa**
- Programa/script: `powershell.exe`
- Adicionar argumentos:
  ```text
  -NoProfile -ExecutionPolicy Bypass -File "C:\YTStudioAI\tools\auto_push.ps1"
  ```

### Aba Condições (opcional)
- Desmarque: "Iniciar a tarefa somente se o computador estiver na alimentação CA"
  (se for notebook e você quiser que rode na bateria)

## 6) Backup diário local (opcional)
Crie outra tarefa:

- Nome: `YTStudioAI Daily Backup`
- Trigger: diariamente (ex: 03:00)
- Ação:
  - Programa: `powershell.exe`
  - Argumentos:
    ```text
    -NoProfile -ExecutionPolicy Bypass -File "C:\YTStudioAI\tools\daily_backup.ps1"
    ```

Backups em: `C:\YTStudioAI_backups\YTStudioAI_YYYY-MM-DD.zip`

## Dicas de segurança
- Trabalhe sempre na branch `dev` durante correções.
- Só faça merge para `main` quando o pipeline LONG estiver estável.
- Se der erro, você pode voltar para um commit anterior:
  ```powershell
  git log --oneline
  git reset --hard <HASH>
  git push --force
  ```
