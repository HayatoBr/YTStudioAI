# Fallback grátis (Ollama + Wikipedia RAG-lite)

Este patch adiciona um **provedor de roteiro** com fallback local:

- **AO_PROFILE=publish** → força **OpenAI** (qualidade máxima)
- **AO_PROFILE=dev** (padrão) → usa **Ollama** local (grátis) para roteiro
  - Opcional: **AO_RAG_ENABLED=1** para puxar um “dossiê” do **Wikipedia** e reduzir temas fictícios.

## 1) Instalar Ollama (Windows)

1. Instale o Ollama.
2. Abra o terminal e baixe um modelo (exemplo):
   - `ollama pull llama3.2:latest`

> O serviço do Ollama precisa estar rodando (porta padrão 11434).

## 2) Variáveis de ambiente (PowerShell)

**Modo dev (barato/grátis):**
```powershell
$env:AO_PROFILE="dev"
$env:AO_SCRIPT_BACKEND="ollama"
$env:AO_OLLAMA_MODEL="llama3.2:latest"
$env:AO_RAG_ENABLED="1"
$env:AO_RAG_LANGS="pt,en"
```

**Modo publish (qualidade máxima OpenAI):**
```powershell
$env:AO_PROFILE="publish"
# (ignora AO_SCRIPT_BACKEND e força OpenAI)
```

## 3) Teste rápido

```powershell
python main.py --long-only --minutes 2.0
```

## Observações

- O RAG-lite usa somente o **extract introdutório** do Wikipedia (portanto é leve).
- O prompt força o modelo a **não inventar**: se não estiver nas fontes, ele deve omitir.
- Ainda assim, revise o conteúdo antes de publicar.
