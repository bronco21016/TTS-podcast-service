# Web UI Plan

## Goal
A simple browser-based interface for submitting articles and managing episodes — accessible
from any device on the LAN (iPhone, laptop, etc.) without SSH.

---

## Stack

| Layer | Choice | Why |
|---|---|---|
| Server | Flask (already installed) | Already running, no new deps |
| Templates | Jinja2 (built into Flask) | No build step |
| Interactivity | HTMX (CDN) | Dynamic updates without writing JS |
| Styling | Pico CSS (CDN) | Clean dark theme, zero config, mobile-friendly |
| Job tracking | JSON files in `jobs/` | Simple, no Redis/Celery needed |

No JavaScript framework. No build pipeline. Everything served by the existing Flask process.

---

## New File Structure

```
TTS_service/
├── templates/
│   ├── index.html          # full page shell
│   ├── _episodes.html      # episode list partial (HTMX target)
│   ├── _episode_row.html   # single episode row partial
│   └── _job_status.html    # synthesis progress card partial
├── static/
│   └── style.css           # minimal overrides on top of Pico
└── jobs/                   # job status JSON files (gitignored)
```

---

## Routes (add to server.py)

| Method | Path | Does |
|---|---|---|
| GET | `/` | Renders full page with submit form + episode list |
| POST | `/add` | Validates input, starts background synthesis, returns `_job_status.html` partial |
| GET | `/job/<id>` | Returns `_job_status.html` partial (HTMX polls this every 3s) |
| DELETE | `/episode/<id>` | Deletes episode + audio, returns updated `_episodes.html` |
| PATCH | `/episode/<id>` | Updates title/description, returns updated `_episode_row.html` |
| GET | `/audio/<filename>` | Already exists — unchanged |
| GET | `/feed.rss` | Already exists — unchanged |

---

## Job Tracking

Synthesis progress needs to be visible in the browser. Add a `jobs/` directory with
one JSON file per active/recent job:

```json
{
  "id": "uuid",
  "title": "Article Title",
  "status": "processing",   // pending | processing | done | error
  "chunk_current": 3,
  "chunk_total": 7,
  "error": null
}
```

Changes needed:
- `synthesize.py`: write/update `jobs/<id>.json` at each chunk
- Background worker: set status to `done` or `error` when finished
- Job files can be cleaned up after 24h or on page load

---

## UI Layout

```
┌─────────────────────────────────────────────┐
│  🎙 The Briefing                  [feed.rss] │
├─────────────────────────────────────────────┤
│                                             │
│  [ URL input field              ] [Add →]   │
│  ── or ──                                   │
│  [ Text area for paste/file     ]           │
│  [ Title (optional)             ] [Add →]   │
│                                             │
├─────────────────────────────────────────────┤
│  ⟳ Processing: "Article Title"  ████░░ 4/7  │  ← job status card (HTMX poll)
├─────────────────────────────────────────────┤
│  Episodes                                   │
│  ────────────────────────────────────────   │
│  ▶  How to Work with AI         15m  [✎][✕] │
│  ▶  Resolvers: Routing Table    18m  [✎][✕] │
│  ▶  Thin Harness Fat Skills     13m  [✎][✕] │
└─────────────────────────────────────────────┘
```

- Clicking ▶ opens the MP3 in the browser's native audio player
- Clicking ✎ turns the title into an inline editable field; saves on blur via PATCH
- Clicking ✕ shows a confirm dialog then DELETEs via HTMX
- Progress bar updates every 3 seconds via HTMX polling until status = done
- When done, status card swaps out for the new episode row at top of list
- Single-column layout works on iPhone Safari over WireGuard

---

## HTMX Patterns

**Submit form → show progress card:**
```html
<form hx-post="/add" hx-target="#job-slot" hx-swap="innerHTML">
```

**Progress card polling:**
```html
<div hx-get="/job/{{ id }}" hx-trigger="every 3s" hx-swap="outerHTML">
```
When status == done, the server returns the episode row instead — polling stops naturally
because the new element has no `hx-trigger`.

**Inline episode title edit:**
```html
<span hx-get="/episode/{{ id }}/edit-form" hx-trigger="click" hx-swap="outerHTML">
```

**Delete with confirmation:**
```html
<button hx-delete="/episode/{{ id }}" hx-confirm="Remove this episode?"
        hx-target="#episode-{{ id }}" hx-swap="outerHTML swap:1s">
```

---

## Implementation Order

1. `jobs/` directory + job file writer in `synthesize.py`
2. Background worker updated to write final status
3. New Flask routes (GET `/`, POST `/add`, GET `/job/<id>`, DELETE, PATCH)
4. Templates: `index.html` shell → `_episodes.html` → `_job_status.html` → `_episode_row.html`
5. `static/style.css` minimal overrides
6. Update `tts-server.service` if gunicorn workers need adjustment (HTMX polling
   requires the job files be readable by all workers — file-based state handles this fine)
7. Test on iPhone Safari over WireGuard

---

## What Doesn't Change

- `cli.py` / `narrate` command — still fully functional
- RSS feed — unchanged
- `episodes.json` — still the source of truth for the feed
- Synthesis pipeline — only change is writing progress to `jobs/<id>.json`
