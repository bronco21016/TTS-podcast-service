#!/usr/bin/env python3
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from config import AUDIO_DIR, PODCAST_AUTHOR
from podcast import Episode, make_episode_id, save_episode, load_episodes, delete_episode


def cmd_add(args):
    from ingest import fetch_text
    from transcript import clean_for_tts
    from synthesize import synthesize

    # --- Ingest ---
    if args.url:
        print(f"Fetching {args.url} ...")
        title, raw_text = fetch_text(args.url)
    elif args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"Error: file not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        raw_text = file_path.read_text(encoding="utf-8").strip()
        title = args.title or file_path.stem.replace("-", " ").replace("_", " ").title()
    elif args.text:
        raw_text = args.text
        title = args.title or raw_text[:60].replace("\n", " ").strip() + "..."
    elif not sys.stdin.isatty():
        raw_text = sys.stdin.read().strip()
        title = args.title or raw_text[:60].replace("\n", " ").strip() + "..."
    else:
        print("Error: provide --url, --file, --text, or pipe text via stdin.", file=sys.stderr)
        sys.exit(1)

    if args.title:
        title = args.title

    source_label = args.url or (args.file and f"file: {args.file}") or "pasted text"
    description = args.description or f"Converted from: {source_label}"

    print(f"\nTitle: {title}")
    print(f"Raw text length: {len(raw_text):,} characters\n")

    # --- Transcript ---
    episode_id = make_episode_id()
    print("=== Cleaning transcript via Claude ===")
    transcript = clean_for_tts(title, raw_text, episode_id=episode_id)
    print(f"  Done — {len(transcript):,} characters saved to transcripts/{episode_id}.txt\n")

    # --- Synthesize ---
    filename = f"{episode_id}.mp3"
    output_path = AUDIO_DIR / filename

    print("=== Synthesizing audio ===")
    duration_secs = synthesize(transcript, output_path)
    file_size = output_path.stat().st_size

    # --- ID3 tags ---
    try:
        from mutagen.id3 import ID3, TIT2, TPE1, TDRC, ID3NoHeaderError
        try:
            tags = ID3(str(output_path))
        except ID3NoHeaderError:
            tags = ID3()
        tags.add(TIT2(encoding=3, text=title))
        tags.add(TPE1(encoding=3, text=PODCAST_AUTHOR))
        tags.add(TDRC(encoding=3, text=datetime.now().strftime("%Y")))
        tags.save(str(output_path))
    except Exception as e:
        print(f"Warning: could not write ID3 tags: {e}")

    # --- Save episode ---
    ep = Episode(
        id=episode_id,
        title=title,
        description=description,
        filename=filename,
        pub_date=datetime.now(timezone.utc).isoformat(),
        duration_secs=duration_secs,
        file_size_bytes=file_size,
    )
    save_episode(ep)

    mins = int(duration_secs // 60)
    secs = int(duration_secs % 60)
    print(f"\n✓ Episode added: \"{title}\"")
    print(f"  Duration : {mins}m {secs}s")
    print(f"  File     : {output_path}")
    print(f"  Size     : {file_size / 1024 / 1024:.1f} MB")


def cmd_list(args):
    episodes = load_episodes()
    if not episodes:
        print("No episodes.")
        return
    for i, ep in enumerate(episodes, 1):
        mins = int(ep.duration_secs // 60)
        secs = int(ep.duration_secs % 60)
        date = ep.pub_date[:10]
        print(f"  {i:>2}.  {ep.title}")
        print(f"        {date}  {mins}m{secs:02d}s  {ep.file_size_bytes / 1024 / 1024:.1f} MB  [{ep.id[:8]}]")


def cmd_delete(args):
    episodes = load_episodes()
    if not episodes:
        print("No episodes.")
        return

    target = args.episode
    ep = None

    # Match by number (1-indexed)
    if target.isdigit():
        idx = int(target) - 1
        if 0 <= idx < len(episodes):
            ep = episodes[idx]
        else:
            print(f"Error: no episode #{target}.", file=sys.stderr)
            sys.exit(1)
    else:
        # Match by ID prefix
        matches = [e for e in episodes if e.id.startswith(target)]
        if len(matches) == 1:
            ep = matches[0]
        elif len(matches) > 1:
            print(f"Error: ambiguous ID prefix '{target}', matches multiple episodes.", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"Error: no episode matching '{target}'.", file=sys.stderr)
            sys.exit(1)

    audio_file = AUDIO_DIR / ep.filename
    delete_episode(ep.id)

    if audio_file.exists():
        audio_file.unlink()
        print(f"✓ Deleted: \"{ep.title}\" (audio file removed)")
    else:
        print(f"✓ Deleted: \"{ep.title}\" (audio file was already missing)")


def main():
    parser = argparse.ArgumentParser(description="TTS Podcast CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # --- add ---
    add_p = sub.add_parser("add", help="Convert an article or text to a podcast episode")
    source = add_p.add_mutually_exclusive_group()
    source.add_argument("--url", help="URL of the article to fetch")
    source.add_argument("--file", help="Path to a .txt file containing the article text")
    source.add_argument("--text", help="Raw text to convert")
    add_p.add_argument("--title", help="Episode title override")
    add_p.add_argument("--description", help="Episode description for RSS feed")

    # --- list ---
    sub.add_parser("list", help="List all episodes")

    # --- delete ---
    del_p = sub.add_parser("delete", help="Delete an episode by number or ID prefix")
    del_p.add_argument("episode", help="Episode number (from list) or ID prefix")

    args = parser.parse_args()

    if args.command == "add":
        cmd_add(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "delete":
        cmd_delete(args)


if __name__ == "__main__":
    main()
