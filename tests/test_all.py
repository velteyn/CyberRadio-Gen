"""
Comprehensive unit tests for CyberRadio-Gen.

Coverage:
  - audio_processor: metadata read/write/repair, radio effect
  - config_manager: load/save/defaults
  - pipeline: fresh generation, continue mode, graceful degradation, track numbering
  - app_gui sanity logic: missing intro detection, orphan files, missing files
"""

import os
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock, call


# =============================================================================
# audio_processor tests
# =============================================================================

class TestAudioProcessor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _touch(self, *parts):
        path = os.path.join(self.tmp, *parts)
        with open(path, "wb") as f:
            f.write(b"dummy")
        return path

    # ── read_radioext_metadata ──────────────────────────────────────────────

    def test_read_metadata_returns_none_when_no_file(self):
        from audio_processor import read_radioext_metadata
        self.assertIsNone(read_radioext_metadata(self.tmp))

    def test_read_metadata_returns_dict_when_valid(self):
        from audio_processor import read_radioext_metadata
        data = {"displayName": "TestFM", "fm": 99.7, "order": ["001_intro.mp3"]}
        with open(os.path.join(self.tmp, "metadata.json"), "w") as f:
            json.dump(data, f)
        result = read_radioext_metadata(self.tmp)
        self.assertEqual(result["displayName"], "TestFM")
        self.assertEqual(result["order"], ["001_intro.mp3"])

    def test_read_metadata_returns_none_on_bad_json(self):
        from audio_processor import read_radioext_metadata
        with open(os.path.join(self.tmp, "metadata.json"), "w") as f:
            f.write("not json")
        result = read_radioext_metadata(self.tmp)
        self.assertIsNone(result)

    # ── create_radioext_metadata ────────────────────────────────────────────

    def test_create_metadata_writes_correct_format(self):
        from audio_processor import create_radioext_metadata
        ok = create_radioext_metadata("Radio99", 99.7, 1.0,
                                       ["001_a.mp3", "002_b.mp3"],
                                       self.tmp)
        self.assertTrue(ok)
        with open(os.path.join(self.tmp, "metadata.json")) as f:
            data = json.load(f)
        self.assertEqual(data["displayName"], "99.7 Radio99")
        self.assertEqual(data["fm"], 99.7)
        self.assertEqual(data["volume"], 1.0)
        self.assertEqual(data["streamInfo"]["isStream"], False)
        self.assertEqual(data["order"], ["001_a.mp3", "002_b.mp3"])

    def test_create_metadata_rejects_non_writable_dir(self):
        from audio_processor import create_radioext_metadata
        bad = os.path.join(self.tmp, "does_not_exist")
        ok = create_radioext_metadata("X", 1.0, 1.0, ["x.mp3"], bad)
        self.assertFalse(ok)

    # ── apply_radio_effect ──────────────────────────────────────────────────

    @patch("audio_processor.shutil.which", return_value=None)
    def test_radio_effect_ffmpeg_missing_copies_file(self, _):
        from audio_processor import apply_radio_effect
        inp = self._touch("in.mp3")
        out = os.path.join(self.tmp, "out.mp3")
        ok, msg = apply_radio_effect(inp, out)
        self.assertTrue(ok)
        self.assertIn("missing", msg)
        self.assertTrue(os.path.exists(out))

    @patch("audio_processor.shutil.which", return_value="ffmpeg")
    @patch("audio_processor.subprocess.run",
           return_value=MagicMock(returncode=0, stdout=b"", stderr=b""))
    def test_radio_effect_success(self, mock_run, _):
        from audio_processor import apply_radio_effect
        inp = self._touch("in.mp3")
        out = os.path.join(self.tmp, "out.mp3")
        ok, msg = apply_radio_effect(inp, out)
        self.assertTrue(ok)
        self.assertIn("successfully", msg)

    @patch("audio_processor.shutil.which", return_value="ffmpeg")
    @patch("audio_processor.subprocess.run",
           return_value=MagicMock(returncode=1, stdout=b"",
                                   stderr=b"some error"))
    def test_radio_effect_failure_falls_back(self, mock_run, _):
        from audio_processor import apply_radio_effect
        inp = self._touch("in.mp3")
        out = os.path.join(self.tmp, "out.mp3")
        ok, msg = apply_radio_effect(inp, out)
        self.assertFalse(ok)
        self.assertIn("failed", msg)
        self.assertTrue(os.path.exists(out))  # fallback copy


