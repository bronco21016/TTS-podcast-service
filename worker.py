from datetime import datetime, timezone
from config import AUDIO_DIR, PODCAST_AUTHOR
from jobs import write_job, acquire_synthesis_lock, release_synthesis_lock


def _description_excerpt(transcript: str, max_chars: int = 500) -> str:
    if len(transcript) <= max_chars:
        return transcript
    chunk = transcript[:max_chars]
    last_end = max(chunk.rfind('. '), chunk.rfind('? '), chunk.rfind('! '))
    cut = last_end + 1 if last_end > 200 else max_chars
    return chunk[:cut].rstrip() + '…'


def run_pipeline(ep_id: str, ep_data: dict, url: str = None, raw_text: str = None) -> None:
    """Full background pipeline: ingest → transcript → synthesize → save episode."""
    from podcast import Episode, save_episode

    filename = f"{ep_id}.mp3"
    output_path = AUDIO_DIR / filename
    lock_file = None

    try:
        if url:
            write_job(ep_id, status="ingesting")
            from ingest import fetch_text
            real_title, raw_text = fetch_text(url)
            ep_data["title"] = real_title
            write_job(ep_id, title=real_title)

        write_job(ep_id, status="transcribing")
        from transcript import clean_for_tts
        transcript = clean_for_tts(ep_data["title"], raw_text, episode_id=ep_id)

        # Use transcript as show notes (truncated to first paragraph/500 chars)
        ep_data["description"] = _description_excerpt(transcript)

        # Serialize GPU access — block until any running synthesis finishes
        write_job(ep_id, status="queued")
        lock_file = acquire_synthesis_lock()

        from synthesize import synthesize
        duration_secs = synthesize(transcript, output_path, job_id=ep_id)

        release_synthesis_lock(lock_file)
        lock_file = None

        try:
            from mutagen.id3 import ID3, TIT2, TPE1, TDRC, ID3NoHeaderError
            try:
                tags = ID3(str(output_path))
            except ID3NoHeaderError:
                tags = ID3()
            tags.add(TIT2(encoding=3, text=ep_data["title"]))
            tags.add(TPE1(encoding=3, text=PODCAST_AUTHOR))
            tags.add(TDRC(encoding=3, text=datetime.now().strftime("%Y")))
            tags.save(str(output_path))
        except Exception:
            pass

        file_size = output_path.stat().st_size
        ep = Episode(
            id=ep_id,
            title=ep_data["title"],
            description=ep_data["description"],
            filename=filename,
            pub_date=ep_data["pub_date"],
            duration_secs=duration_secs,
            file_size_bytes=file_size,
            source_url=ep_data.get("source_url", ""),
        )
        save_episode(ep)

        mins = int(duration_secs // 60)
        secs = int(duration_secs % 60)
        write_job(ep_id, status="done", duration_label=f"{mins}m{secs:02d}s")

    except Exception as exc:
        if lock_file is not None:
            release_synthesis_lock(lock_file)
        # Remove any partial audio files left by a failed synthesis
        for path in [output_path, output_path.with_suffix(".wav")]:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
        write_job(ep_id, status="error", error=str(exc))
