from pathlib import Path
import numpy as np
import soundfile as sf
from pydub import AudioSegment
from config import KOKORO_VOICE, KOKORO_SPEED, KOKORO_SAMPLE_RATE, KOKORO_CHUNK_WORDS, MP3_BITRATE

_pipeline = None


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        import torch
        from kokoro import KPipeline
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Loading Kokoro on {device}...")
        _pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
    return _pipeline


def _chunk_text(text: str, max_words: int) -> list[str]:
    """Split text into chunks at sentence boundaries, respecting max_words."""
    import re
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks = []
    current: list[str] = []
    count = 0
    for sentence in sentences:
        words = len(sentence.split())
        if count + words > max_words and current:
            chunks.append(" ".join(current))
            current = [sentence]
            count = words
        else:
            current.append(sentence)
            count += words
    if current:
        chunks.append(" ".join(current))
    return chunks


def synthesize(transcript: str, output_path: Path) -> float:
    """Synthesize transcript to MP3. Returns duration in seconds."""
    pipeline = _get_pipeline()
    chunks = _chunk_text(transcript, KOKORO_CHUNK_WORDS)

    all_audio: list[np.ndarray] = []
    for i, chunk in enumerate(chunks, 1):
        print(f"  Synthesizing chunk {i}/{len(chunks)}...")
        for _, _, audio in pipeline(chunk, voice=KOKORO_VOICE, speed=KOKORO_SPEED):
            # audio is a torch tensor; convert to numpy
            arr = audio.numpy() if hasattr(audio, "numpy") else np.array(audio)
            all_audio.append(arr)

    combined = np.concatenate(all_audio) if len(all_audio) > 1 else all_audio[0]

    wav_path = output_path.with_suffix(".wav")
    sf.write(str(wav_path), combined, KOKORO_SAMPLE_RATE)

    audio_seg = AudioSegment.from_wav(str(wav_path))
    audio_seg.export(str(output_path), format="mp3", bitrate=MP3_BITRATE)
    wav_path.unlink()

    return len(combined) / KOKORO_SAMPLE_RATE
