# CyberRadio-Gen — Project Context

## Goal
Build a desktop Python app that generates a custom **Cyberpunk 2077** radio station with AI anchor voice (ElevenLabs TTS) + music (Suno API or manual MP3s) and outputs it in **RadioExt** mod format.

---

## Architecture & Files

### Entry Point
- `main.py` — Starts the GUI (`app_gui.py`), no CLI args needed.

### Files

| File | Responsibility |
|---|---|
| `app_gui.py` | CustomTkinter window — settings fields, credit display, log area, GENERATE button. Calls pipeline in a daemon thread. |
| `pipeline.py` | Orchestrator: LLM script (anchorman only) → TTS voice → music (Suno handles lyrics + style) → RadioExt metadata. Paid APIs degrade gracefully (partial station). |
| `llm_client.py` | Sends prompt to LM Studio (`http://localhost:1234/v1`) or Ollama, returns generated text. |
| `tts_client.py` | ElevenLabs: credits (`GET /v1/user`), voice list (`GET /v1/voices`), model list (`GET /v1/models`), TTS generation (`POST /v1/text-to-speech/{voice_id}`) with model fallback loop. |
| `suno_client.py` | Suno API: credits (`GET /v1/generate/credit`), song generation (`POST /v1/generate`), polling (`GET /v1/generate/record`). |
| `audio_processor.py` | FFmpeg radio FM filter + RadioExt `metadata.json` writer. |
| `config_manager.py` | JSON config load/save with defaults. |
| `config.json` | Persistent settings (API keys, voice ID, station name/frequency/volume). |

### Output Directory Structure

```
output/
  {StationName}/
    001_Anchorman_Intro.mp3
    002_Suno_Song_1.mp3
    003_Suno_Song_2.mp3
    004_Suno_Song_3.mp3
    cover.jpg             (optional, from Suno)
    metadata.json         (RadioExt format)
```

---

## API Keys & Credentials (ACTIVE)

### ElevenLabs
- **API Key**: `sk_7a634ce428cd2cfa52dbb9c66e2f1b06f8fa8b0ee1d33f09`
- **Plan**: Free tier (10k chars/month)
- **Credits used**: 360 / 10,000
- **Current voice**: Charlie (`IKne3meq5aSn9XLyUdCD`) — premade, works on free API
- **Free tier limitation**: Only **premade** voices work. Library/generated/professional voices return 402 `paid_plan_required`.
- **Default model**: `eleven_v3` (queried dynamically from `GET /v1/models`)
- **Fallback models** (if API query fails): `eleven_flash_v2_5`, `eleven_flash_v2`, `eleven_multilingual_v2`, `eleven_turbo_v2_5`

### Suno
- **API Key**: stored in `config.json`
- **Credits**: ~2 remaining

### LLM
- **Provider**: LM Studio (local)
- **URL**: `http://localhost:1234/v1`

---

## Key Design Decisions

### LM Studio Scope
- **Anchorman script only** — writes punchy, theatrical radio host lines. That's it.
- **Not used for music** — Suno handles all song content (lyrics + style) on its own.

### Multi-Song Generation (new)
- `song_count` config field (default 3) controls how many songs per station.
- `song_styles` is a list of style prompts (editable in GUI as one-per-line).
- Each song picks a **random style** from the list, so every generation is different.
- A fixed lyrical theme ("Night City lifestyle — neon streets, corpo wars, netrunners, survival") is passed as the Suno prompt.
- Suno generates its own lyrics from that theme (`customMode: False`).
- Tracks are numbered sequentially: `002_Suno_Song_1.mp3`, `003_Suno_Song_2.mp3`, etc.

### Pipeline Resilience (most recent change)
- **LLM script**: hard gate — free, local, no credits spent. If it fails, pipeline aborts.
- **ElevenLabs TTS**: graceful degradation — if it fails, the station is still created with music only.
- **Suno music**: graceful degradation — if it fails, the station is still created with anchor only.
- **No tracks at all** → `"failed"` result.
- Return values: `"complete"` (all steps OK), `"partial"` (some steps failed but tracks exist), `"failed"` (nothing produced).

### Credit Pre-Check (before generation starts)
1. Queries ElevenLabs `GET /v1/user` for remaining characters.
2. Queries Suno `GET /v1/generate/credit` for remaining credits.
3. Shows `tkinter.messagebox.askyesno` with warnings if either is low/missing.
4. User can click "Yes" to proceed anyway or "No" to cancel.

### Voice Dropdown
- Populated from `GET /v1/voices` on startup.
- Sorted: premade (✅), generated (⚠️), professional (❌ — paid plan).
- Updated 500ms after app starts in a background thread.

### TTS Model Fallback
- Queries `GET /v1/models` dynamically to find which models the account supports.
- Tries each model in order until one succeeds.
- If the API query fails, uses hardcoded fallback list.

### RadioExt Metadata Format
```json
{
  "displayName": "Station Name",
  "fm": 99.7,
  "volume": 0.5,
  "isStream": false,
  "tracks": [
    "001_Anchorman_Intro.mp3",
    "002_Suno_Song_1.mp3"
  ]
}
```

### Audio Processing
- FFmpeg-based bandpass filter (300Hz–5kHz) to simulate small FM speaker.
- Dynamic range compression for punchy radio feel.
- Mild saturation for analog grit.

---

## How to Run

1. Start LM Studio (or Ollama) on `http://localhost:1234/v1`.
2. `python main.py`
3. Fill in settings in the GUI (or rely on saved `config.json`).
4. Click **GENERATE RADIO STATION**.

---

## Manual Music Mode
If no Suno API key is configured, the pipeline looks for `.mp3` files in `input_music/` and processes those instead.

---

## Testing
Run from project root:
```powershell
python -m py_compile app_gui.py
python -c "import sys; sys.path.insert(0, '.'); from tts_client import *; from suno_client import *; from pipeline import *; from app_gui import *; print('All modules OK')"
```
