from datetime import datetime, timezone
from config import AUDIO_DIR, PODCAST_AUTHOR
from jobs import write_job


def run_pipeline(ep_id: str, ep_data: dict, url: str = None, raw_text: str = None) -> None:
    """Full background pipeline: ingest → transcript → synthesize → save episode."""
    from podcast import Episode, save_episode

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

        filename = f"{ep_id}.mp3"
        output_path = AUDIO_DIR / filename

        from synthesize import synthesize
        duration_secs = synthesize(transcript, output_path, job_id=ep_id)

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
        write_job(ep_id, status="error", error=str(exc))
