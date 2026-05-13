#!/usr/bin/env python3
import argparse
import multiprocessing
import sys
from datetime import datetime, timezone
from pathlib import Path

from config import AUDIO_DIR, PODCAST_AUTHOR
from podcast import Episode, make_episode_id, save_episode, load_episodes, delete_episode, find_duplicate_url
from ingest import check_x_session


def cmd_add(args):
    from ingest import fetch_text
    from transcript import clean_for_tts
    from synthesize import synthesize

    # --- Ingest ---
    if args.url:
        dup = find_duplicate_url(args.url)
        if dup:
            print(f"Already in feed: \"{dup.title}\" (added {dup.pub_date[:10]}). Use --force to add anyway.")
            if not getattr(args, "force", False):
                sys.exit(0)
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
    print()

    # --- Synthesize (background) ---
    filename = f"{episode_id}.mp3"
    output_path = AUDIO_DIR / filename
    ep_data = dict(
        id=episode_id, title=title, description=description,
        filename=filename, pub_date=datetime.now(timezone.utc).isoformat(),
        source_url=args.url or "",
    )

    print("=== Synthesizing audio in background ===")
    print(f"  Episode ID: {episode_id[:8]}")
    print(f"  Run 'narrate list' to see it once synthesis completes.\n")

    proc = multiprocessing.Process(
        target=_synthesize_and_save,
        args=(transcript, output_path, ep_data),
        daemon=False,
    )
    proc.start()


def _synthesize_and_save(transcript: str, output_path: Path, ep_data: dict):
    """Runs in a background process: synthesize, tag, and save the episode."""
    from synthesize import synthesize
    from podcast import Episode, save_episode
    import json

    try:
        duration_secs = synthesize(transcript, output_path)
        file_size = output_path.stat().st_size

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
        except Exception as e:
            print(f"Warning: could not write ID3 tags: {e}")

        ep = Episode(
            **ep_data,
            duration_secs=duration_secs,
            file_size_bytes=file_size,
        )
        save_episode(ep)

        mins = int(duration_secs // 60)
        secs = int(duration_secs % 60)
        print(f"\n✓ Background synthesis complete: \"{ep_data['title']}\" ({mins}m{secs:02d}s)")
    except Exception as e:
        print(f"\n✗ Background synthesis failed: {e}", file=sys.stderr)


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

    ep = _resolve_episode(episodes, args.episode)

    audio_file = AUDIO_DIR / ep.filename
    delete_episode(ep.id)

    if audio_file.exists():
        audio_file.unlink()
        print(f"✓ Deleted: \"{ep.title}\" (audio file removed)")
    else:
        print(f"✓ Deleted: \"{ep.title}\" (audio file was already missing)")


def _resolve_episode(episodes, target):
    if target.isdigit():
        idx = int(target) - 1
        if 0 <= idx < len(episodes):
            return episodes[idx]
        print(f"Error: no episode #{target}.", file=sys.stderr)
        sys.exit(1)
    matches = [e for e in episodes if e.id.startswith(target)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"Error: ambiguous ID prefix '{target}'.", file=sys.stderr)
    else:
        print(f"Error: no episode matching '{target}'.", file=sys.stderr)
    sys.exit(1)


def cmd_edit(args):
    from dataclasses import asdict
    import json

    episodes = load_episodes()
    if not episodes:
        print("No episodes.")
        return

    ep = _resolve_episode(episodes, args.episode)

    if not args.title and not args.description:
        print("Nothing to change — provide --title and/or --description.")
        return

    if args.title:
        ep.title = args.title
    if args.description:
        ep.description = args.description

    with open(EPISODES_FILE, "w") as f:
        json.dump([asdict(e) for e in episodes], f, indent=2)

    print(f"✓ Updated: \"{ep.title}\"")


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
    add_p.add_argument("--force", action="store_true", help="Add even if URL already exists in feed")

    # --- list ---
    sub.add_parser("list", help="List all episodes")

    # --- delete ---
    del_p = sub.add_parser("delete", help="Delete an episode by number or ID prefix")
    del_p.add_argument("episode", help="Episode number (from list) or ID prefix")

    # --- edit ---
    edit_p = sub.add_parser("edit", help="Update an episode's title or description")
    edit_p.add_argument("episode", help="Episode number (from list) or ID prefix")
    edit_p.add_argument("--title", help="New title")
    edit_p.add_argument("--description", help="New description")

    # --- check-x ---
    sub.add_parser("check-x", help="Check how many days remain on the saved X.com session")

    args = parser.parse_args()

    if args.command == "add":
        cmd_add(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "delete":
        cmd_delete(args)
    elif args.command == "edit":
        cmd_edit(args)
    elif args.command == "check-x":
        check_x_session()


if __name__ == "__main__":
    main()