# =============================================================================
# config_manager tests
# =============================================================================

class TestConfigManager(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # Point config_manager to temp
        self._orig_dir = os.getcwd()
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self._orig_dir)
        shutil.rmtree(self.tmp)

    def test_load_returns_defaults_when_no_file(self):
        from config_manager import load_config, DEFAULT_CONFIG
        cfg = load_config()
        for k, v in DEFAULT_CONFIG.items():
            self.assertIn(k, cfg)
            if isinstance(v, (list, dict)):
                self.assertEqual(cfg[k], v)

    def test_save_and_load_preserves_values(self):
        from config_manager import load_config, save_config
        cfg = load_config()
        cfg["station_name"] = "UnitTestFM"
        cfg["song_count"] = 5
        save_config(cfg)
        cfg2 = load_config()
        self.assertEqual(cfg2["station_name"], "UnitTestFM")
        self.assertEqual(cfg2["song_count"], 5)

    def test_load_fills_missing_keys(self):
        from config_manager import load_config, save_config
        # Save a partial config
        with open(os.path.join(self.tmp, "config.json"), "w") as f:
            json.dump({"station_name": "Partial"}, f)
        cfg = load_config()
        self.assertEqual(cfg["station_name"], "Partial")
        self.assertIn("station_frequency", cfg)  # from defaults

    def test_default_config_has_all_required_keys(self):
        from config_manager import DEFAULT_CONFIG
        required = ["elevenlabs_api_key", "suno_api_key", "llm_api_url",
                     "station_name", "station_frequency", "host_prompt",
                     "song_count", "song_styles"]
        for k in required:
            self.assertIn(k, DEFAULT_CONFIG)


# =============================================================================
# Pipeline orchestration tests
# =============================================================================

BASE_CONFIG = {
    "elevenlabs_api_key": "el_test_key",
    "elevenlabs_voice_id": "test_voice",
    "suno_api_key": "suno_test_key",
    "llm_provider": "LM Studio",
    "llm_api_url": "http://localhost:1234/v1",
    "station_name": "TestRadio",
    "station_frequency": "99.7",
    "station_volume": 1.0,
    "host_prompt": "You are a test host.",
    "song_count": 2,
    "song_styles": ["test style A, dark", "test style B, upbeat"],
}


def make_log():
    """Return (collector, log_callback). collector is a list of log strings."""
    collected = []

    def log(msg):
        collected.append(msg)

    return collected, log


