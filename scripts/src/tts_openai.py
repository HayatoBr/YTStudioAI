# scripts/src/tts_openai.py
import os
from pathlib import Path
from openai import OpenAI

def _sanitize_for_tts(text: str) -> str:
    # Remove marcador de pausa (ele é só para ritmo do roteiro)
    return text.replace("[PAUSA_FINAL]", "").strip() + "\n"

def generate_tts_mp3(
    text: str,
    out_path: str,
    model: str = "gpt-4o-mini-tts",
    voice: str = "cedar",
    speed: float = 0.98,  # leve desaceleração para evitar corte de fonema final
) -> str:
    """Gera narração em MP3 usando OpenAI TTS (SDK compatível)."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY não encontrada. Defina a variável de ambiente antes de rodar.")

    client = OpenAI(api_key=api_key)

    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    clean_text = _sanitize_for_tts(text)

    audio = client.audio.speech.create(
        model=model,
        voice=voice,
        input=clean_text,
        speed=speed,
    )

    data = None
    if hasattr(audio, "read"):
        data = audio.read()
    elif hasattr(audio, "iter_bytes"):
        data = b"".join(list(audio.iter_bytes()))
    elif hasattr(audio, "content"):
        data = audio.content
    else:
        try:
            data = bytes(audio)
        except Exception as e:
            raise RuntimeError(f"Resposta de TTS inesperada: {type(audio)}") from e

    out_file.write_bytes(data)
    return str(out_file)
