# CyberRadio-Gen 📻⚡

> *"MADE WITH AI USING AI — just like Cyberpunk. We don't need humans here."*
>
> — the repository

**CyberRadio-Gen** is an AI-powered desktop app that generates custom radio stations for **Cyberpunk 2077**. It writes the anchorman script via a local LLM (LM Studio / Ollama), voices it with ElevenLabs, generates original music through Suno AI, applies gritty FM radio effects, and packages everything as a drop-in RadioExt mod. No recording studio. No voice actors. No musicians. Just you, your GPU, and a few API keys.

---

## How it works

```
Local LLM ──→ writes anchorman script (intro + interludes)
     ↓
ElevenLabs ──→ synthesizes the host voice (free tier: premade voices)
     ↓
Suno AI ────→ generates original cyberpunk tracks (lyrics + music)
     ↓
FFmpeg ─────→ applies FM bandpass + compression (cheap car speaker feel)
     ↓
RadioExt ───→ metadata.json + numbered MP3s → drop into Cyberpunk 2077
```

---

## Prerequisites

### Required mods (install these first)
| Mod | Why |
|---|---|
| [Cyber Engine Tweaks](https://github.com/maximegmd/CyberEngineTweaks) | CET mod loader — required by RadioExt |
| [Red4Ext](https://github.com/WopsS/RED4ext) | Native plugin loader — required by RadioExt |
| [RadioExt](https://github.com/justarandomgabe/CP77_radioExt) | The radio mod itself — reads our `metadata.json` and plays the tracks |

### Required software
- **Python 3.10+** (tested on 3.14)
- **FFmpeg** on your system PATH (for radio FX; gracefully skipped if missing)
- **LM Studio** or **Ollama** running locally (for the anchorman script)

### API keys
- **ElevenLabs** — free tier works (premade voices only). Get one at https://elevenlabs.io
- **Suno API** — via `sunoapi.org` or your gateway of choice

---

## Installation

### Option A: One-click setup (Windows)

```powershell
.\setup.ps1
```

This creates a virtual environment, installs everything, checks for FFmpeg, and creates `run.bat` for double-click launching.

### Option B: Manual

```bash
git clone https://github.com/yourusername/CyberRadio-Gen.git
cd CyberRadio-Gen
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

The dependencies are minimal — just `customtkinter` and `requests`.

Then start your LLM server (LM Studio → Start Server, default `http://localhost:1234/v1`).

---

## Usage

```bash
.\venv\Scripts\activate
python main.py
```

Or just double-click `run.bat` after running the setup script.

1. **Configure** — paste your ElevenLabs / Suno keys in the left panel, pick a voice, set your station name and frequency
2. **Generate** — click **GENERATE RADIO STATION** and watch the log console build your station live
3. **Copy to Cyberpunk 2077** — the output lands in `output/{StationName}/`. Copy that folder to:

```
Cyberpunk 2077\bin\x64\plugins\cyber_engine_tweaks\mods\radioExt\radios\
```

4. **Tune in** — launch the game, get in any vehicle, and scroll through the radio stations. Yours will be there.

### Continue mode (build over time)

RadioExt shows all tracks in the station folder. Run the app again with the same station name and click **Add to Station** to append more interludes and songs. Credits reset naturally — build your station across multiple sessions.

### Manual music mode (no Suno credits)

Drop `.mp3` files in `input_music/`, leave the Suno key blank, and generate. The app will sequence them alongside the AI host.

---

## Output format

Each station generates a folder with:
- `001_Anchorman_Intro.mp3` — AI radio host intro
- `002_Suno_Song_1.mp3` — AI-generated track
- `003_Anchorman_Interlude_1.mp3` — AI radio host interlude (continue mode)
- `metadata.json` — RadioExt format with `order`, `streamInfo`, `icon`, etc.
- `cover.jpg` — optional album art from Suno

The `metadata.json` follows the actual RadioExt schema:
```json
{
  "displayName": "87.5 My Station",
  "fm": 87.5,
  "volume": 0.5,
  "icon": "UIIcon.RadioHipHop",
  "order": ["001_Anchorman_Intro.mp3", "002_Suno_Song_1.mp3"]
}
```

---

## Project structure

```
CyberRadio-Gen/
├── main.py              # Entry point — launches the GUI
├── app_gui.py           # CustomTkinter window (settings, log, generate button)
├── pipeline.py          # Orchestrator — LLM → TTS → Suno → RadioExt
├── llm_client.py        # LM Studio / Ollama chat completion
├── tts_client.py        # ElevenLabs TTS with model fallback
├── suno_client.py       # Suno API song generation + polling
├── audio_processor.py   # FFmpeg FM filter + RadioExt metadata
├── config_manager.py    # JSON config load/save
├── config.json          # Persistent settings
├── input_music/         # Drop manual MP3s here
├── output/              # Generated stations land here
├── tests/               # 249 unit tests (all passing)
│   ├── test_all.py
│   ├── test_clients.py
│   ├── test_edge_cases.py
│   └── test_app_gui.py
└── README.md            # You are here
```

---

## 249 tests — because chrome can fail

```bash
python -m unittest discover tests -v
```
Run these after any change. The test suite covers pipeline modes (fresh/continue/repair), all API error paths (ElevenLabs 402, Suno polling timeouts, LLM connection refused), GUI logic (button states, sanity check, credit display), filesystem edge cases (unicode names, read-only dirs, 150-track playlists), and resource cleanup (no temp file leaks, KeyboardInterrupt safety).

---

## License

MIT — go chrome some radios.

---

*Built with AI, for a city that runs on AI. Night City never sleeps, and neither should your radio.*
