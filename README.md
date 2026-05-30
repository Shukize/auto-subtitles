# Subtitle Studio

Drag-and-drop desktop app that generates **highly accurate AI subtitles** for any
video or audio file, optionally **translates** them into any language, lets you
**edit** every line, and can **burn** styled subtitles directly into the video.

Runs locally. Uses your **NVIDIA GPU** automatically when available (with an
automatic CPU fallback), so transcription is fast and private.

![overview](docs/overview.png)

## Features

- **Drag & drop** a file, click to open a file, or **Open Folder** for batch jobs.
- **Accurate transcription** via OpenAI Whisper (`faster-whisper`), defaulting to
  the `large-v3` model with word-level timestamps and natural line segmentation.
- **GPU acceleration** (CUDA) with automatic fallback to CPU.
- **Translate** subtitles into 50+ languages.
- **Full editor**: adjust timings, edit text, add / delete / merge / split cues.
- **Styling**: font, size, colour, outline, bold/italic, position and margins.
- **Export**: `.srt`, `.vtt`, styled `.ass`, or **burn** the subtitles into a new MP4.
- **Batch mode**: transcribe a whole folder and write a `.srt` next to each file.
- Self-contained — **ffmpeg is bundled**, nothing else to install.

## Quick start (from source)

```powershell
# 1. Create the environment and install dependencies
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. Run
.\run_dev.ps1            #  or:  .\.venv\Scripts\python.exe run_app.py
```

The first transcription downloads the chosen Whisper model (the default
`large-v3` is ~3 GB) into `%APPDATA%\SubtitleStudio\models`. Smaller/faster models
(`tiny` … `medium`) are selectable in the UI.

## Building the standalone .exe

```powershell
.\build.ps1
```

This produces `dist\SubtitleStudio\SubtitleStudio.exe` (a self-contained folder you
can zip and share). `onedir` mode is used so the bundled CUDA DLLs don't have to be
unpacked on every launch. ffmpeg is included; the GPU runtime libraries are bundled
and registered automatically at startup.

## How to use

1. **Add media** – drop a file onto the window, or use *Open File* / *Open Folder*.
2. Pick the **model** (accuracy), the **spoken language** (or auto-detect), and an
   optional **translate-to** language.
3. Click **⚡ Generate Subtitles**. Progress shows extraction → transcription →
   translation.
4. **Edit** the result in the table — timings are `HH:MM:SS.mmm`.
5. **Style** the subtitles, then **Save** (`.srt`/`.vtt`/`.ass`) or
   **🔥 Burn into video** to produce a new MP4 with hard-coded subtitles.

## Architecture

```
subtitle_studio/
  app.py                 # QApplication bootstrap
  config.py              # settings + persistence (%APPDATA%\SubtitleStudio)
  core/
    cuda_setup.py        # registers bundled NVIDIA DLLs at runtime
    media.py             # ffmpeg: probe / extract audio / burn-in
    transcribe.py        # faster-whisper, GPU→CPU fallback, re-segmentation
    translate.py         # any-language translation (pluggable backend)
    subtitles.py         # subtitle document model + ASS styling (pysubs2)
  ui/
    main_window.py       # drag-drop, editable table, styling, export
    workers.py           # background QThread so the UI stays responsive
    util.py              # timestamp formatting/parsing
```

## Notes

- Translation uses an online service (Google via `deep-translator`); transcription
  is fully local.
- The bundled ffmpeg supports the common video/audio containers; output burn-in is
  H.264 (`libx264`, CRF 18) with the original audio copied through.

## License

For your own use. Review the licenses of the bundled components (Whisper models,
ffmpeg, PySide6/Qt) before redistributing.
