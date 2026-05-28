import json
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from feedgen.feed import FeedGenerator
from config import (
    EPISODES_FILE, AUDIO_DIR, BASE_URL,
    PODCAST_TITLE, PODCAST_AUTHOR, PODCAST_EMAIL,
    PODCAST_DESCRIPTION, PODCAST_LANGUAGE,
)


@dataclass
class Episode:
    id: str
    title: str
    description: str
    filename: str
    pub_date: str          # ISO 8601
    duration_secs: float
    file_size_bytes: int
    source_url: str = ""   # original URL, empty for text/file input


def make_episode_id() -> str:
    return str(uuid.uuid4())


def load_episodes() -> list[Episode]:
    if not EPISODES_FILE.exists():
        return []
    with open(EPISODES_FILE) as f:
        data = json.load(f)
    # source_url may be missing in older episodes — default to ""
    return [Episode(**{**ep, "source_url": ep.get("source_url", "")}) for ep in data]


def find_duplicate_url(url: str) -> "Episode | None":
    if not url:
        return None
    for ep in load_episodes():
        if ep.source_url and ep.source_url == url:
            return ep
    return None


def save_episode(ep: Episode) -> None:
    episodes = load_episodes()
    episodes.append(ep)
    with open(EPISODES_FILE, "w") as f:
        json.dump([asdict(e) for e in episodes], f, indent=2)


def delete_episode(episode_id: str) -> None:
    episodes = [e for e in load_episodes() if e.id != episode_id]
    with open(EPISODES_FILE, "w") as f:
        json.dump([asdict(e) for e in episodes], f, indent=2)


def _format_duration(secs: float) -> str:
    secs = int(secs)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def generate_rss() -> bytes:
    episodes = load_episodes()

    fg = FeedGenerator()
    fg.load_extension("podcast")

    feed_url = f"{BASE_URL}/feed.rss"
    fg.id(feed_url)
    fg.title(PODCAST_TITLE)
    fg.author({"name": PODCAST_AUTHOR, "email": PODCAST_EMAIL})
    fg.link(href=feed_url, rel="self")
    fg.language(PODCAST_LANGUAGE)
    fg.description(PODCAST_DESCRIPTION)
    fg.image(f"{BASE_URL}/cover.jpg", PODCAST_TITLE, BASE_URL)  # standard RSS <image>
    fg.podcast.itunes_author(PODCAST_AUTHOR)
    fg.podcast.itunes_explicit("no")
    fg.podcast.itunes_category("Technology")
    fg.podcast.itunes_image(f"{BASE_URL}/cover.jpg")

    for ep in sorted(episodes, key=lambda e: e.pub_date, reverse=True):
        fe = fg.add_entry()
        fe.id(ep.id)
        fe.title(ep.title)
        fe.description(ep.description)

        pub = datetime.fromisoformat(ep.pub_date)
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        fe.published(pub)

        audio_url = f"{BASE_URL}/audio/{ep.filename}"
        fe.enclosure(audio_url, str(ep.file_size_bytes), "audio/mpeg")
        fe.podcast.itunes_duration(_format_duration(ep.duration_secs))
        fe.podcast.itunes_summary(ep.description)

    return fg.rss_str(pretty=True)
