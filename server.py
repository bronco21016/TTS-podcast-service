from flask import Flask, Response, send_from_directory, abort
from config import AUDIO_DIR, BASE_DIR, FLASK_PORT
from podcast import generate_rss

app = Flask(__name__)


@app.route("/feed.rss")
def rss_feed():
    rss = generate_rss()
    return Response(rss, mimetype="application/rss+xml")


@app.route("/audio/<path:filename>")
def serve_audio(filename: str):
    if not (AUDIO_DIR / filename).exists():
        abort(404)
    return send_from_directory(AUDIO_DIR, filename)


@app.route("/cover.png")
def serve_cover():
    cover = BASE_DIR / "cover.png"
    if not cover.exists():
        abort(404)
    return send_from_directory(BASE_DIR, "cover.png")


if __name__ == "__main__":
    print(f"RSS feed: http://0.0.0.0:{FLASK_PORT}/feed.rss")
    app.run(host="0.0.0.0", port=FLASK_PORT)
