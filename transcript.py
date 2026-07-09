import sys
import time
import threading
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
9. PRONUNCIATION: This transcript is synthesized by Kokoro TTS. Kokoro supports an inline phonetic override: `[word](/phonemes/)` — the phonemes between the slashes are inserted directly, bypassing Kokoro's own (unreliable) guess for that word. Use this for any word Kokoro is likely to mispronounce or fail on entirely — most importantly, uncommon proper nouns, product/technical names, and acronyms not in a standard dictionary (e.g. "Kubernetes", "nginx", "kubectl" — these come out as a silent error token if left unannotated). Do NOT use spelled-out hints in parentheses like "(koo-ber-NET-eez)" — that text gets read aloud literally as extra garbled words, it is not interpreted as pronunciation guidance.
   - Valid phoneme symbols (American English only — using any other character will break the override):
     - Stress marks: ˈ primary, ˌ secondary — placed immediately before the stressed syllable's vowel.
     - Vowels: ə i u ɑ ɔ ɛ ɜ ɪ ʊ ʌ æ
     - Diphthongs: A ("day"), I ("high"), W ("how"), O ("go"), Y ("boy")
     - Consonants: b d f h j k l m n p s t v w z ɡ (hard "g") ŋ ("sing") ɹ ("r") ʃ ("sh") ʒ ("zh") ð ("this") θ ("thin") ʤ ("jump") ʧ ("chip") ɾ (American flap t/d, as in "butter")
   - Example, verified against Kokoro's phonemizer: `[Kubernetes](/ˌkubəɹnˈɛtiz/) is a container orchestration system.`
   - Annotate the word every time it appears, not just on first use — Kokoro's phonemizer has no memory across the transcript, so an unannotated repeat will mispronounce again.
   - Wrap only one word per bracket. For a multi-word name, put the phonemes for the whole phrase in one bracket around the whole phrase, e.g. `[San Jose](/ˌsænhozˈeɪ/)`.
   - Don't override words Kokoro already says correctly — only annotate genuine trouble spots, and only if you're confident in the phoneme string; an incorrect override is worse than leaving the word alone.
   - Abbreviations that could be read as words: "SQL" → "S-Q-L", "APIs" → "A-P-I-s", unless they are universally spoken as words (e.g. "NASA" stays as-is).
10. DO NOT add commentary, introductions, or sign-offs that weren't in the original.
11. OUTPUT only the transcript text — no headings, no metadata, no explanations.
"""


def _spinner(stop_event: threading.Event):
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    start = time.time()
    i = 0
    while not stop_event.is_set():
        elapsed = time.time() - start
        print(f"\r  {frames[i % len(frames)]} Cleaning transcript... {elapsed:.0f}s", end="", flush=True)
        i += 1
        time.sleep(0.1)
    print("\r", end="", flush=True)


def clean_for_tts(title: str, raw_text: str, episode_id: str = "") -> str:
    if not ANTHROPIC_API_KEY:
        print("Error: ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    user_message = f"Article title: {title}\n\n---\n\n{raw_text}"

    stop = threading.Event()
    spinner = threading.Thread(target=_spinner, args=(stop,), daemon=True)
    spinner.start()
    t_start = time.time()

    transcript = ""
    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        for text in stream.text_stream:
            transcript += text

    stop.set()
    spinner.join()
    elapsed = time.time() - t_start

    transcript = transcript.strip()

    slug = episode_id or title[:40].replace(" ", "_").replace("/", "-")
    archive_path = TRANSCRIPTS_DIR / f"{slug}.txt"
    archive_path.write_text(f"{title}\n{'='*len(title)}\n\n{transcript}\n", encoding="utf-8")

    print(f"  Done — {len(transcript):,} chars in {elapsed:.0f}s → transcripts/{archive_path.name}")
    return transcript
