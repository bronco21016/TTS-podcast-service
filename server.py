import json
import multiprocessing
import os
from dataclasses import asdict
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import urlparse

from flask import Flask, Response, send_from_directory, abort, render_template, request, jsonify

from config import AUDIO_DIR, BASE_DIR, EPISODES_FILE, FLASK_PORT, PODCAST_TITLE
from podcast import Episode, generate_rss, load_episodes, make_episode_id, delete_episode

app = Flask(__name__)


# ---------- helpers ----------

def _ep_ctx(ep: Episode) -> dict:
    mins = int(ep.duration_secs // 60)
    secs = int(ep.duration_secs % 60)
    return {
        "id": ep.id,
        "title": ep.title,
        "description": ep.description or "",
        "filename": ep.filename,
        "pub_date": ep.pub_date[:10],
        "duration_label": f"{mins}m{secs:02d}s",
    }


def _episodes_ctx() -> list[dict]:
    return [_ep_ctx(ep) for ep in reversed(load_episodes())]


# ---------- existing routes ----------

@app.route("/feed.rss")
def rss_feed():
    rss = generate_rss()
    return Response(rss, mimetype="application/rss+xml")


@app.route("/audio/<path:filename>")
def serve_audio(filename: str):
    if not (AUDIO_DIR / filename).exists():
        abort(404)
    return send_from_directory(AUDIO_DIR, filename)


@app.route("/cover.jpg")
def serve_cover():
    cover = BASE_DIR / "cover.jpg"
    if not cover.exists():
        abort(404)
    return send_from_directory(BASE_DIR, "cover.jpg")


# ---------- web UI ----------

@app.route("/")
def index():
    from jobs import cleanup_old_jobs
    cleanup_old_jobs()
    return render_template("index.html",
                           episodes=_episodes_ctx(),
                           podcast_title=PODCAST_TITLE)


@app.route("/add", methods=["POST"])
def add_episode_web():
    url = request.form.get("url", "").strip()
    text = request.form.get("text", "").strip()
    title = request.form.get("title", "").strip()

    if not url and not text:
        return ('<article class="job-card job-error">'
                '<strong>Error:</strong> Provide a URL or paste some text.'
                '</article>'), 200

    if url:
        from podcast import find_duplicate_url
        dup = find_duplicate_url(url)
        if dup:
            return (f'<article class="job-card job-error">'
                    f'<strong>Already in feed:</strong> &ldquo;{dup.title}&rdquo;'
                    f'</article>'), 200

    ep_id = make_episode_id()

    if url:
        parsed = urlparse(url)
        placeholder_title = title or parsed.netloc.lstrip("www.")
    else:
        placeholder_title = title or (text[:60].replace("\n", " ").strip() + "…")

    ep_data = {
        "id": ep_id,
        "title": placeholder_title,
        "description": f"Converted from: {url or 'pasted text'}",
        "pub_date": datetime.now(timezone.utc).isoformat(),
        "source_url": url,
    }

    from jobs import write_job
    write_job(ep_id, title=placeholder_title, status="pending",
              chunk_current=0, chunk_total=0)

    from worker import run_pipeline
    proc = multiprocessing.Process(
        target=run_pipeline,
        args=(ep_id, ep_data),
        kwargs={"url": url or None, "raw_text": text or None},
        daemon=False,
    )
    proc.start()

    job = {"id": ep_id, "title": placeholder_title, "status": "pending",
           "chunk_current": 0, "chunk_total": 0}
    return render_template("_job_card.html", job=job, episodes=None)


@app.route("/job/<ep_id>")
def job_status(ep_id: str):
    from jobs import read_job
    job = read_job(ep_id)
    if not job:
        return "", 200

    episodes = _episodes_ctx() if job.get("status") == "done" else None
    return render_template("_job_card.html", job=job, episodes=episodes)


@app.route("/episode/<ep_id>")
def get_episode(ep_id: str):
    ep = next((e for e in load_episodes() if e.id == ep_id), None)
    if not ep:
        abort(404)
    return render_template("_episode_row.html", ep=_ep_ctx(ep))


@app.route("/episode/<ep_id>/edit")
def edit_episode_form(ep_id: str):
    ep = next((e for e in load_episodes() if e.id == ep_id), None)
    if not ep:
        abort(404)
    return render_template("_episode_edit.html", ep=_ep_ctx(ep))


@app.route("/episode/<ep_id>", methods=["PATCH"])
def patch_episode(ep_id: str):
    episodes = load_episodes()
    ep = next((e for e in episodes if e.id == ep_id), None)
    if not ep:
        abort(404)

    new_title = request.form.get("title", "").strip()
    if new_title:
        ep.title = new_title

    with open(EPISODES_FILE, "w") as f:
        json.dump([asdict(e) for e in episodes], f, indent=2)

    return render_template("_episode_row.html", ep=_ep_ctx(ep))


@app.route("/episode/<ep_id>", methods=["DELETE"])
def delete_episode_web(ep_id: str):
    ep = next((e for e in load_episodes() if e.id == ep_id), None)
    if ep:
        audio_file = AUDIO_DIR / ep.filename
        delete_episode(ep_id)
        if audio_file.exists():
            audio_file.unlink()
    return "", 200


# ---------- API ----------

def _require_api_key(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        api_key = os.environ.get("TTS_API_KEY", "")
        if not api_key:
            return jsonify({"error": "TTS_API_KEY not configured on server"}), 503
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != api_key:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper


@app.route("/api/episodes", methods=["POST"])
@_require_api_key
def api_add_episode():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    text = data.get("text", "").strip()
    title = data.get("title", "").strip()
    description = data.get("description", "").strip()

    if not text:
        return jsonify({"error": "'text' field is required"}), 400

    if not title:
        title = text[:60].replace("\n", " ").strip() + "…"

    ep_id = make_episode_id()
    ep_data = {
        "id": ep_id,
        "title": title,
        "description": description or "",
        "pub_date": datetime.now(timezone.utc).isoformat(),
        "source_url": "",
    }

    from jobs import write_job
    write_job(ep_id, title=title, status="pending", chunk_current=0, chunk_total=0)

    from worker import run_pipeline
    proc = multiprocessing.Process(
        target=run_pipeline,
        args=(ep_id, ep_data),
        kwargs={"raw_text": text},
        daemon=False,
    )
    proc.start()

    return jsonify({
        "job_id": ep_id,
        "title": title,
        "status_url": f"/job/{ep_id}",
    }), 202


if __name__ == "__main__":
    print(f"RSS feed: http://0.0.0.0:{FLASK_PORT}/feed.rss")
    app.run(host="0.0.0.0", port=FLASK_PORT)
