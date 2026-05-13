import time
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


def synthesize(transcript: str, output_path: Path, job_id: str = None) -> float:
    """Synthesize transcript to MP3. Returns duration in seconds."""
    pipeline = _get_pipeline()
    chunks = _chunk_text(transcript, KOKORO_CHUNK_WORDS)

    if job_id:
        from jobs import write_job
        write_job(job_id, status="synthesizing", chunk_current=0, chunk_total=len(chunks))

    all_audio: list[np.ndarray] = []
    t_start = time.time()
    for i, chunk in enumerate(chunks, 1):
        print(f"  Chunk {i}/{len(chunks)}...", end=" ", flush=True)
        t_chunk = time.time()
        for _, _, audio in pipeline(chunk, voice=KOKORO_VOICE, speed=KOKORO_SPEED):
            arr = audio.numpy() if hasattr(audio, "numpy") else np.array(audio)
            all_audio.append(arr)
        print(f"{time.time() - t_chunk:.1f}s")
        if job_id:
            from jobs import write_job
            write_job(job_id, chunk_current=i)

    combined = np.concatenate(all_audio) if len(all_audio) > 1 else all_audio[0]
    audio_duration = len(combined) / KOKORO_SAMPLE_RATE
    wall_time = time.time() - t_start
    rtf = audio_duration / wall_time  # real-time factor: >1 means faster than realtime

    wav_path = output_path.with_suffix(".wav")
    sf.write(str(wav_path), combined, KOKORO_SAMPLE_RATE)

    audio_seg = AudioSegment.from_wav(str(wav_path))
    audio_seg.export(str(output_path), format="mp3", bitrate=MP3_BITRATE)
    wav_path.unlink()

    print(f"  Synthesis: {wall_time:.1f}s wall time → {audio_duration:.1f}s audio ({rtf:.1f}x real-time)")
    return audio_duration
