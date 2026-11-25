"""Create a project-local environment and start Stemroom."""
import hashlib
import os
import shutil
import subprocess
import sys
import venv
import webbrowser
from pathlib import Path
from threading import Timer
from time import sleep
from urllib.request import urlopen

base = Path(__file__).resolve().parent
os.chdir(base)
if not (3, 10) <= sys.version_info[:2] <= (3, 12):
    raise SystemExit("Use Python 3.10, 3.11 or 3.12 to run start.py.")
if not all(shutil.which(binary) for binary in ("ffmpeg", "ffprobe")):
    raise SystemExit("Install FFmpeg (including ffprobe), reopen your terminal, then run start.py again.")
env = base / ".venv"
python = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
if not python.exists():
    venv.create(env, with_pip=True)
stamp = env / "stemroom-version"
version = hashlib.sha256((base / "requirements.txt").read_bytes()).hexdigest()
if not stamp.exists() or stamp.read_text() != version:
    pip = [str(python), "-m", "pip", "install"]
    if sys.platform != "darwin":
        subprocess.run(pip + ["--index-url", "https://download.pytorch.org/whl/cpu", "torch==2.5.1", "torchaudio==2.5.1"], check=True)
    subprocess.run(pip + ["-r", "requirements.txt"], check=True)
    stamp.write_text(version)


def open_studio():
    for _ in range(30):
        try:
            with urlopen("http://127.0.0.1:8765", timeout=1) as page:
                if b"studio-token" in page.read():
                    webbrowser.open(page.url)
                    return
        except OSError:
            sleep(.25)


timer = Timer(.5, open_studio)
timer.daemon = True
timer.start()
try:
    subprocess.run([str(python), "app.py"], check=True)
except KeyboardInterrupt:
    pass
