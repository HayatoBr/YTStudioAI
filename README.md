# ARQUIVO OCULTO — PROJETO COMPLETO (COM ANIMAÇÃO VIA FFMPEG)

Este projeto já vem com:
- Estrutura completa
- Render local com FFmpeg
- Animação automática estilo documental (zoom/parallax leve)
- Trilha sonora aleatória
- Watermark automática
- Geração de Long 16:9 + Long 9:16

Você só precisa:
1) Colocar músicas em assets/music/
2) Colocar watermark.png em assets/watermark/
3) Ter imagens + áudio de voz
4) Rodar os comandos


---

## Legendas estilo CapCut (SRT + ASS)

Este projeto gera legendas **a partir do texto da narração** (arquivo .txt) e sincroniza de forma **estimada** com base na duração do áudio (via FFprobe).

### Gerar legendas (recomendado)
```powershell
python main.py --make-subs --text "C:\ArquivoOculto\texto.txt" --audio "C:\ArquivoOculto\voice.mp3" --format short --out "outputs\subtitles"
```

Saída:
- `outputs/subtitles/captions.srt`
- `outputs/subtitles/captions.ass`

### Informar duração manualmente (se quiser)
```powershell
python main.py --make-subs --text texto.txt --duration 60 --format short
```


---
## Shorts automáticos (Teaser + Curiosidades)

O projeto agora gera **dois tipos de Shorts** a partir do mesmo roteiro:

### 1) Teaser (20s)
- Serve como chamada para o vídeo longo
- Usa as primeiras frases mais fortes

### 2) Curiosidade (30s)
- Conteúdo independente, voltado ao nicho
- Ajuda a atrair público novo

### Gerar Shorts
```powershell
python main.py --make-shorts --text roteiro.txt
```

Saída:
- `outputs/shorts/teaser/`
- `outputs/shorts/curiosidades/`
---

## OpenAI (roteiro + imagens + voz) com guard-rails

Este projeto usa:
- **Texto/roteiro** via Responses API
- **Imagens** via gpt-image-1
- **Voz (TTS)** via Audio Speech API

Docs oficiais:
- Imagens: https://developers.openai.com/api/docs/guides/image-generation/
- TTS: https://developers.openai.com/api/docs/guides/text-to-speech/

### 1) Configure sua chave
Copie `.env.example` para `.env` e coloque sua chave `OPENAI_API_KEY`.

### 2) Crie um arquivo de fatos (1 por linha)
Ex: `fatos.txt`

### 3) Rode a geração do pack do Long
```powershell
python main.py --openai-long --case-title "CASO ARQUIVADO: ..." --facts "C:\ArquivoOculto\fatos.txt" --minutes 5.5 --out "outputs"
```

Saída:
`outputs/openai/long_pack/`
- script.json (roteiro + storyboard)
- narration.txt
- voice.mp3
- images/scene_001.png ...
- subtitles/captions.srt e captions.ass
- shorts/ (teaser_20s, teaser_40s, curiosity_30s)

### Proteções anti-custo
Você pode limitar pelo `.env`:
- `OPENAI_MAX_IMAGE_COUNT`
- `OPENAI_MAX_TTS_CHARS`

## UM comando (run-all) — automação completa

### Simular sem gastar nada (recomendado primeiro)
```powershell
python main.py --run-all --dry-run --case-title "CASO ARQUIVADO: exemplo" --facts "fatos.txt" --minutes 5.5
```

### Rodar de verdade (gera TUDO)
```powershell
python main.py --run-all --case-title "CASO ARQUIVADO: exemplo" --facts "fatos.txt" --minutes 5.5
```

Saídas finais:
- `outputs/final/long/16x9/long_master_16x9.mp4`
- `outputs/final/long/9x16/long_derived_9x16.mp4`
- `outputs/final/shorts/teaser_20s/teaser_20s.mp4` (se tiver shorts)
- `outputs/final/shorts/curiosity_30s/curiosity_30s.mp4` (se tiver shorts)
