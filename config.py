import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# --- User-editable settings ---
PODCAST_TITLE = "The Briefing"
PODCAST_AUTHOR = "Justin"
PODCAST_EMAIL = "justin.vandemark@gmail.com"
PODCAST_DESCRIPTION = "Articles and long-form reading, synthesized and narrated by AI."
PODCAST_LANGUAGE = "en-us"

# LAN IP or hostname of this machine, no trailing slash
# Run `ip addr show` to find your LAN IP, e.g. http://192.168.1.x:5050
BASE_URL = os.environ.get("TTS_BASE_URL", "http://localhost:5050")

FLASK_PORT = 5050

KOKORO_VOICE = "af_heart"
KOKORO_SPEED = 0.92
KOKORO_SAMPLE_RATE = 24000
MP3_BITRATE = "128k"

# Max words per Kokoro chunk to avoid context overflow
KOKORO_CHUNK_WORDS = 450

# --- Paths ---
BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "audio"
EPISODES_FILE = BASE_DIR / "episodes.json"

AUDIO_DIR.mkdir(exist_ok=True)

# --- API key (validated at use time in transcript.py) ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
