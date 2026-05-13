import sys
from pathlib import Path
import anthropic
from config import ANTHROPIC_API_KEY, BASE_DIR

TRANSCRIPTS_DIR = BASE_DIR / "transcripts"
TRANSCRIPTS_DIR.mkdir(exist_ok=True)

_SYSTEM_PROMPT = """\
You are a transcript editor preparing written content for text-to-speech conversion.

Transform the provided article into a clean, natural-sounding spoken transcript. Follow these rules:

1. PRESERVE the full content faithfully — do not summarize, skip sections, or editorialize.
2. CODE BLOCKS: Replace with a brief spoken description. Example: "The following Python function takes a list of numbers and returns their sum." Then continue with the surrounding explanation.
3. URLS: Remove all raw URLs. If a URL is cited as a source, say "linked in the original article" or similar.
4. MARKDOWN: Convert to natural prose. Headings become spoken transitions ("In the next section..."). Bold/italic emphasis is dropped. Lists become flowing sentences or short spoken lists ("first... second... and third...").
5. ACRONYMS: Spell out on first use, e.g. "CPU, or Central Processing Unit".
6. SPECIAL CHARACTERS: Convert symbols to words where they'd be read aloud oddly. "100%" → "one hundred percent". "C++" → "C plus plus". "&" → "and".
7. NUMBERS: Write out numbers that would sound odd if read as digits. Keep technical figures as-is when precision matters.
8. NATURAL FLOW: The output should sound like a professional narrator reading aloud. Add brief transitions between abrupt section jumps if needed.
9. DO NOT add commentary, introductions, or sign-offs that weren't in the original.
10. OUTPUT only the transcript text — no headings, no metadata, no explanations.
"""


def clean_for_tts(title: str, raw_text: str, episode_id: str = "") -> str:
    if not ANTHROPIC_API_KEY:
        print("Error: ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    user_message = f"Article title: {title}\n\n---\n\n{raw_text}"

    transcript = ""
    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        for text in stream.text_stream:
            transcript += text

    transcript = transcript.strip()

    # Save transcript to archive
    slug = episode_id or title[:40].replace(" ", "_").replace("/", "-")
    archive_path = TRANSCRIPTS_DIR / f"{slug}.txt"
    archive_path.write_text(f"{title}\n{'='*len(title)}\n\n{transcript}\n", encoding="utf-8")

    return transcript
