# Stemroom

A local browser studio for separating songs, listening to individual instruments, and exporting backing tracks.

## Start the app

Install 64-bit Python 3.10–3.12 and FFmpeg with ffprobe available on your PATH. On Windows, macOS and Linux, extract the archive and open a terminal inside the Stemroom folder. Run the command for your system.

- Windows with Python 3.12 installed — `py -3.12 start.py`
- macOS or Linux with Python 3.12 installed — `python3.12 start.py`

The launcher creates a virtual environment, installs the dependencies, and opens http://127.0.0.1:8765. The first launch needs internet access and several gigabytes of free space. Keep the terminal open while using the app. Ctrl+C stops the server. Export anything you want to keep before stopping it.

## Separate a song

1. Choose a local audio file or paste a YouTube video link. Click **Load song** and check the title and duration. The input limit is 15 minutes and uploads must fit within 256 MB.
2. Select **4 stems** for vocals, drums, bass, and other instruments. Select **6 stems** for separate guitar and piano estimates as well. Click **Separate tracks**. The first use of each model downloads its weights. Later local-file runs can use cached weights offline.
3. Click **Play**. Use **Solo** to isolate tracks, **Mute** to remove an instrument for practice, and the sliders to balance the mix. **Export mix as MP3** uses those settings. **Download all WAVs** saves the full-length individual stems together in a ZIP.
4. To compare models, choose the other model for the same loaded song and separate it again. Compare the same passage with your instrument soloed and muted. Completed model runs are reused for the loaded song.

The four-stem engine uses TorchAudio's Hybrid Demucs model trained on MUSDB plus additional songs. The six-stem engine uses Demucs htdemucs_6s. Closely overlapping instruments can bleed into one another. Browser playback holds decoded tracks in memory. Try a shorter excerpt on machines with limited RAM.

YouTube import uses yt-dlp and requires network access. Availability depends on the video and YouTube's access rules. For broader YouTube support install Deno 2.3 or newer on PATH, then restart the app. If an import fails, choose Audio file and load a local copy.