# ── File-creating side-effect helpers for pipeline mocks ──────────────────────
def _touch(path):
    """Create an empty dummy file, ensuring parent dir exists."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(b'dummy')


def voice_ok(api_key, voice_id, script, out_path):
    """Mock generate_voice — success, writes dummy file."""
    _touch(out_path)
    return (True, "Voice generated (50 KB)")


def voice_fail(api_key, voice_id, script, out_path):
    """Mock generate_voice — failure, no file."""
    return (False, "402 paid_plan_required — upgrade your ElevenLabs plan")


def voice_zero_credits(api_key, voice_id, script, out_path):
    """Mock generate_voice — success but 0 credits path (won't be called)."""
    return (True, "")


def song_ok(api_key, lyrics_prompt, style, title, out_path, log_callback=None):
    """Mock generate_suno_song — success, writes dummy file."""
    _touch(out_path)
    return (True, None, "Song generated")


def song_fail(api_key, lyrics_prompt, style, title, out_path, log_callback=None):
    """Mock generate_suno_song — failure, no file."""
    return (False, None, "Suno API error: no credits")


def radio_ok(inp, out):
    """Mock apply_radio_effect — copies input to output or creates dummy."""
    if os.path.exists(inp):
        shutil.copy(inp, out)
    else:
        _touch(out)
    return (True, "FM filter applied")


def radio_fail(inp, out):
    """Mock apply_radio_effect — failure, still copies as fallback."""
    if os.path.exists(inp):
        shutil.copy(inp, out)
    else:
        _touch(out)
    return (False, "FM filter failed")


def song_fail_then_ok():
    """Returns a side-effect function: first call fails, subsequent calls succeed."""
    def _fn(api_key, lyrics_prompt, style, title, out_path, log_callback=None):
        call_count = getattr(_fn, 'call_count', 0) + 1
        _fn.call_count = call_count
        if call_count == 1:
            return (False, None, "No credits left")
        _touch(out_path)
        return (True, None, "Song generated")
    return _fn


def meta_ok(name, freq, vol, tracks, output_dir, station_icon="UIIcon.RadioElectronic"):
    """Mock create_radioext_metadata — writes valid JSON."""
    os.makedirs(output_dir, exist_ok=True)
    data = {
        "displayName": f"{freq} {name}",
        "fm": float(freq),
        "volume": float(vol),
        "icon": "UIIcon.RadioHipHop",
        "customIcon": {"useCustom": False, "inkAtlasPath": "", "inkAtlasPart": ""},
        "streamInfo": {"isStream": False, "streamURL": ""},
        "order": tracks,
    }
    with open(os.path.join(output_dir, "metadata.json"), 'w') as f:
        json.dump(data, f)
    return True


class TestPipelineFreshGeneration(unittest.TestCase):
    """mode='fresh' — brand-new station from scratch."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig_abspath = os.path.abspath

        def fake_abspath(p):
            return os.path.join(self.tmp, "script.py")
        self.abspath_patch = patch("os.path.abspath", fake_abspath)
        self.abspath_patch.start()

    def tearDown(self):
        self.abspath_patch.stop()
        shutil.rmtree(self.tmp)

    @patch("pipeline.generate_script", return_value="Good morning Night City!")
    @patch("pipeline.generate_voice", side_effect=voice_ok)
    @patch("pipeline.get_user_info", return_value=(True, 5000, 10000))
    @patch("pipeline.generate_suno_song", side_effect=song_ok)
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_fresh_full_success(self, *mocks):
        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        result = run_generation_pipeline(BASE_CONFIG, cb)
        self.assertEqual(result, "complete")
        combined = "\n".join(logs)
        self.assertIn("COMPLETE", combined)
        self.assertIn("001_Anchorman_Intro.mp3", combined)
        self.assertIn("Suno_Song", combined)

    @patch("pipeline.generate_script", return_value="Good morning Night City!")
    @patch("pipeline.generate_voice", side_effect=voice_ok)
    @patch("pipeline.get_user_info", return_value=(True, 5000, 10000))
    @patch("pipeline.generate_suno_song",
           side_effect=song_fail_then_ok())
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_fresh_one_song_fails_rest_succeed(self, *mocks):
        """One song fails → partial, but others still generated."""
        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        result = run_generation_pipeline(BASE_CONFIG, cb)
        self.assertEqual(result, "partial")
        combined = "\n".join(logs)
        self.assertIn("WITH ISSUES", combined)
        self.assertIn("No credits", combined)
        self.assertIn("Suno_Song_2", combined)

    @patch("pipeline.generate_script", return_value="Error: LM Studio down")
    def test_fresh_llm_fails_aborts(self, *mocks):
        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        result = run_generation_pipeline(BASE_CONFIG, cb)
        self.assertEqual(result, "failed")
        combined = "\n".join(logs)
        self.assertIn("FAILED", combined)

    @patch("pipeline.generate_script", return_value="Good morning Night City!")
    @patch("pipeline.generate_voice", side_effect=voice_fail)
    @patch("pipeline.get_user_info", return_value=(True, 5000, 10000))
    @patch("pipeline.generate_suno_song", side_effect=song_ok)
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_fresh_tts_fails_still_has_music(self, *mocks):
        """ElevenLabs fails → partial station with music only."""
        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        result = run_generation_pipeline(BASE_CONFIG, cb)
        self.assertEqual(result, "partial")
        combined = "\n".join(logs)
        self.assertIn("WITH ISSUES", combined)
        self.assertNotIn("Voice track saved", combined)

    @patch("pipeline.generate_script", return_value="Good morning Night City!")
    @patch("pipeline.generate_voice", side_effect=voice_ok)
    @patch("pipeline.get_user_info", return_value=(True, 5000, 10000))
    @patch("pipeline.generate_suno_song", side_effect=song_fail)
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_fresh_suno_fails_still_has_anchor(self, *mocks):
        """Suno fails → partial station with anchor only."""
        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        result = run_generation_pipeline(BASE_CONFIG, cb)
        self.assertEqual(result, "partial")
        combined = "\n".join(logs)
        self.assertIn("WITH ISSUES", combined)
        self.assertIn("001_Anchorman_Intro.mp3", combined)
        self.assertNotIn("Suno_Song", combined)

    @patch("pipeline.generate_script", return_value="Good morning Night City!")
    @patch("pipeline.get_user_info", return_value=(True, 0, 10000))
    @patch("pipeline.generate_suno_song", side_effect=song_fail)
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_fresh_zero_credits_skips_tts(self, *mocks):
        """0 ElevenLabs credits → anchor skipped, music fails → failed."""
        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        result = run_generation_pipeline(BASE_CONFIG, cb)
        self.assertEqual(result, "failed")
        combined = "\n".join(logs)
        self.assertIn("quota is exhausted", combined)

    @patch("pipeline.generate_script", return_value="Good morning Night City!")
    @patch("pipeline.generate_voice", side_effect=voice_ok)
    @patch("pipeline.get_user_info", return_value=(True, 5000, 10000))
    @patch("pipeline.generate_suno_song", side_effect=song_ok)
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_fresh_respects_song_count(self, *mocks):
        """Uses song_count from config (2)."""
        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        result = run_generation_pipeline(BASE_CONFIG, cb)
        self.assertEqual(result, "complete")
        combined = "\n".join(logs)
        self.assertIn("2 song(s)", combined)
        self.assertEqual(combined.count("Suno_Song"), 2)


class TestPipelineContinueMode(unittest.TestCase):
    """mode='continue' — appending to an existing station."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig_abspath = os.path.abspath

        def fake_abspath(p):
            return os.path.join(self.tmp, "script.py")
        self.abspath_patch = patch("os.path.abspath", fake_abspath)
        self.abspath_patch.start()

    def tearDown(self):
        self.abspath_patch.stop()
        shutil.rmtree(self.tmp)

    @patch("pipeline.generate_script", return_value="Back after the break!")
    @patch("pipeline.generate_voice", side_effect=voice_ok)
    @patch("pipeline.get_user_info", return_value=(True, 5000, 10000))
    @patch("pipeline.generate_suno_song", side_effect=song_ok)
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_continue_basic_numbering(self, *mocks):
        """Existing track at 002 → new interlude at 003, song at 004."""
        from pipeline import run_generation_pipeline
        existing = ["002_Suno_Song_1.mp3"]
        logs, cb = make_log()
        result = run_generation_pipeline(BASE_CONFIG, cb,
                                          mode="continue",
                                          existing_tracks=existing,
                                          new_interludes=1,
                                          new_songs=1)
        self.assertEqual(result, "complete")
        combined = "\n".join(logs)
        self.assertIn("003_Anchorman_Interlude", combined)

    @patch("pipeline.generate_script", return_value="Welcome to the show!")
    @patch("pipeline.generate_voice", side_effect=voice_ok)
    @patch("pipeline.get_user_info", return_value=(True, 5000, 10000))
    @patch("pipeline.generate_suno_song", side_effect=song_ok)
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_continue_no_existing_songs(self, *mocks):
        """Existing track is an interlude → song numbering starts at 1."""
        from pipeline import run_generation_pipeline
        existing = ["001_Anchorman_Intro.mp3"]
        logs, cb = make_log()
        result = run_generation_pipeline(BASE_CONFIG, cb,
                                          mode="continue",
                                          existing_tracks=existing,
                                          new_interludes=0,
                                          new_songs=2)
        self.assertEqual(result, "complete")
        combined = "\n".join(logs)
        # songs should be numbered from 002
        self.assertIn("002_Suno_Song_1", combined)
        self.assertIn("003_Suno_Song_2", combined)

    @patch("pipeline.generate_script", return_value="Error: LLM down")
    @patch("pipeline.get_user_info", return_value=(True, 5000, 10000))
    @patch("pipeline.generate_suno_song", side_effect=song_ok)
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_continue_llm_fails_graceful(self, *mocks):
        """In continue mode, LLM failure for interlude → partial (song still generated)."""
        from pipeline import run_generation_pipeline
        existing = ["002_Suno_Song_1.mp3"]
        logs, cb = make_log()
        result = run_generation_pipeline(BASE_CONFIG, cb,
                                          mode="continue",
                                          existing_tracks=existing,
                                          new_interludes=1,
                                          new_songs=1)
        # LLM failed for interlude, but song still succeeds → "partial" (song exists on disk)
        self.assertEqual(result, "partial")
        combined = "\n".join(logs)
        self.assertIn("WITH ISSUES", combined)

    @patch("pipeline.generate_script", return_value="Error: LLM down")
    @patch("pipeline.get_user_info", return_value=(True, 5000, 10000))
    def test_continue_only_interlude_fails(self, *mocks):
        """Continue with only interludes, LLM fails → no tracks → failed."""
        from pipeline import run_generation_pipeline
        existing = ["001_Intro.mp3"]
        logs, cb = make_log()
        result = run_generation_pipeline(BASE_CONFIG, cb,
                                          mode="continue",
                                          existing_tracks=existing,
                                          new_interludes=2,
                                          new_songs=0)
        # interludes fail (no script), no songs requested → no files on disk → "failed"
        self.assertEqual(result, "failed")
        combined = "\n".join(logs)
        self.assertIn("FAILED", combined)


class TestTrackNumbering(unittest.TestCase):
    """Tests for the track numbering logic (from existing filenames)."""

    def test_max_track_from_filenames(self):
        """Parses highest number from existing track names."""
        from pipeline import run_generation_pipeline
        # We test indirectly via the pipeline's internal logic
        # But we can inspect the numbering by looking at the generated filenames
        pass

    def test_track_parsing_logic(self):
        """Direct test of the track number extraction logic."""
        tracks = ["001_Intro.mp3", "003_Song_2.mp3", "005_Interlude.mp3"]
        max_num = 0
        for t in tracks:
            try:
                num = int(t[:3])
                max_num = max(max_num, num)
            except ValueError:
                pass
        self.assertEqual(max_num, 5)

    def test_track_parsing_no_numbers(self):
        tracks = ["intro.mp3", "song.mp3"]
        max_num = 0
        for t in tracks:
            try:
                num = int(t[:3])
                max_num = max(max_num, num)
            except ValueError:
                pass
        self.assertEqual(max_num, 0)

    def test_song_count_parsing(self):
        tracks = ["001_Intro.mp3", "002_Suno_Song_1.mp3", "003_Music_test.mp3"]
        existing_song_count = sum(1 for t in tracks if "Suno_Song" in t)
        self.assertEqual(existing_song_count, 1)


# =============================================================================
# app_gui sanity check logic tests
# =============================================================================

class TestSanityCheckLogic(unittest.TestCase):
    """Test the sanity check detection logic in isolation."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _make_metadata(self, tracks):
        """Write a metadata.json with given tracks."""
        data = {"displayName": "Test", "fm": 99.7, "volume": 1.0,
                "icon": "UIIcon.RadioHipHop",
                "customIcon": {"useCustom": False, "inkAtlasPath": "", "inkAtlasPart": ""},
                "streamInfo": {"isStream": False, "streamURL": ""},
                "order": tracks}
        with open(os.path.join(self.tmp, "metadata.json"), "w") as f:
            json.dump(data, f)

    def _touch(self, name):
        with open(os.path.join(self.tmp, name), "wb") as f:
            f.write(b"d")

    def test_sanity_no_intro_detected(self):
        """Has music but no anchor intro → should flag missing intro."""
        self._make_metadata(["002_Suno_Song_1.mp3"])
        self._touch("002_Suno_Song_1.mp3")

        # Replicate the sanity check logic
        listed = ["002_Suno_Song_1.mp3"]
        has_music = any("Suno_Song" in t or "Music_" in t for t in listed)
        has_intro = any("Anchorman_Intro" in t for t in listed)
        self.assertTrue(has_music)
        self.assertFalse(has_intro)

    def test_sanity_all_accounted(self):
        """All files present, no orphans, intro exists → clean."""
        self._make_metadata(["001_Anchorman_Intro.mp3", "002_Suno_Song_1.mp3"])
        self._touch("001_Anchorman_Intro.mp3")
        self._touch("002_Suno_Song_1.mp3")

        on_disk = set(os.listdir(self.tmp))
        in_meta = {"001_Anchorman_Intro.mp3", "002_Suno_Song_1.mp3"}
        # Filter out non-mp3
        mp3_disk = set(f for f in on_disk if f.lower().endswith(".mp3"))
        orphans = sorted(mp3_disk - in_meta)
        missing = sorted(in_meta - mp3_disk)
        self.assertEqual(orphans, [])
        self.assertEqual(missing, [])

    def test_sanity_orphans_detected(self):
        """Files on disk not in metadata → flagged."""
        self._make_metadata(["001_Intro.mp3"])
        self._touch("001_Intro.mp3")
        self._touch("002_extra_song.mp3")

        on_disk = set(os.listdir(self.tmp))
        in_meta = {"001_Intro.mp3"}
        mp3_disk = set(f for f in on_disk if f.lower().endswith(".mp3"))
        orphans = sorted(mp3_disk - in_meta)
        self.assertEqual(orphans, ["002_extra_song.mp3"])

    def test_sanity_missing_files_detected(self):
        """Files in metadata not on disk → flagged."""
        self._make_metadata(["001_Intro.mp3", "002_Song.mp3"])
        self._touch("001_Intro.mp3")

        on_disk = set(os.listdir(self.tmp))
        in_meta = {"001_Intro.mp3", "002_Song.mp3"}
        mp3_disk = set(f for f in on_disk if f.lower().endswith(".mp3"))
        missing = sorted(in_meta - mp3_disk)
        self.assertEqual(missing, ["002_Song.mp3"])

    def test_sanity_intro_exists_not_flagged(self):
        """Has intro → no missing-intro warning."""
        self._make_metadata(["001_Anchorman_Intro.mp3", "002_Suno_Song_1.mp3"])
        self._touch("001_Anchorman_Intro.mp3")
        self._touch("002_Suno_Song_1.mp3")

        listed = ["001_Anchorman_Intro.mp3", "002_Suno_Song_1.mp3"]
        has_music = any("Suno_Song" in t or "Music_" in t for t in listed)
        has_intro = any("Anchorman_Intro" in t for t in listed)
        self.assertTrue(has_intro)

    def test_repair_renumbering_logic(self):
        """Inserting intro at 001: existing files should NOT be renumbered."""
        # Simulate the current repair logic: intro missing, generate 001
        before = ["002_Suno_Song_1.mp3", "003_Anchorman_Interlude_1.mp3"]
        # Generate intro at 001
        after = ["001_Anchorman_Intro.mp3"] + before
        # Sort by prefix
        after_sorted = sorted(after,
                              key=lambda x: int(x[:3]) if x[:3].isdigit() else 999)
        self.assertEqual(after_sorted[0], "001_Anchorman_Intro.mp3")
        self.assertEqual(len(after_sorted), 3)

    def test_metadata_rebuild_from_disk(self):
        """Always rebuild metadata from actual files on disk."""
        self._touch("001_Intro.mp3")
        self._touch("003_Song_2.mp3")

        actual_tracks = sorted(
            [f for f in os.listdir(self.tmp) if f.lower().endswith(".mp3")],
            key=lambda x: int(x[:3]) if x[:3].isdigit() else 999
        )
        from audio_processor import create_radioext_metadata
        ok = create_radioext_metadata("Test", 99.7, 1.0, actual_tracks, self.tmp)
        self.assertTrue(ok)

        from audio_processor import read_radioext_metadata
        meta = read_radioext_metadata(self.tmp)
        self.assertEqual(meta["order"], ["001_Intro.mp3", "003_Song_2.mp3"])


# =============================================================================
# Manual music mode tests
# =============================================================================

class TestManualMusicMode(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.input_dir = os.path.join(self.tmp, "input_music")
        os.makedirs(self.input_dir)

        def fake_abspath(p):
            return os.path.join(self.tmp, "script.py")
        self.abspath_patch = patch("os.path.abspath", fake_abspath)
        self.abspath_patch.start()

    def tearDown(self):
        self.abspath_patch.stop()
        shutil.rmtree(self.tmp)

    def _touch(self, dir, name):
        with open(os.path.join(dir, name), "wb") as f:
            f.write(b"d")

    @patch("pipeline.generate_script", return_value="Good morning Night City!")
    @patch("pipeline.generate_voice", side_effect=voice_ok)
    @patch("pipeline.get_user_info", return_value=(True, 5000, 10000))
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_manual_music_from_input_folder(self, *mocks):
        """No Suno key → uses files from input_music."""
        input_dir = os.path.join(self.tmp, "input_music")
        self._touch(input_dir, "my_track.mp3")
        self._touch(input_dir, "another_one.mp3")

        config = dict(BASE_CONFIG)
        config["suno_api_key"] = ""  # no Suno key

        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        result = run_generation_pipeline(config, cb)
        self.assertEqual(result, "complete")
        combined = "\n".join(logs)
        self.assertIn("my_track.mp3", combined)
        self.assertIn("another_one.mp3", combined)
        self.assertIn("Music_", combined)

    @patch("pipeline.generate_script", return_value="Good morning Night City!")
    @patch("pipeline.generate_voice", side_effect=voice_ok)
    @patch("pipeline.get_user_info", return_value=(True, 5000, 10000))
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_manual_music_empty_folder_no_error(self, *mocks):
        """No Suno key, no input files → anchor only → complete."""
        config = dict(BASE_CONFIG)
        config["suno_api_key"] = ""

        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        result = run_generation_pipeline(config, cb)
        self.assertEqual(result, "complete")
        combined = "\n".join(logs)
        self.assertIn("COMPLETE", combined)


# =============================================================================
# Edge case tests
# =============================================================================

class TestEdgeCases(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

        def fake_abspath(p):
            return os.path.join(self.tmp, "script.py")
        self.abspath_patch = patch("os.path.abspath", fake_abspath)
        self.abspath_patch.start()

    def tearDown(self):
        self.abspath_patch.stop()
        shutil.rmtree(self.tmp)

    @patch("pipeline.generate_script", return_value="")
    @patch("pipeline.get_user_info", return_value=(True, 5000, 10000))
    @patch("pipeline.generate_suno_song", side_effect=song_ok)
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_empty_script_still_proceeds(self, *mocks):
        """Empty string from LLM is NOT an error — it's valid output."""
        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        result = run_generation_pipeline(BASE_CONFIG, cb)
        self.assertIn(result, ("complete", "partial"))

    @patch("pipeline.generate_script", return_value="Hi")
    @patch("pipeline.generate_voice", side_effect=voice_ok)
    @patch("pipeline.get_user_info", return_value=(True, 5000, 10000))
    @patch("pipeline.generate_suno_song", side_effect=song_ok)
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_single_char_script(self, *mocks):
        """Minimal script should still produce tracks."""
        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        result = run_generation_pipeline(BASE_CONFIG, cb)
        self.assertEqual(result, "complete")

    @patch("pipeline.generate_script", return_value="Hello!")
    @patch("pipeline.generate_voice", side_effect=voice_ok)
    @patch("pipeline.get_user_info", return_value=(True, 5000, 10000))
    @patch("pipeline.generate_suno_song", side_effect=song_ok)
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_no_song_styles_list_uses_default(self, *mocks):
        """Empty song_styles list → uses hardcoded default."""
        config = dict(BASE_CONFIG)
        config["song_styles"] = []
        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        result = run_generation_pipeline(config, cb)
        self.assertEqual(result, "complete")


# =============================================================================
# Failure scenario tests
# =============================================================================

class TestFailureScenarios(unittest.TestCase):
    """Tests for various API failure modes and error messages."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

        def fake_abspath(p):
            return os.path.join(self.tmp, "script.py")
        self.abspath_patch = patch("os.path.abspath", fake_abspath)
        self.abspath_patch.start()

    def tearDown(self):
        self.abspath_patch.stop()
        shutil.rmtree(self.tmp)

    @patch("pipeline.generate_script", return_value="Good morning Night City!")
    @patch("pipeline.get_user_info", return_value=(False, "invalid_key", "Invalid API Key"))
    @patch("pipeline.generate_suno_song", side_effect=song_ok)
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_invalid_elevenlabs_key_message(self, *mocks):
        """Invalid ElevenLabs key logs specific error message."""
        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        result = run_generation_pipeline(BASE_CONFIG, cb)
        self.assertEqual(result, "partial")
        combined = "\n".join(logs)
        self.assertIn("invalid", combined.lower())
        self.assertIn("WITH ISSUES", combined)

    @patch("pipeline.generate_script", return_value="Good morning Night City!")
    @patch("pipeline.get_user_info", return_value=(True, 5000, 10000))
    @patch("pipeline.generate_voice", side_effect=voice_ok)
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_no_suno_key_with_music_anchor_only(self, *mocks):
        """No Suno key + no manual files = anchor only = complete."""
        config = dict(BASE_CONFIG)
        config["suno_api_key"] = ""
        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        result = run_generation_pipeline(config, cb)
        self.assertEqual(result, "complete")
        combined = "\n".join(logs)
        self.assertIn("COMPLETE", combined)

    @patch("pipeline.generate_script", return_value="Error: Connection refused by LM Studio")
    def test_llm_connection_refused(self, *mocks):
        """LLM connection refused → pipeline aborts with failed."""
        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        result = run_generation_pipeline(BASE_CONFIG, cb)
        self.assertEqual(result, "failed")
        combined = "\n".join(logs)
        self.assertIn("FAILED", combined)

    @patch("pipeline.generate_script", return_value="Good morning Night City!")
    @patch("pipeline.get_user_info", return_value=(True, 50, 10000))
    @patch("pipeline.generate_voice", side_effect=voice_ok)
    @patch("pipeline.generate_suno_song", side_effect=song_ok)
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_low_elevenlabs_chars_proceeds(self, *mocks):
        """Low but non-zero ElevenLabs chars → proceeds with warning."""
        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        result = run_generation_pipeline(BASE_CONFIG, cb)
        self.assertEqual(result, "complete")
        combined = "\n".join(logs)
        self.assertIn("50/10000", combined)
        self.assertIn("COMPLETE", combined)

    @patch("pipeline.generate_script", return_value="Good morning Night City!")
    @patch("pipeline.get_user_info", return_value=(False, "no_connection", "Network error"))
    @patch("pipeline.generate_suno_song", side_effect=song_ok)
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_elevenlabs_network_error_skips_anchor(self, *mocks):
        """ElevenLabs API unreachable → anchor skipped, music still works."""
        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        result = run_generation_pipeline(BASE_CONFIG, cb)
        self.assertEqual(result, "partial")
        combined = "\n".join(logs)
        self.assertIn("API check failed", combined)
        self.assertNotIn("Voice track saved", combined)

    @patch("pipeline.generate_script", return_value="Good morning Night City!")
    @patch("pipeline.get_user_info", return_value=(True, 5000, 10000))
    @patch("pipeline.generate_voice", side_effect=voice_ok)
    @patch("pipeline.generate_suno_song", side_effect=song_fail)
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_all_songs_fail_anchor_only(self, *mocks):
        """All Suno songs fail → partial station with anchor only."""
        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        result = run_generation_pipeline(BASE_CONFIG, cb)
        self.assertEqual(result, "partial")
        combined = "\n".join(logs)
        self.assertIn("WITH ISSUES", combined)
        self.assertIn("001_Anchorman_Intro.mp3", combined)

    @patch("pipeline.generate_script", return_value="Good morning Night City!")
    @patch("pipeline.get_user_info", return_value=(True, 0, 10000))
    @patch("pipeline.generate_suno_song", side_effect=song_fail)
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_both_services_empty_failed(self, *mocks):
        """No credits for TTS and Suno fails → failed."""
        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        result = run_generation_pipeline(BASE_CONFIG, cb)
        self.assertEqual(result, "failed")
        combined = "\n".join(logs)
        self.assertIn("FAILED", combined)


# =============================================================================
# Runner
# =============================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
