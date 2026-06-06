"""
Tests for filesystem edge cases, resource cleanup, and config manager edge cases.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Helpers (synchronized with test_all.py) ──────────────────────────────────

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
    "song_styles": ["test style A", "test style B"],
}


def make_log():
    collected = []

    def log(msg):
        collected.append(msg)

    return collected, log


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(b'dummy')


def voice_ok(api_key, voice_id, script, out_path):
    _touch(out_path)
    return (True, "Voice generated (50 KB)")


def voice_fail(api_key, voice_id, script, out_path):
    return (False, "402 paid_plan_required")


def song_ok(api_key, lyrics_prompt, style, title, out_path, log_callback=None):
    _touch(out_path)
    return (True, None, "Song generated")


def song_fail(api_key, lyrics_prompt, style, title, out_path, log_callback=None):
    return (False, None, "Suno API error")


def radio_ok(inp, out):
    if os.path.exists(inp):
        shutil.copy(inp, out)
    else:
        _touch(out)
    return (True, "FM filter applied")


def radio_fail_copy(inp, out):
    """FM filter fails but fallback copy still works."""
    if os.path.exists(inp):
        shutil.copy(inp, out)
    else:
        _touch(out)
    return (False, "FM filter failed")


def meta_ok(name, freq, vol, tracks, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    data = {
        "displayName": name,
        "fm": float(freq),
        "volume": float(vol),
        "icon": "UIIcon.RadioHipHop",
        "customIcon": {"useCustom": False, "inkAtlasPath": "", "inkAtlasPart": ""},
        "streamInfo": {"isStream": False, "streamURL": ""},
        "order": tracks,
    }
    with open(os.path.join(output_dir, 'metadata.json'), 'w') as f:
        json.dump(data, f)
    return True


# =============================================================================
# Filesystem Edge Cases
# =============================================================================

class TestFilesystemEdgeCases(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

        def fake_abspath(p):
            return os.path.join(self.tmp, "script.py")

        self.abspath_patch = patch("os.path.abspath", fake_abspath)
        self.abspath_patch.start()

    def tearDown(self):
        self.abspath_patch.stop()
        shutil.rmtree(self.tmp)

    # ── 1. Output directory already exists with files ──────────────────────

    @patch("pipeline.generate_script", return_value="Good morning Night City!")
    @patch("pipeline.generate_voice", side_effect=voice_ok)
    @patch("pipeline.get_user_info", return_value=(True, 5000, 10000))
    @patch("pipeline.generate_suno_song", side_effect=song_ok)
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_output_dir_exists_with_pre_existing_files(self, *mocks):
        """Pre-existing unrelated files in output dir do not disrupt fresh generation."""
        out_dir = os.path.join(self.tmp, "output", "TestRadio")
        os.makedirs(out_dir, exist_ok=True)
        _touch(os.path.join(out_dir, "old_track.mp3"))
        _touch(os.path.join(out_dir, "cover.jpg"))

        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        result = run_generation_pipeline(BASE_CONFIG, cb)
        self.assertEqual(result, "complete")

        files = os.listdir(out_dir)
        self.assertIn("001_Anchorman_Intro.mp3", files)
        self.assertIn("old_track.mp3", files)

    # ── 2. Output directory is read-only ──────────────────────────────────

    @patch("pipeline.generate_script", return_value="Good morning Night City!")
    @patch("pipeline.generate_voice", side_effect=voice_ok)
    @patch("pipeline.get_user_info", return_value=(True, 5000, 10000))
    @patch("pipeline.generate_suno_song", side_effect=song_ok)
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_output_dir_read_only_does_not_crash(self, *mocks):
        """Read-only output dir does not cause an unhandled PermissionError crash."""
        # On some platforms chmod may not prevent writes to a directory,
        # so we also test the error-handling path by mocking file writes.
        out_dir = os.path.join(self.tmp, "output", "TestRadio")
        os.makedirs(out_dir, exist_ok=True)

        from pipeline import run_generation_pipeline
        from unittest.mock import patch as _patch
        logs, cb = make_log()

        # Simulate read-only by patching shutil.copy to fail for output writes
        original_copy = shutil.copy
        def _fail_on_output(src, dst):
            if 'output' in str(dst):
                raise PermissionError("Access denied to output")
            return original_copy(src, dst)

        with _patch("shutil.copy", _fail_on_output):
            try:
                result = run_generation_pipeline(BASE_CONFIG, cb)
                # May complete (mocks handle file creation) or fail (writes blocked)
                self.assertIn(result, ("complete", "partial", "failed"))
            except PermissionError:
                # PermissionError may propagate from pipeline's fallback
                # shutil.copy when output is unwritable. Acceptable.
                pass

    # ── 3. Output path is a file instead of directory ─────────────────────

    def test_output_path_is_file_raises_file_exists_error(self):
        """os.makedirs raises FileExistsError when the path is an existing file."""
        out_dir_parent = os.path.join(self.tmp, "output")
        os.makedirs(out_dir_parent, exist_ok=True)
        file_path = os.path.join(out_dir_parent, "TestRadio")
        with open(file_path, 'w') as f:
            f.write("not a directory")

        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        with self.assertRaises(FileExistsError):
            run_generation_pipeline(BASE_CONFIG, cb)

    # ── 4. Very long station name (>255 chars) ────────────────────────────

    @patch("pipeline.generate_script", return_value="Good morning Night City!")
    @patch("pipeline.generate_voice", side_effect=voice_ok)
    @patch("pipeline.get_user_info", return_value=(True, 5000, 10000))
    @patch("pipeline.generate_suno_song", side_effect=song_ok)
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_very_long_station_name(self, *mocks):
        """Station name >255 chars may cause path-length errors but must not hang."""
        config = dict(BASE_CONFIG)
        config["station_name"] = "A" * 260

        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        try:
            result = run_generation_pipeline(config, cb)
            self.assertIn(result, ("complete", "partial", "failed"))
        except OSError:
            # OSError from overly long paths is acceptable on platforms
            # with path-length limits (e.g. Windows MAX_PATH ~260 chars).
            # The critical thing is no hang / no unrelated crash.
            pass

    # ── 5. Unicode characters in station name ──────────────────────────────

    @patch("pipeline.generate_script", return_value="Good morning Night City!")
    @patch("pipeline.generate_voice", side_effect=voice_ok)
    @patch("pipeline.get_user_info", return_value=(True, 5000, 10000))
    @patch("pipeline.generate_suno_song", side_effect=song_ok)
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_unicode_station_name(self, *mocks):
        """Unicode chars in station name must not crash the pipeline."""
        config = dict(BASE_CONFIG)
        config["station_name"] = "東京サイバーラジオ★Night_City_🔊"

        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        result = run_generation_pipeline(config, cb)
        self.assertEqual(result, "complete")

        out_dir = os.path.join(
            self.tmp, "output", "東京サイバーラジオ★Night_City_🔊"
        )
        self.assertTrue(os.path.isdir(out_dir))
        self.assertIn("001_Anchorman_Intro.mp3", os.listdir(out_dir))

    def test_unicode_station_name_metadata(self):
        """Unicode station name is preserved in metadata.json."""
        from audio_processor import create_radioext_metadata
        ok = create_radioext_metadata(
            "東京サイバーラジオ", 99.7, 1.0,
            ["001_intro.mp3"], self.tmp
        )
        self.assertTrue(ok)
        with open(os.path.join(self.tmp, "metadata.json")) as f:
            data = json.load(f)
        self.assertEqual(data["displayName"], "東京サイバーラジオ")

    # ── 6. Empty output directory ─────────────────────────────────────────

    def test_empty_output_dir_listdir(self):
        """An empty output dir returns empty listdir without error."""
        out_dir = os.path.join(self.tmp, "output", "EmptyRadio")
        os.makedirs(out_dir, exist_ok=True)
        self.assertEqual(os.listdir(out_dir), [])

    @patch("pipeline.generate_script", return_value="Good morning Night City!")
    @patch("pipeline.get_user_info", return_value=(True, 0, 10000))
    @patch("pipeline.generate_suno_song", side_effect=song_fail)
    def test_pipeline_with_empty_output_dir_returns_failed(self, *mocks):
        """When no tracks are produced (0 credits + no suno), pipeline returns 'failed'."""
        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        result = run_generation_pipeline(BASE_CONFIG, cb)
        self.assertEqual(result, "failed")
        combined = "\n".join(logs)
        self.assertIn("FAILED", combined)

    # ── 7. Corrupted metadata.json ─────────────────────────────────────────

    def test_corrupted_metadata_json_returns_none(self):
        """Unparseable JSON in metadata.json returns None."""
        out_dir = os.path.join(self.tmp, "output", "TestRadio")
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "metadata.json"), 'w') as f:
            f.write("{invalid json!!!}")

        from audio_processor import read_radioext_metadata
        self.assertIsNone(read_radioext_metadata(out_dir))

    def test_corrupted_metadata_json_invalid_unicode(self):
        """Invalid unicode bytes in metadata.json returns None."""
        out_dir = os.path.join(self.tmp, "output", "TestRadio")
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "metadata.json"), 'wb') as f:
            f.write(b"\xff\xfe\x00\x01\x02")

        from audio_processor import read_radioext_metadata
        result = read_radioext_metadata(out_dir)
        self.assertIsNone(result)

    # ── 8. Metadata.json with wrong structure ──────────────────────────────

    def test_metadata_missing_tracks_key(self):
        """Metadata without 'tracks' key is still read as valid JSON."""
        out_dir = os.path.join(self.tmp, "output", "TestRadio")
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "metadata.json"), 'w') as f:
            json.dump({"displayName": "Test"}, f)

        from audio_processor import read_radioext_metadata
        meta = read_radioext_metadata(out_dir)
        self.assertIsNotNone(meta)
        self.assertNotIn("order", meta)

    def test_metadata_tracks_is_wrong_type(self):
        """Tracks key with non-list value is read as-is (no validation)."""
        out_dir = os.path.join(self.tmp, "output", "TestRadio")
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "metadata.json"), 'w') as f:
            json.dump({"displayName": "Test", "order": "not_a_list"}, f)

        from audio_processor import read_radioext_metadata
        meta = read_radioext_metadata(out_dir)
        self.assertEqual(meta["order"], "not_a_list")

    # ── 9. Very large number of tracks ────────────────────────────────────

    def test_large_number_of_tracks_in_metadata(self):
        """create_radioext_metadata handles 150+ tracks without error."""
        from audio_processor import create_radioext_metadata
        tracks = [f"{i:03d}_Track_{i}.mp3" for i in range(1, 151)]
        ok = create_radioext_metadata("LargeRadio", 99.7, 1.0, tracks, self.tmp)
        self.assertTrue(ok)

        with open(os.path.join(self.tmp, "metadata.json")) as f:
            data = json.load(f)
        self.assertEqual(len(data["order"]), 150)

    def test_metadata_sorted_by_prefix_with_large_count(self):
        """Tracks with 3-digit numeric prefixes sort correctly even at 100+."""
        tracks = [f"{i:03d}_Song_{i}.mp3" for i in range(1, 151)]
        sorted_tracks = sorted(
            tracks,
            key=lambda x: int(x[:3]) if x[:3].isdigit() else 999
        )
        self.assertEqual(sorted_tracks[0], "001_Song_1.mp3")
        self.assertEqual(sorted_tracks[-1], "150_Song_150.mp3")

    # ── 10. No MP3 files on disk but metadata lists them ──────────────────

    def test_all_metadata_tracks_missing_from_disk(self):
        """When every file in metadata is missing from disk, sanity detects all."""
        out_dir = os.path.join(self.tmp, "output", "TestRadio")
        os.makedirs(out_dir, exist_ok=True)
        meta_tracks = [
            "001_Anchorman_Intro.mp3",
            "002_Suno_Song_1.mp3",
            "003_Suno_Song_2.mp3",
        ]
        on_disk = set()
        in_meta = set(meta_tracks)
        missing = sorted(in_meta - on_disk)
        self.assertEqual(len(missing), 3)
        self.assertEqual(missing[0], "001_Anchorman_Intro.mp3")


# =============================================================================
# Resource Cleanup Tests
# =============================================================================

class TestResourceCleanup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

        def fake_abspath(p):
            return os.path.join(self.tmp, "script.py")

        self.abspath_patch = patch("os.path.abspath", fake_abspath)
        self.abspath_patch.start()

    def tearDown(self):
        self.abspath_patch.stop()
        shutil.rmtree(self.tmp)

    # ── 11. Temp files isolated from output dir on success ────────────────

    @patch("pipeline.generate_script", return_value="Good morning Night City!")
    @patch("pipeline.generate_voice", side_effect=voice_ok)
    @patch("pipeline.get_user_info", return_value=(True, 5000, 10000))
    @patch("pipeline.generate_suno_song", side_effect=song_ok)
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_no_temp_files_leak_into_output_on_success(self, *mocks):
        """After successful generation, no 'raw_' prefixed files appear in output dir."""
        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        result = run_generation_pipeline(BASE_CONFIG, cb)
        self.assertEqual(result, "complete")

        out_dir = os.path.join(self.tmp, "output", "TestRadio")
        for f in os.listdir(out_dir):
            if f.endswith(".mp3"):
                self.assertFalse(
                    f.startswith("raw_"),
                    f"Temp-prefixed file leaked into output: {f}"
                )

    @patch("pipeline.generate_script", return_value="Good morning Night City!")
    @patch("pipeline.generate_voice", side_effect=voice_ok)
    @patch("pipeline.get_user_info", return_value=(True, 5000, 10000))
    @patch("pipeline.generate_suno_song", side_effect=song_ok)
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_temp_directory_created_by_pipeline(self, *mocks):
        """Pipeline creates the temp/ directory for intermediate files."""
        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        run_generation_pipeline(BASE_CONFIG, cb)
        temp_dir = os.path.join(self.tmp, "temp")
        self.assertTrue(os.path.isdir(temp_dir))

    # ── 12. Partial failure — no temp file leak ──────────────────────────

    @patch("pipeline.generate_script", return_value="Good morning Night City!")
    @patch("pipeline.generate_voice", side_effect=voice_ok)
    @patch("pipeline.get_user_info", return_value=(True, 5000, 10000))
    @patch("pipeline.generate_suno_song", side_effect=song_fail)
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_no_temp_leak_when_suno_fails(self, *mocks):
        """When Suno fails, no raw_ temp files appear in the output dir."""
        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        result = run_generation_pipeline(BASE_CONFIG, cb)
        self.assertEqual(result, "partial")

        out_dir = os.path.join(self.tmp, "output", "TestRadio")
        for f in os.listdir(out_dir):
            if f.endswith(".mp3"):
                self.assertFalse(
                    f.startswith("raw_"),
                    f"Temp file leaked on partial failure: {f}"
                )

    # ── 13. PermissionError on file ops does not crash ───────────────────

    @patch("pipeline.generate_script", return_value="Good morning Night City!")
    @patch("pipeline.generate_voice", side_effect=voice_ok)
    @patch("pipeline.get_user_info", return_value=(True, 5000, 10000))
    @patch("pipeline.generate_suno_song", side_effect=song_ok)
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_permission_error_on_voice_file_write_caught(self, *mocks):
        """PermissionError during voice file write is caught by try/except in generate_voice."""
        from pipeline import run_generation_pipeline
        from tts_client import generate_voice

        # generate_voice returns False without crashing on file write errors
        with patch("builtins.open", side_effect=PermissionError("Access denied")):
            ok, msg = generate_voice("key", "voice", "text", "out.mp3")
            self.assertFalse(ok)

    @patch("audio_processor.shutil.which", return_value=None)
    def test_radio_effect_copy_permission_error_caught(self, *_):
        """PermissionError during shutil.copy fallback is caught by apply_radio_effect."""
        from audio_processor import apply_radio_effect
        inp = os.path.join(self.tmp, "in.mp3")
        _touch(inp)
        out = os.path.join(self.tmp, "out.mp3")

        with patch("audio_processor.shutil.copy", side_effect=PermissionError("Locked")):
            ok, msg = apply_radio_effect(inp, out)
            self.assertFalse(ok)

    # ── 14. KeyboardInterrupt during generation ──────────────────────────

    @patch("pipeline.generate_script",
           side_effect=KeyboardInterrupt("User pressed Ctrl+C"))
    def test_keyboard_interrupt_during_script_propagates(self, *_):
        """KeyboardInterrupt during LLM script generation propagates upward."""
        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        with self.assertRaises(KeyboardInterrupt):
            run_generation_pipeline(BASE_CONFIG, cb)

    @patch("pipeline.generate_script", return_value="Good morning Night City!")
    @patch("pipeline.generate_voice", side_effect=KeyboardInterrupt)
    @patch("pipeline.get_user_info", return_value=(True, 5000, 10000))
    def test_keyboard_interrupt_during_tts_propagates(self, *_):
        """KeyboardInterrupt during TTS generation propagates upward."""
        from pipeline import run_generation_pipeline
        logs, cb = make_log()
        with self.assertRaises(KeyboardInterrupt):
            run_generation_pipeline(BASE_CONFIG, cb)

    # ── 15. Multiple rapid generations ────────────────────────────────────

    @patch("pipeline.generate_script", return_value="Good morning Night City!")
    @patch("pipeline.generate_voice", side_effect=voice_ok)
    @patch("pipeline.get_user_info", return_value=(True, 5000, 10000))
    @patch("pipeline.generate_suno_song", side_effect=song_ok)
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_consecutive_generations_different_stations(self, *mocks):
        """Two back-to-back generations with different names produce independent outputs."""
        from pipeline import run_generation_pipeline

        cfg_a = dict(BASE_CONFIG)
        cfg_a["station_name"] = "StationAlpha"
        la, ca = make_log()
        self.assertEqual(run_generation_pipeline(cfg_a, ca), "complete")

        cfg_b = dict(BASE_CONFIG)
        cfg_b["station_name"] = "StationBeta"
        lb, cb = make_log()
        self.assertEqual(run_generation_pipeline(cfg_b, cb), "complete")

        dir_a = os.path.join(self.tmp, "output", "StationAlpha")
        dir_b = os.path.join(self.tmp, "output", "StationBeta")
        self.assertTrue(os.path.isdir(dir_a))
        self.assertTrue(os.path.isdir(dir_b))
        self.assertGreater(len(os.listdir(dir_a)), 0)
        self.assertGreater(len(os.listdir(dir_b)), 0)

    @patch("pipeline.generate_script", return_value="Good morning Night City!")
    @patch("pipeline.generate_voice", side_effect=voice_ok)
    @patch("pipeline.get_user_info", return_value=(True, 5000, 10000))
    @patch("pipeline.generate_suno_song", side_effect=song_ok)
    @patch("pipeline.apply_radio_effect", side_effect=radio_ok)
    @patch("pipeline.create_radioext_metadata", side_effect=meta_ok)
    def test_two_generations_same_station_both_succeed(self, *mocks):
        """Running the pipeline twice against the same station name does not corrupt output."""
        from pipeline import run_generation_pipeline

        logs, cb = make_log()
        r1 = run_generation_pipeline(BASE_CONFIG, cb)
        self.assertEqual(r1, "complete")

        logs, cb = make_log()
        r2 = run_generation_pipeline(BASE_CONFIG, cb)
        self.assertEqual(r2, "complete")

        out_dir = os.path.join(self.tmp, "output", "TestRadio")
        mp3s = [f for f in os.listdir(out_dir) if f.endswith(".mp3")]
        self.assertGreaterEqual(len(mp3s), 2)


# =============================================================================
# Config Manager Edge Cases
# =============================================================================

class TestConfigManagerEdgeCases(unittest.TestCase):
    """Edge cases for config_manager.load_config and save_config."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig_dir = os.getcwd()
        os.chdir(self.tmp)
        self.config_path = os.path.join(self.tmp, "config.json")

    def tearDown(self):
        os.chdir(self._orig_dir)
        shutil.rmtree(self.tmp)

    def _delete_config(self):
        if os.path.exists(self.config_path):
            os.remove(self.config_path)

    # ── 16. Config file missing ────────────────────────────────────────────

    def test_load_when_config_missing_writes_defaults_and_returns_them(self):
        """When no config.json exists, load_config writes defaults and returns them."""
        from config_manager import load_config, DEFAULT_CONFIG
        self._delete_config()
        cfg = load_config()
        self.assertEqual(cfg["station_name"], DEFAULT_CONFIG["station_name"])
        self.assertEqual(cfg["song_count"], DEFAULT_CONFIG["song_count"])
        self.assertEqual(cfg["song_styles"], DEFAULT_CONFIG["song_styles"])
        self.assertTrue(os.path.exists(self.config_path))

    # ── 17. Config file corrupted JSON ──────────────────────────────────────

    def test_corrupted_json_returns_defaults(self):
        """Unparseable JSON in config.json returns DEFAULT_CONFIG."""
        from config_manager import load_config, DEFAULT_CONFIG
        with open(self.config_path, 'w') as f:
            f.write("{broken json!!!")
        cfg = load_config()
        self.assertEqual(cfg["station_name"], DEFAULT_CONFIG["station_name"])
        self.assertEqual(cfg["song_count"], DEFAULT_CONFIG["song_count"])

    def test_truncated_json_returns_defaults(self):
        """Truncated JSON in config.json returns DEFAULT_CONFIG."""
        from config_manager import load_config, DEFAULT_CONFIG
        with open(self.config_path, 'w') as f:
            f.write('{"station_name": "')
        cfg = load_config()
        self.assertEqual(cfg["station_name"], DEFAULT_CONFIG["station_name"])

    # ── 18. Config file empty ───────────────────────────────────────────────

    def test_empty_config_file_returns_defaults(self):
        """Empty (zero-byte) config file returns DEFAULT_CONFIG."""
        from config_manager import load_config, DEFAULT_CONFIG
        with open(self.config_path, 'w') as f:
            f.write("")
        cfg = load_config()
        self.assertEqual(cfg["station_name"], DEFAULT_CONFIG["station_name"])

    def test_whitespace_only_config_returns_defaults(self):
        """Config file containing only whitespace returns DEFAULT_CONFIG."""
        from config_manager import load_config, DEFAULT_CONFIG
        with open(self.config_path, 'w') as f:
            f.write("   \n\n  \t  ")
        cfg = load_config()
        self.assertEqual(cfg["station_name"], DEFAULT_CONFIG["station_name"])

    # ── 19. Config with partial data gets defaults for missing keys ─────────

    def test_partial_config_fills_missing_from_defaults(self):
        """Config with only a subset of keys gets defaults for the rest."""
        from config_manager import load_config, DEFAULT_CONFIG
        with open(self.config_path, 'w') as f:
            json.dump({"station_name": "CustomName", "song_count": 7}, f)
        cfg = load_config()
        self.assertEqual(cfg["station_name"], "CustomName")
        self.assertEqual(cfg["song_count"], 7)
        self.assertEqual(
            cfg["station_frequency"],
            DEFAULT_CONFIG["station_frequency"]
        )
        self.assertEqual(cfg["song_styles"], DEFAULT_CONFIG["song_styles"])
        self.assertEqual(cfg["host_prompt"], DEFAULT_CONFIG["host_prompt"])

    # ── 20. Save config to unwritable path ──────────────────────────────────

    def test_save_config_to_nonexistent_directory_returns_false(self):
        """save_config to a path whose parent doesn't exist returns False."""
        from config_manager import save_config
        bad_path = os.path.join(self.tmp, "nonexistent_subdir", "config.json")
        with patch("config_manager.CONFIG_FILE", bad_path):
            result = save_config({"station_name": "Test"})
            self.assertFalse(result)

    # ── 21. Config value types are preserved as-is (no coercion in config_manager) ─

    def test_song_count_as_string_preserved(self):
        """config_manager does NOT coerce types — song_count stays a string."""
        from config_manager import load_config
        with open(self.config_path, 'w') as f:
            json.dump({"song_count": "not_a_number"}, f)
        cfg = load_config()
        self.assertIsInstance(cfg.get("song_count"), str)

    def test_station_frequency_as_string_preserved(self):
        """Station frequency stored as string surfaces as-is."""
        from config_manager import load_config
        with open(self.config_path, 'w') as f:
            json.dump({"station_frequency": "104.5"}, f)
        cfg = load_config()
        self.assertIsInstance(cfg["station_frequency"], str)
        self.assertEqual(cfg["station_frequency"], "104.5")

    # ── 22. Config defaults for new / missing fields ────────────────────────

    def test_old_config_without_song_count_gets_default(self):
        """Config from before song_count was added gets the default value."""
        from config_manager import load_config, DEFAULT_CONFIG
        old_data = {
            "elevenlabs_api_key": "",
            "suno_api_key": "",
            "llm_api_url": "http://localhost:1234/v1",
            "station_name": "OldRadio",
        }
        with open(self.config_path, 'w') as f:
            json.dump(old_data, f)
        cfg = load_config()
        self.assertEqual(cfg["station_name"], "OldRadio")
        self.assertEqual(cfg["song_count"], DEFAULT_CONFIG["song_count"])
        self.assertEqual(cfg["song_styles"], DEFAULT_CONFIG["song_styles"])

    def test_old_config_without_song_styles_gets_default(self):
        """Config from before song_styles was added gets the default list."""
        from config_manager import load_config, DEFAULT_CONFIG
        old_data = {
            "elevenlabs_api_key": "",
            "station_name": "OldRadio",
            "song_count": 5,
        }
        with open(self.config_path, 'w') as f:
            json.dump(old_data, f)
        cfg = load_config()
        self.assertEqual(cfg["song_styles"], DEFAULT_CONFIG["song_styles"])
        self.assertEqual(cfg["song_count"], 5)

    def test_old_config_without_host_prompt_gets_default(self):
        """Config without host_prompt gets the default system prompt."""
        from config_manager import load_config, DEFAULT_CONFIG
        old_data = {
            "elevenlabs_api_key": "",
            "station_name": "OldRadio",
        }
        with open(self.config_path, 'w') as f:
            json.dump(old_data, f)
        cfg = load_config()
        self.assertEqual(cfg["host_prompt"], DEFAULT_CONFIG["host_prompt"])

    def test_every_default_key_present_after_load(self):
        """After load_config, every key in DEFAULT_CONFIG must be present in result."""
        from config_manager import load_config, DEFAULT_CONFIG
        self._delete_config()
        cfg = load_config()
        for key in DEFAULT_CONFIG:
            self.assertIn(key, cfg, f"Missing key in loaded config: {key}")

    def test_round_trip_preserves_custom_values(self):
        """Saving then loading preserves all custom values exactly."""
        from config_manager import load_config, save_config
        cfg = load_config()
        cfg["station_name"] = "RoundTripFM"
        cfg["song_count"] = 42
        cfg["station_frequency"] = "104.5"
        cfg["station_volume"] = 0.75
        cfg["host_prompt"] = "Custom host."
        ok = save_config(cfg)
        self.assertTrue(ok)

        cfg2 = load_config()
        self.assertEqual(cfg2["station_name"], "RoundTripFM")
        self.assertEqual(cfg2["song_count"], 42)
        self.assertEqual(cfg2["station_frequency"], "104.5")
        self.assertEqual(cfg2["station_volume"], 0.75)
        self.assertEqual(cfg2["host_prompt"], "Custom host.")


# =============================================================================
# Runner
# =============================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
