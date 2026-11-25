"""Local music stem studio. Run with python app.py."""
import io
import json
import math
import re
import secrets
import subprocess
import sys
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from flask import Flask, abort, jsonify, render_template_string, request, send_file

app = Flask(__name__)
app.config.update(MAX_CONTENT_LENGTH=256 * 1024**2, TRUSTED_HOSTS=["127.0.0.1", "localhost"])
session_dir = tempfile.TemporaryDirectory(prefix="stemroom-")
root = Path(session_dir.name)
token = secrets.token_urlsafe(32)
queue = ThreadPoolExecutor(max_workers=1)
jobs = {}
models = {"hdemucs", "htdemucs_6s"}


def run(args):
    result = subprocess.run(args, capture_output=True, text=True, errors="replace")
    if result.returncode:
        raise ValueError(result.stderr.strip()[-900:] or "Media processing failed.")
    return result.stdout


def youtube_url(value):
    url = urlsplit(value.strip())
    host = (url.hostname or "").lower()
    if host == "youtu.be":
        video = url.path.strip("/")
    elif host in {"www.youtube.com", "youtube.com", "music.youtube.com", "m.youtube.com"}:
        video = parse_qs(url.query).get("v", [""])[0] if url.path == "/watch" else url.path.split("/")[-1] if url.path.startswith(("/shorts/", "/live/", "/embed/")) else ""
    else:
        video = ""
    if url.scheme not in {"http", "https"} or not re.fullmatch(r"[\w-]{11}", video, re.ASCII):
        raise ValueError("Enter a YouTube video link.")
    return "https://www.youtube.com/watch?v=" + video


def ytdlp(*args):
    return run([sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-playlist", "--no-warnings", *args])


@app.before_request
def guard():
    if request.method == "POST" and request.headers.get("X-Studio") != token:
        abort(403)


@app.get("/")
def index():
    return render_template_string((Path(app.root_path) / "studio.html").read_text(encoding="utf8"), token=token)


@app.post("/source")
def source():
    directory = root / uuid4().hex
    directory.mkdir()
    try:
        if "file" in request.files:
            upload = request.files["file"]
            upload.save(directory / "input")
            metadata = json.loads(run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index:format=duration", "-of", "json", directory / "input"]))
            if not metadata["streams"]:
                raise ValueError("Choose a file containing audio.")
            duration = float(metadata["format"]["duration"])
            title = Path(upload.filename or "Track").stem
            url = None
        else:
            url = youtube_url(request.form.get("url", ""))
            info = json.loads(ytdlp("--dump-single-json", url))
            title, duration = info["title"], info.get("duration")
        if not duration or not 0 < duration <= 900:
            raise ValueError("Choose a recording up to 15 minutes long.")
        data = dict(title=title, duration=duration, url=url)
        (directory / "source.json").write_text(json.dumps(data))
        return jsonify(id=directory.name, title=title, duration=duration)
    except (ValueError, KeyError, OSError) as exc:
        import shutil
        shutil.rmtree(directory)
        return jsonify(error=str(exc)), 400


def separate(job, directory, data, model):
    try:
        source_path = directory / "input"
        if data["url"] and not source_path.exists():
            job["status"] = "Downloading audio"
            ytdlp("-f", "bestaudio/best", "-o", str(directory / "download.%(ext)s"), data["url"])
            downloaded = next(directory.glob("download.*"))
            downloaded.replace(source_path)
        job["status"] = "Preparing stereo audio"
        wav = directory / "audio.wav"
        run(["ffmpeg", "-v", "error", "-y", "-i", source_path, "-map", "0:a:0", "-ar", "44100", "-ac", "2", "-c:a", "pcm_f32le", wav])
        job["status"] = "Separating instruments · first use downloads the model"
        folder = directory / "stems" / model / "audio"
        if model == "hdemucs":
            run([sys.executable, Path(app.root_path) / "four_stems.py", wav, folder])
        else:
            run([sys.executable, "-m", "demucs", "-n", model, "--float32", "-o", directory / "stems", wav])
        stems = sorted(f.stem for f in folder.glob("*.wav"))
        if len(stems) != (6 if model == "htdemucs_6s" else 4):
            raise ValueError("The model produced an incomplete set of tracks.")
        job.update(folder=folder, stems=stems, status="Ready")
    except Exception as exc:
        job.update(error=str(exc), status="Failed")


@app.post("/split/<sid>")
def split(sid):
    meta = root / sid / "source.json"
    model = request.form.get("model")
    if not re.fullmatch("[a-f0-9]{32}", sid) or not meta.is_file() or model not in models:
        abort(400)
    key = sid + "-" + model
    if key not in jobs or jobs[key]["status"] == "Failed":
        jobs[key] = {"status": "Queued"}
        queue.submit(separate, jobs[key], meta.parent, json.loads(meta.read_text()), model)
    return jsonify(id=key)


@app.get("/job/<key>")
def status(key):
    job = jobs.get(key) or abort(404)
    return jsonify({k: v for k, v in job.items() if k != "folder"})


def completed(key):
    job = jobs.get(key) or abort(404)
    if job["status"] != "Ready":
        abort(409)
    return job


@app.get("/audio/<key>/<stem>")
def audio(key, stem):
    job = completed(key)
    if stem not in job["stems"]:
        abort(404)
    return send_file(job["folder"] / (stem + ".wav"))


@app.get("/archive/<key>")
def archive(key):
    job = completed(key)
    output = tempfile.TemporaryFile()
    with zipfile.ZipFile(output, "w") as bundle:
        for stem in job["stems"]:
            bundle.write(job["folder"] / (stem + ".wav"), stem + ".wav")
    output.seek(0)
    return send_file(output, mimetype="application/zip", as_attachment=True, download_name="stems.zip")


@app.post("/mix/<key>")
def mix(key):
    job = completed(key)
    levels = request.get_json()
    if not isinstance(levels, dict) or set(levels) != set(job["stems"]):
        abort(400)
    args = ["ffmpeg", "-v", "error"]
    filters, streams = [], []
    for i, stem in enumerate(job["stems"]):
        level = levels[stem]
        if type(level) not in (int, float) or not math.isfinite(level) or not 0 <= level <= 1:
            abort(400)
        args.extend(["-i", str(job["folder"] / (stem + ".wav"))])
        filters.append(f"[{i}:a]volume={level}[s{i}]")
        streams.append(f"[s{i}]")
    filters.append("".join(streams) + f"amix=inputs={len(streams)}:normalize=0,alimiter=limit=0.98:level=0:latency=1")
    result = subprocess.run(args + ["-filter_complex", ";".join(filters), "-f", "mp3", "-b:a", "320k", "pipe:1"], capture_output=True, check=True)
    return send_file(io.BytesIO(result.stdout), mimetype="audio/mpeg", download_name="mix.mp3", as_attachment=True)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8765, threaded=True)
