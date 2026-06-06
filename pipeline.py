import os
import random
import shutil
from llm_client import generate_script
from tts_client import generate_voice, get_user_info
from suno_client import generate_suno_song
from audio_processor import apply_radio_effect, create_radioext_metadata

def run_generation_pipeline(config, log_callback):
    """
    Orchestrates the complete Radio Station generation process.
    Returns True on full success, False if any step failed.

    Design: non-critical steps (paid APIs) degrade gracefully.
    If ElevenLabs fails, you still get a music-only station.
    If Suno fails, you still get an anchor-only station.
    Only the free LLM step is a hard gate — no script = nothing to do.
    """

    def log(msg):
        log_callback(msg)

    def log_ok(msg):
        log_callback(f"  ✅ {msg}")

    def log_err(msg):
        log_callback(f"  ❌ ERROR: {msg}")

    def log_warn(msg):
        log_callback(f"  ⚠️  WARNING: {msg}")

    log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log("🎙️  CyberRadio-Gen — Starting Pipeline")
    log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    base_dir = os.path.dirname(os.path.abspath(__file__))
    input_dir  = os.path.join(base_dir, "input_music")
    output_dir = os.path.join(base_dir, "output", config["station_name"].replace(" ", "_"))
    temp_dir   = os.path.join(base_dir, "temp")

    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)
    log(f"📁 Output folder: {output_dir}")

    tracks = []
    failed_steps = []

    # ── Pre-check ElevenLabs credits ───────────────────────────────────────
    log("")
    log("── Pre-check: ElevenLabs account ──")
    el_key = config.get("elevenlabs_api_key", "")
    if el_key:
        ok, remaining, limit = get_user_info(el_key)
        if ok:
            log(f"  ✅ ElevenLabs: {remaining}/{limit} monthly characters remaining.")
            if remaining <= 0:
                log_err("ElevenLabs monthly character quota is exhausted — anchor voice will be skipped.")
                failed_steps.append("ElevenLabs (0 credits)")
        elif remaining == "invalid_key":
            log_err("ElevenLabs API key is invalid or expired — anchor voice will be skipped.")
            log_err("  Go to elevenlabs.io → Profile → API Keys to generate a new one.")
            failed_steps.append("ElevenLabs (invalid key)")
        else:
            log_warn(f"ElevenLabs API check failed: {limit}")
    else:
        log_warn("No ElevenLabs API key — anchor voice will be skipped.")

    # ── STEP 1: Generate Anchorman Script ──────────────────────────────────
    # This is the only hard gate — free (local LLM), no credits spent.
    log("")
    log("── STEP 1/4: Generating Anchorman Script ──")
    system_prompt = config.get("host_prompt", "You are a cynical, dynamic radio host in Night City.")
    user_prompt = (
        "Write a punchy, energetic 3-sentence radio intro for your cyberpunk radio station. "
        "Start mid-sentence, be charismatic, sarcastic and theatrical. "
        "Reference Night City or corporate dystopia. Output ONLY the spoken lines."
    )

    intro_script = generate_script(
        config["llm_api_url"],
        config["llm_provider"],
        system_prompt,
        user_prompt
    )

    if intro_script.startswith("Error"):
        log_err(f"LLM script generation failed — check your LLM server (LM Studio / Ollama).")
        log_err(f"  {intro_script}")
        log_err("Cannot continue without a script. Aborting.")
        log("")
        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        log("❌ Pipeline FAILED — no script generated.")
        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return "failed"

    log_ok(f"Script generated ({len(intro_script)} chars)")
    log(f"  📝 Preview: {intro_script[:80].strip()}...")

    # ── STEP 2: Synthesize Anchorman Voice ─────────────────────────────────
    log("")
    log("── STEP 2/4: Synthesizing Anchorman Voice (ElevenLabs) ──")

    if config.get("elevenlabs_api_key") and "ElevenLabs" not in str(failed_steps):
        temp_intro = os.path.join(temp_dir, "raw_intro.mp3")
        success, msg = generate_voice(
            config["elevenlabs_api_key"],
            config["elevenlabs_voice_id"],
            intro_script,
            temp_intro
        )

        if success:
            out_intro = os.path.join(output_dir, "001_Anchorman_Intro.mp3")
            log(f"  {msg}")
            log(f"  🎙️  Applying radio FM filter...")
            ok, filter_msg = apply_radio_effect(temp_intro, out_intro)
            if ok:
                log_ok("Voice track saved → 001_Anchorman_Intro.mp3")
            else:
                log_warn(f"FM filter failed ({filter_msg}). Saving unfiltered.")
                shutil.copy(temp_intro, out_intro)
            tracks.append("001_Anchorman_Intro.mp3")
        else:
            log_err(f"ElevenLabs voice synthesis failed — skipping anchor.")
            log_err(f"  {msg}")
            failed_steps.append("ElevenLabs")
    else:
        log_warn("Skipping anchor voice (no valid ElevenLabs key).")

    # ── STEP 3: Generate Music ─────────────────────────────────────────────
    log("")
    log("── STEP 3/4: Preparing Music ──")

    if config.get("suno_api_key"):
        log("  🎵 Suno API Key found — generating music automatically...")

        song_styles = config.get("song_styles", [])
        if not song_styles:
            song_styles = ["synth-pop, cyberpunk, 100 BPM, female vocals, dark atmosphere"]
        song_count = max(1, config.get("song_count", 3))

        # Lyrical theme (Suno generates lyrics from this description)
        lyrics_prompt = (
            "A cyberpunk song set in Night City — neon-lit streets, fast cars, "
            "corporate greed, street punks, chrome and steel, surviving in a dystopian future. "
            "References to night markets, netrunners, corpo wars, and the everlasting neon glow."
        )

        log(f"  🎵 Generating {song_count} song(s) with rotating styles...")
        log(f"  📝 Lyrical theme: Night City lifestyle")
        log(f"     (Suno generates lyrics automatically from this description)")

        for song_idx in range(song_count):
            track_num = song_idx + 2  # 002, 003, ...
            style = random.choice(song_styles)
            log(f"")
            log(f"  ── Song {song_idx + 1}/{song_count} ──")
            log(f"  🎵 Style: {style[:100].strip()}...")

            temp_song = os.path.join(temp_dir, f"raw_song_{song_idx}.mp3")
            title = f"{config['station_name']} — Track {song_idx + 1}"
            success, image_url, msg = generate_suno_song(
                config["suno_api_key"],
                lyrics_prompt,
                style,
                title,
                temp_song,
                log_callback=log
            )

            if success:
                out_name = f"{str(track_num).zfill(3)}_Suno_Song_{song_idx + 1}.mp3"
                out_song = os.path.join(output_dir, out_name)
                log(f"  {msg}")
                log(f"  🎛️  Applying radio FM filter...")
                ok, filter_msg = apply_radio_effect(temp_song, out_song)
                if ok:
                    log_ok(f"Music track saved → {out_name}")
                else:
                    log_warn(f"FM filter failed ({filter_msg}). Saving unfiltered.")
                    shutil.copy(temp_song, out_song)
                    log_ok(f"Music track saved (unfiltered) → {out_name}")
                tracks.append(out_name)

                # Use first successful song's cover art
                if image_url and not any("cover.jpg" in t for t in tracks):
                    try:
                        import requests as req
                        img_r = req.get(image_url, timeout=20)
                        if img_r.status_code == 200:
                            cover_path = os.path.join(output_dir, "cover.jpg")
                            with open(cover_path, 'wb') as f:
                                f.write(img_r.content)
                            log_ok("Station cover art saved → cover.jpg")
                    except Exception as e:
                        log_warn(f"Could not download cover art: {e}")
            else:
                log_err(f"Song {song_idx + 1} failed — {msg}")
                failed_steps.append(f"Suno (song {song_idx + 1})")

    else:
        log("  📂 No Suno API Key — checking /input_music for manual files...")
        manual_files = sorted([f for f in os.listdir(input_dir) if f.lower().endswith('.mp3')])
        if manual_files:
            log(f"  Found {len(manual_files)} manual file(s): {', '.join(manual_files)}")
            for i, f in enumerate(manual_files):
                in_path  = os.path.join(input_dir, f)
                out_name = f"{str(i + 2).zfill(3)}_Music_{f}"
                out_path = os.path.join(output_dir, out_name)
                log(f"  🎛️  Filtering: {f} → {out_name}")
                ok, filter_msg = apply_radio_effect(in_path, out_path)
                if ok:
                    log_ok(f"Track saved → {out_name}")
                else:
                    shutil.copy(in_path, out_path)
                    log_warn(f"Filter failed for {f}. Copied as-is.")
                tracks.append(out_name)
        else:
            log_warn("No manual MP3 files found in /input_music.")

    # ── STEP 4: Create RadioExt Metadata ───────────────────────────────────
    log("")
    log("── STEP 4/4: Creating RadioExt metadata.json ──")

    if not tracks:
        log_err("No tracks were generated at all — metadata.json not created.")
        log("")
        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        log("❌ Pipeline FAILED — zero tracks produced.")
        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return "failed"

    ok = create_radioext_metadata(
        config["station_name"],
        config["station_frequency"],
        config["station_volume"],
        tracks,
        output_dir
    )
    if not ok:
        log_err("Failed to write metadata.json. Check folder permissions.")
        log("")
        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        log("❌ Pipeline FAILED — could not write metadata.")
        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return "failed"

    log_ok(f"metadata.json created with {len(tracks)} track(s).")

    # ── FINAL SUMMARY ──────────────────────────────────────────────────────
    log("")
    log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    if failed_steps:
        log("⚠️  Pipeline finished WITH ISSUES")
        log(f"    Generated {len(tracks)} track(s).")
        log(f"    Failed steps: {', '.join(failed_steps)}")
        log(f"    The station is usable but incomplete.")
    else:
        log("🎉 Pipeline COMPLETE — Station is ready!")
        log(f"    Generated {len(tracks)} track(s).")

    log(f"📁 Output folder: {output_dir}")
    log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    if not failed_steps:
        return "complete"
    return "partial"