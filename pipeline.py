import os
import random
import shutil
from llm_client import generate_script
from tts_client import generate_voice, get_user_info
from suno_client import generate_suno_song
from audio_processor import apply_radio_effect, create_radioext_metadata


def run_generation_pipeline(config, log_callback, mode="fresh",
                            existing_tracks=None, new_interludes=0, new_songs=0):
    """
    Orchestrates Radio Station generation.

    mode="fresh" (default): create a brand-new station from scratch.
    mode="continue": appends new interludes + songs to an existing station.

    In continue mode:
      - existing_tracks: list of filenames already in the station.
      - new_interludes: how many anchor interlude segments to add.
      - new_songs: how many songs to add.
      - New tracks are numbered after all existing tracks.
      - Metadata is merged (existing + new tracks).
    """

    def log(msg):
        log_callback(msg)

    def log_ok(msg):
        log_callback(f"  ✅ {msg}")

    def log_err(msg):
        log_callback(f"  ❌ ERROR: {msg}")

    def log_warn(msg):
        log_callback(f"  ⚠️  WARNING: {msg}")

    is_continue = mode == "continue" and existing_tracks is not None

    if is_continue:
        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        log("📀 CyberRadio-Gen — Adding Tracks")
        log(f"    Existing tracks: {len(existing_tracks)}")
        log(f"    Adding: {new_interludes} interlude(s) + {new_songs} song(s)")
        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    else:
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

    tracks = list(existing_tracks) if existing_tracks else []
    failed_steps = []

    # Parse highest track number from existing files to continue numbering
    max_track_num = 0
    existing_song_count = 0
    for t in tracks:
        try:
            num = int(t[:3])
            max_track_num = max(max_track_num, num)
        except ValueError:
            pass
        if "Suno_Song" in t:
            existing_song_count += 1
    track_offset = max_track_num

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

    # ── STEP 1: Generate Anchorman Script(s) ───────────────────────────────
    if is_continue and new_interludes > 0:
        step_label = f"1/4: Generating {new_interludes} Anchorman Interlude(s)"
    else:
        step_label = "1/4: Generating Anchorman Script"

    log("")
    log(f"── {step_label} ──")
    system_prompt = config.get("host_prompt", "You are a cynical, dynamic radio host in Night City.")

    scripts_to_generate = []
    if is_continue:
        for i in range(new_interludes):
            user_prompt = (
                "Write a punchy, energetic 2-sentence radio interlude for a Night City radio show. "
                f"The station \"{config['station_name']}\" already has {len(tracks)} tracks playing. "
                "This interlude plays BETWEEN songs. Be charismatic, sarcastic and theatrical. "
                "Reference Night City events — corpo raids, cyberpsychos, street gossip, "
                "the latest news from the combat zone. "
                "Make it feel like a natural continuation of the broadcast. "
                "Output ONLY the spoken lines."
            )
            script = generate_script(
                config["llm_api_url"],
                config["llm_provider"],
                system_prompt,
                user_prompt
            )
            if script.startswith("Error"):
                log_err(f"Interlude {i+1} script failed — {script}")
                failed_steps.append(f"LLM (interlude {i+1})")
                scripts_to_generate.append(None)
            else:
                log_ok(f"Interlude {i+1} script ({len(script)} chars)")
                log(f"  📝 Preview: {script[:80].strip()}...")
                scripts_to_generate.append(script)
    else:
        user_prompt = (
            "Write a high-energy, theatrical radio intro for a Night City cyberpunk station. "
            "Start with a greeting like 'Good morning Night City!' "
            "Be charismatic, sarcastic, and street-smart. Reference current events "
            "(corpo wars, cyberpsychos, braindance craze, the latest gang dispute). "
            "End by hinting at the first song. Output ONLY the 3-4 spoken sentences."
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
        scripts_to_generate.append(intro_script)

    # ── STEP 2: Synthesize Anchorman Voice ─────────────────────────────────
    if scripts_to_generate and any(s is not None for s in scripts_to_generate):
        log("")
        log(f"── STEP 2/4: Synthesizing Anchor Voice(s) (ElevenLabs) ──")

        for i, script in enumerate(scripts_to_generate):
            if script is None:
                continue

            if is_continue:
                track_num = track_offset + i + 1
                out_name = f"{str(track_num).zfill(3)}_Anchorman_Interlude_{i + 1}.mp3"
                title = f"interlude_{i + 1}"
            else:
                track_num = 1
                out_name = "001_Anchorman_Intro.mp3"
                title = "intro"

            if config.get("elevenlabs_api_key") and "ElevenLabs" not in str(failed_steps):
                temp_voice = os.path.join(temp_dir, f"raw_voice_{title}.mp3")
                success, msg = generate_voice(
                    config["elevenlabs_api_key"],
                    config["elevenlabs_voice_id"],
                    script,
                    temp_voice
                )

                if success:
                    out_path = os.path.join(output_dir, out_name)
                    log(f"  {msg}")
                    log(f"  🎙️  Applying radio FM filter...")
                    ok, filter_msg = apply_radio_effect(temp_voice, out_path)
                    if ok:
                        log_ok(f"Voice track saved → {out_name}")
                    else:
                        log_warn(f"FM filter failed ({filter_msg}). Saving unfiltered.")
                        shutil.copy(temp_voice, out_path)
                    tracks.append(out_name)
                else:
                    log_err(f"Voice synthesis failed for {out_name} — skipping.")
                    log_err(f"  {msg}")
                    failed_steps.append("ElevenLabs")
            else:
                log_warn(f"Skipping voice track (no valid ElevenLabs key).")
                # Still append the track name placeholder? No — user won't have a file.
    else:
        log_warn("No script available — skipping voice step.")

    # ── STEP 3: Generate Music ─────────────────────────────────────────────
    song_count = new_songs if is_continue else max(1, config.get("song_count", 3))
    if song_count > 0 and config.get("suno_api_key"):
        log("")
        log(f"── STEP 3/4: Preparing Music ({song_count} song(s)) ──")

        song_styles = config.get("song_styles", [])
        if not song_styles:
            song_styles = ["synth-pop, cyberpunk, 100 BPM, female vocals, dark atmosphere"]

        lyrics_prompt = (
            "A cyberpunk song set in Night City — neon-lit streets, fast cars, "
            "corporate greed, street punks, chrome and steel, surviving in a dystopian future. "
            "References to night markets, netrunners, corpo wars, and the everlasting neon glow."
        )

        log(f"  📝 Lyrical theme: Night City lifestyle (Suno generates lyrics)")

        for song_idx in range(song_count):
            abs_song_idx = existing_song_count + song_idx  # for display naming
            track_num = track_offset + song_idx + 1
            style = random.choice(song_styles)
            log(f"")
            log(f"  ── Song {song_idx + 1}/{song_count} ──")
            log(f"  🎵 Style: {style[:100].strip()}...")

            temp_song = os.path.join(temp_dir, f"raw_song_{track_num}.mp3")
            title = f"{config['station_name']} — Track {abs_song_idx + 1}"
            success, image_url, msg = generate_suno_song(
                config["suno_api_key"],
                lyrics_prompt,
                style,
                title,
                temp_song,
                log_callback=log
            )

            if success:
                out_name = f"{str(track_num).zfill(3)}_Suno_Song_{abs_song_idx + 1}.mp3"
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

                if image_url and not os.path.exists(os.path.join(output_dir, "cover.jpg")):
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

    elif song_count > 0 and not config.get("suno_api_key"):
        log("")
        log("── STEP 3/4: Preparing Music ──")
        log("  📂 No Suno API Key — checking /input_music for manual files...")
        manual_files = sorted([f for f in os.listdir(input_dir) if f.lower().endswith('.mp3')])
        if manual_files:
            log(f"  Found {len(manual_files)} manual file(s): {', '.join(manual_files)}")
            for i, f in enumerate(manual_files):
                track_num = track_offset + i + 1 + (1 if not is_continue and i == 0 else 0)
                in_path  = os.path.join(input_dir, f)
                out_name = f"{str(track_num).zfill(3)}_Music_{f}"
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

    # ── STEP 4: Create/Update RadioExt Metadata ────────────────────────────
    log("")
    log("── STEP 4/4: Creating RadioExt metadata.json ──")

    # Always rebuild metadata from actual files on disk to avoid sync issues.
    actual_tracks = sorted(
        [f for f in os.listdir(output_dir) if f.lower().endswith(".mp3")],
        key=lambda x: int(x[:3]) if x[:3].isdigit() else 999
    )

    if not actual_tracks:
        log_err("No tracks found in output folder — metadata.json not created.")
        log("")
        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        log("❌ Pipeline FAILED — zero tracks produced.")
        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return "failed"

    ok = create_radioext_metadata(
        config["station_name"],
        config["station_frequency"],
        config["station_volume"],
        actual_tracks,
        output_dir,
        config.get("station_icon", "UIIcon.RadioElectronic")
    )
    if not ok:
        log_err("Failed to write metadata.json. Check folder permissions.")
        log("")
        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        log("❌ Pipeline FAILED — could not write metadata.")
        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return "failed"

    log_ok(f"metadata.json updated with {len(actual_tracks)} track(s).")

    # ── FINAL SUMMARY ──────────────────────────────────────────────────────
    log("")
    log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    total = len(actual_tracks)

    if is_continue:
        new_count = total - track_offset
        if failed_steps:
            log("⚠️  Adding tracks finished WITH ISSUES")
            log(f"    Added {new_count} new track(s). Total: {total}")
            log(f"    Failed: {', '.join(failed_steps)}")
        else:
            log("🎉 Tracks added successfully!")
            log(f"    Added {new_count} new track(s). Total: {total}")
    else:
        if failed_steps:
            log("⚠️  Pipeline finished WITH ISSUES")
            log(f"    Generated {total} track(s).")
            log(f"    Failed steps: {', '.join(failed_steps)}")
            log(f"    The station is usable but incomplete.")
        else:
            log("🎉 Pipeline COMPLETE — Station is ready!")
            log(f"    Generated {total} track(s).")

    log(f"📁 Output folder: {output_dir}")
    log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    if not failed_steps:
        return "complete"
    return "partial"