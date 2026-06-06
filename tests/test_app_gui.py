"""
Comprehensive unit tests for app_gui.CyberRadioApp.

Tests method logic WITHOUT opening a real GUI window by mocking customtkinter
before import, and patching all external dependencies (pipeline, tts_client,
suno_client, audio_processor, config_manager, requests).
"""

import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, PropertyMock, call, patch

# ── Mock customtkinter BEFORE importing app_gui ──────────────────────────
ctk_mock = MagicMock()
sys.modules["customtkinter"] = ctk_mock

# Mock tkinter (used for messagebox inside methods)
tk_mock = MagicMock()
sys.modules["tkinter"] = tk_mock
sys.modules["tkinter.messagebox"] = MagicMock()
tk_mock.messagebox = sys.modules["tkinter.messagebox"]

class FakeCTk:
    """Minimal CTk base so super().__init__() and attribute access work.

    All attribute access goes through ``__getattribute__``, which checks
    ``_widgets`` first — this allows instance-attribute overrides of class
    methods like ``_station_output_dir``. Unknown attributes are created as
    ``MagicMock`` and *cached* (so ``self.app.title.call_args`` works).
    """

    def __init__(self, *args, **kwargs):
        object.__setattr__(self, "_widgets", {})

    def __getattribute__(self, name):
        if name == "_widgets":
            return object.__getattribute__(self, name)
        widgets = object.__getattribute__(self, "_widgets")
        if name in widgets:
            return widgets[name]
        try:
            return object.__getattribute__(self, name)
        except AttributeError:
            m = MagicMock(name=name)
            widgets[name] = m
            return m

    def __setattr__(self, name, value):
        if name == "_widgets":
            object.__setattr__(self, name, value)
        else:
            self.__dict__.setdefault("_widgets", {})[name] = value

    def __delattr__(self, name):
        d = self.__dict__.get("_widgets", {})
        if name in d:
            del d[name]

    def configure(self, **kwargs):
        pass

    def pack(self, **kwargs):
        pass

    def grid(self, **kwargs):
        pass

    def pack_forget(self):
        pass

    def configure(self, **kwargs):
        pass

    def pack(self, **kwargs):
        pass

    def grid(self, **kwargs):
        pass

    def pack_forget(self):
        pass


# Helper: each widget constructor returns its own fresh MagicMock
def _fresh_mock(*a, **kw):
    return MagicMock()


# Register mocked CTk classes — each call returns a NEW MagicMock
ctk_mock.CTk = FakeCTk
for cls_name in [
    "CTkFrame",
    "CTkLabel",
    "CTkEntry",
    "CTkButton",
    "CTkCheckBox",
    "CTkOptionMenu",
    "CTkTextbox",
    "CTkFont",
    "CTkInputDialog",
    "StringVar",
]:
    setattr(ctk_mock, cls_name, MagicMock(side_effect=_fresh_mock))

ctk_mock.set_appearance_mode = MagicMock()
ctk_mock.set_default_color_theme = MagicMock()

# ── Now import the module under test ─────────────────────────────────────
from app_gui import CyberRadioApp


DEFAULT_CONFIG = {
    "elevenlabs_api_key": "el_test_key",
    "elevenlabs_voice_id": "voice_123",
    "suno_api_key": "sn_test_key",
    "llm_provider": "LM Studio",
    "llm_api_url": "http://localhost:1234/v1",
    "station_name": "TestStation",
    "station_frequency": "99.7",
    "station_volume": 1.0,
    "host_prompt": "You are a cynical host.",
    "song_count": 3,
    "song_styles": ["synthwave", "industrial"],
}


class TestCyberRadioApp(unittest.TestCase):
    """Main test suite for CyberRadioApp."""

    def setUp(self):
        # Start module-level patches so CyberRadioApp() construction works
        self._patchers = []
        self._mocks = {}

        for target, retval in [
            ("app_gui.load_config", dict(DEFAULT_CONFIG)),
            ("app_gui.save_config", True),
            ("app_gui.run_generation_pipeline", "complete"),
            ("app_gui.read_radioext_metadata", None),
            ("app_gui.get_user_info", (True, 5000, 10000)),
            ("app_gui.list_voices", (True, [
                {"voice_id": "v1", "name": "Charlie", "category": "premade"},
                {"voice_id": "v2", "name": "Custom", "category": "generated"},
            ])),
            ("app_gui.get_suno_credits", (True, 50, "OK")),
        ]:
            p = patch(target, return_value=retval)
            mocked = p.start()
            self._patchers.append(p)
            self._mocks[target] = mocked

        self._patcher_req = patch("app_gui.requests.get")
        self.mock_requests_get = self._patcher_req.start()
        self._patchers.append(self._patcher_req)

        # Mock threading.Thread: make threads run synchronously
        self._thread_target = None

        def mock_thread_init(target=None, args=(), kwargs=None, **kw):
            self._thread_target = target
            # Return the standard mock so .start() exists
            return self._thread_mock

        self._patcher_thread = patch("threading.Thread")
        self.mock_thread_class = self._patcher_thread.start()
        self._thread_mock = MagicMock()
        self.mock_thread_class.side_effect = mock_thread_init
        self.mock_thread_class.return_value = self._thread_mock
        self._thread_mock.start.side_effect = lambda: (
            self._thread_target() if self._thread_target else None
        )
        self._patchers.append(self._patcher_thread)

        # Create the app instance
        self.app = CyberRadioApp()

        # Retrieve the ``after`` MagicMock created during __init__ and
        # configure it so ms=0 callbacks fire immediately (for the
        # thread→main-thread handoff). Calls are still recorded for
        # assertions.
        self._after_mock = self.app.after
        self._after_mock.side_effect = lambda ms, fn, *args: fn(*args) if ms == 0 else None

        # Common widget return‑value stubs (each test may override)
        self.app.show_el_key.get = MagicMock(return_value=True)
        self.app.voice_var.get = MagicMock(return_value="[PREMADE] Charlie (v1...)")
        self.app.entry_el_key.get = MagicMock(return_value="el_test_key")
        self.app.entry_suno_key.get = MagicMock(return_value="sn_test_key")
        self.app.entry_station_name.get = MagicMock(return_value="TestStation")
        self.app.entry_station_freq.get = MagicMock(return_value="99.7")
        self.app.entry_song_count.get = MagicMock(return_value="3")
        self.app.entry_llm_url.get = MagicMock(return_value="http://localhost:1234/v1")
        self.app.llm_option.get = MagicMock(return_value="LM Studio")
        self.app.text_song_styles.get = MagicMock(return_value="synthwave\nindustrial\n")
        self.app.spin_interludes.get = MagicMock(return_value="1")
        self.app.spin_songs.get = MagicMock(return_value="1")

        # Default: user cancels any dialog (overridden per test as needed)
        tk_mock.messagebox.askyesno.return_value = False

        # Reset per-test state on shared mocks
        self.app.console.insert.reset_mock()
        self.app.voice_var.set.reset_mock()

        # Temp dir helpers
        self._tmpdirs = []

    def tearDown(self):
        for d in self._tmpdirs:
            shutil.rmtree(d, ignore_errors=True)
        for p in reversed(self._patchers):
            try:
                p.stop()
            except RuntimeError:
                pass

    # ── helpers ────────────────────────────────────────────────────────────

    def _make_temp_dir(self):
        d = tempfile.mkdtemp()
        self._tmpdirs.append(d)
        return d

    def _set_station_output_dir(self, path):
        self.app._station_output_dir = MagicMock(return_value=path)

    def _find_after_call(self, ms, func):
        for c in self._after_mock.call_args_list:
            args = c[0]
            if len(args) >= 2 and args[0] == ms and args[1] == func:
                return True, args, c[1]
        return False, None, {}

    # ━━━━━━━━━━━━ BASIC CONSTRUCTION (8 tests) ━━━━━━━━━━━━━━━━━━━━━━━━━━

    def test_init_sets_title(self):
        """Title contains 'CyberRadio-Gen'."""
        self.assertIn("CyberRadio-Gen", self.app.title.call_args[0][0])

    def test_init_loads_config(self):
        """load_config was called during __init__."""
        self._mocks["app_gui.load_config"].assert_called_once()

    def test_init_creates_widgets(self):
        """Key widget attributes exist after init."""
        self.assertIsNotNone(self.app.entry_el_key)
        self.assertIsNotNone(self.app.console)
        self.assertIsNotNone(self.app.btn_generate)
        self.assertIsNotNone(self.app.btn_save)
        self.assertIsNotNone(self.app.entry_station_name)
        self.assertIsNotNone(self.app.voice_dropdown)
        self.assertIsNotNone(self.app.lbl_el_credits)
        self.assertIsNotNone(self.app.lbl_suno_credits)
        self.assertIsNotNone(self.app.text_song_styles)
        self.assertIsNotNone(self.app.continue_frame)
        self.assertIsNotNone(self.app.btn_add_to_station)
        self.assertIsNotNone(self.app.btn_repair)
        self.assertIsNotNone(self.app.btn_start_over)

    def test_init_starts_credit_check(self):
        """after(500, check_all_credits) was scheduled."""
        was_called, _, _ = self._find_after_call(500, self.app.check_all_credits)
        self.assertTrue(was_called)

    def test_init_starts_refresh(self):
        """after(800, _refresh_station_status) was scheduled."""
        was_called, _, _ = self._find_after_call(800, self.app._refresh_station_status)
        self.assertTrue(was_called)

    def test_init_continue_frame_hidden(self):
        """continue_frame.pack_forget called at least once."""
        self.app.continue_frame.pack_forget.assert_called()

    def test_init_station_name_bind(self):
        """KeyRelease bind attached to entry_station_name."""
        self.app.entry_station_name.bind.assert_called()

    def test_init_song_styles_populated(self):
        """text_song_styles receives config styles."""
        insert_calls = [str(c) for c in self.app.text_song_styles.insert.call_args_list]
        self.assertTrue(any("synthwave" in c for c in insert_calls))
        self.assertTrue(any("industrial" in c for c in insert_calls))

    # ━━━━━━━━━━━━ toggle_el_key (3 tests) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def test_toggle_el_key_shows(self):
        """Checkbox checked → show='' on both entries."""
        self.app.show_el_key.get = MagicMock(return_value=True)
        self.app.toggle_el_key()
        self.app.entry_el_key.configure.assert_called_with(show="")
        self.app.entry_suno_key.configure.assert_called_with(show="")

    def test_toggle_el_key_hides(self):
        """Checkbox unchecked → show='*' on both entries."""
        self.app.show_el_key.get = MagicMock(return_value=False)
        self.app.toggle_el_key()
        self.app.entry_el_key.configure.assert_called_with(show="*")
        self.app.entry_suno_key.configure.assert_called_with(show="*")

    def test_toggle_el_key_clears_checkbox(self):
        """No crash when show_el_key.get returns True."""
        self.app.show_el_key.get = MagicMock(return_value=True)
        self.app.toggle_el_key()

    # ━━━━━━━━━━━━ log (2 tests) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def test_log_inserts_text(self):
        """Inserts message plus newline."""
        self.app.console.insert.reset_mock()
        self.app.console.configure.reset_mock()
        self.app.log("Hello")
        self.app.console.configure.assert_any_call(state="normal")
        self.app.console.insert.assert_called_with("end", "Hello\n")
        self.app.console.configure.assert_any_call(state="disabled")

    def test_log_ensures_visible(self):
        """Calls see('end')."""
        self.app.console.see.reset_mock()
        self.app.log("test")
        self.app.console.see.assert_called_with("end")

    # ━━━━━━━━━━━━ _station_output_dir (3 tests) ━━━━━━━━━━━━━━━━━━━━━━━━

    def test_station_output_dir_uses_station_name(self):
        """Path contains output/{station_name}."""
        result = self.app._station_output_dir()
        self.assertIn("output", result)
        self.assertIn("TestStation", result)

    def test_station_output_dir_replaces_spaces(self):
        """Spaces in name replaced with underscores."""
        self.app.entry_station_name.get = MagicMock(return_value="My Station")
        result = self.app._station_output_dir()
        self.assertIn("My_Station", result)
        self.assertNotIn("My Station", result)

    def test_station_output_dir_uses_script_dir(self):
        """Based on os.path.dirname of app_gui.__file__."""
        result = self.app._station_output_dir()
        expected_parent = os.path.dirname(os.path.abspath(sys.modules["app_gui"].__file__))
        self.assertTrue(result.startswith(expected_parent))

    # ━━━━━━━━━━━━ _get_voice_id (3 tests) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def test_get_voice_id_from_map(self):
        """Returns voice_id from voice_id_map."""
        self.app.voice_id_map = {"[PREMADE] Charlie (v1...)": "v1"}
        self.app.voice_var.get = MagicMock(return_value="[PREMADE] Charlie (v1...)")
        self.assertEqual(self.app._get_voice_id(), "v1")

    def test_get_voice_id_fallback(self):
        """Returns label verbatim if not in map."""
        self.app.voice_id_map = {}
        self.app.voice_var.get = MagicMock(return_value="some_label")
        self.assertEqual(self.app._get_voice_id(), "some_label")

    def test_get_voice_id_empty_map(self):
        """Returns label when map is empty."""
        self.app.voice_id_map = {}
        self.app.voice_var.get = MagicMock(return_value="[PREMADE] X (abc...)")
        self.assertEqual(self.app._get_voice_id(), "[PREMADE] X (abc...)")

    # ━━━━━━━━━━━━ _apply_credits (11 tests) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def test_apply_credits_voice_data_updates_dropdown(self):
        """Populates voice_dropdown with labels (caller is responsible for sorting)."""
        voice_data = [
            ("[PREMADE] Charlie (v1...)", "v1"),
            ("[GENERATED] Custom (abc...)", "vid2"),
        ]
        self.app.voice_dropdown.configure.reset_mock()
        self.app._apply_credits(voice_data, None, None)
        expected_labels = ["[PREMADE] Charlie (v1...)", "[GENERATED] Custom (abc...)"]
        self.app.voice_dropdown.configure.assert_called_with(values=expected_labels)

    def test_apply_credits_voice_data_finds_current(self):
        """Selects matching voice_id from config."""
        voice_data = [
            ("[PREMADE] Charlie (v1...)", "v1"),
            ("[GENERATED] Custom (xyz...)", "vid2"),
        ]
        self.app.voice_var.set.reset_mock()
        self.app.config["elevenlabs_voice_id"] = "v1"
        self.app._apply_credits(voice_data, None, None)
        self.app.voice_var.set.assert_called_with("[PREMADE] Charlie (v1...)")

    def test_apply_credits_voice_data_fallsback_premade(self):
        """Selects first premade if current_vid not found."""
        voice_data = [
            ("[GENERATED] Custom (xyz...)", "vid2"),
            ("[PREMADE] Charlie (v1...)", "v1"),
        ]
        self.app.voice_var.set.reset_mock()
        self.app.config["elevenlabs_voice_id"] = "nonexistent"
        self.app._apply_credits(voice_data, None, None)
        self.app.voice_var.set.assert_called_with("[PREMADE] Charlie (v1...)")
        self.assertEqual(self.app.config["elevenlabs_voice_id"], "v1")

    def test_apply_credits_el_data_ok(self):
        """Shows remaining/limit with green."""
        self.app._apply_credits(None, (True, 500, 10000), None)
        self.app.lbl_el_credits.configure.assert_called_with(
            text="ElevenLabs: 500/10000 chars",
            text_color="#4CAF50",
        )

    def test_apply_credits_el_data_ok_zero_red(self):
        """Shows remaining/limit with red when 0 remaining."""
        self.app._apply_credits(None, (True, 0, 10000), None)
        self.app.lbl_el_credits.configure.assert_called_with(
            text="ElevenLabs: 0/10000 chars",
            text_color="#f44336",
        )

    def test_apply_credits_el_data_invalid_key(self):
        """Shows 'invalid key' in red."""
        self.app.lbl_el_credits.configure.reset_mock()
        self.app._apply_credits(None, (False, "invalid_key", "invalid"), None)
        self.app.lbl_el_credits.configure.assert_called_with(
            text="ElevenLabs: invalid key",
            text_color="#f44336",
        )

    def test_apply_credits_el_data_error(self):
        """Shows 'unreachable' in gray."""
        self.app.lbl_el_credits.configure.reset_mock()
        self.app._apply_credits(None, (False, 0, "connection error"), None)
        self.app.lbl_el_credits.configure.assert_called_with(
            text="ElevenLabs: unreachable",
            text_color="#888",
        )

    def test_apply_credits_el_data_none(self):
        """Clears label when el_data is None."""
        self.app.lbl_el_credits.configure.reset_mock()
        self.app._apply_credits(None, None, (True, 10, "OK"))
        self.app.lbl_el_credits.configure.assert_called_with(text="")

    def test_apply_credits_sn_data_ok(self):
        """Shows credits count with green."""
        self.app.lbl_suno_credits.configure.reset_mock()
        self.app._apply_credits(None, None, (True, 25, "OK"))
        self.app.lbl_suno_credits.configure.assert_called_with(
            text="Suno: 25 credits",
            text_color="#4CAF50",
        )

    def test_apply_credits_sn_data_invalid(self):
        """Shows 'invalid key' in red."""
        self.app.lbl_suno_credits.configure.reset_mock()
        self.app._apply_credits(None, None, (False, 0, "Invalid API key"))
        self.app.lbl_suno_credits.configure.assert_called_with(
            text="Suno: invalid key",
            text_color="#f44336",
        )

    def test_apply_credits_sn_data_error(self):
        """Shows 'unreachable' in red."""
        self.app.lbl_suno_credits.configure.reset_mock()
        self.app._apply_credits(None, None, (False, 0, "timeout"))
        self.app.lbl_suno_credits.configure.assert_called_with(
            text="Suno: unreachable",
            text_color="#f44336",
        )

    def test_apply_credits_sn_data_none(self):
        """Clears label when sn_data is None."""
        self.app.lbl_suno_credits.configure.reset_mock()
        self.app._apply_credits(None, (True, 10, 100), None)
        self.app.lbl_suno_credits.configure.assert_called_with(text="")

    # ━━━━━━━━━━━━ _sanity_check_station (9 tests) ━━━━━━━━━━━━━━━━━━━━━━

    def test_sanity_no_meta(self):
        """Returns empty list if no meta/tracks."""
        self.assertEqual(self.app._sanity_check_station("/tmp", None), [])
        self.assertEqual(self.app._sanity_check_station("/tmp", {}), [])
        self.assertEqual(self.app._sanity_check_station("/tmp", {"order": []}), [])

    def test_sanity_all_ok(self):
        """Meta files exist, no orphans → empty list."""
        tmp = self._make_temp_dir()
        for f in ["001_Anchorman_Intro.mp3", "002_Suno_Song_1.mp3"]:
            open(os.path.join(tmp, f), "w").close()
        meta = {"order": ["001_Anchorman_Intro.mp3", "002_Suno_Song_1.mp3"]}
        self.assertEqual(self.app._sanity_check_station(tmp, meta), [])

    def test_sanity_missing_files(self):
        """Meta tracks missing from disk → issues."""
        tmp = self._make_temp_dir()
        open(os.path.join(tmp, "001_Anchorman_Intro.mp3"), "w").close()
        meta = {"order": ["001_Anchorman_Intro.mp3", "002_Suno_Song_1.mp3"]}
        issues = self.app._sanity_check_station(tmp, meta)
        self.assertTrue(any("missing" in i for i in issues))

    def test_sanity_orphaned_mp3s(self):
        """Extra MP3s on disk not in meta → issues."""
        tmp = self._make_temp_dir()
        open(os.path.join(tmp, "001_Anchorman_Intro.mp3"), "w").close()
        open(os.path.join(tmp, "orphan.mp3"), "w").close()
        meta = {"order": ["001_Anchorman_Intro.mp3"]}
        issues = self.app._sanity_check_station(tmp, meta)
        self.assertTrue(
            any("orphan" in i.lower() or "not in metadata" in i.lower() for i in issues)
        )

    def test_sanity_no_intro_with_music(self):
        """Has songs but no intro → issues and spin_interludes set."""
        tmp = self._make_temp_dir()
        for f in ["002_Suno_Song_1.mp3", "003_Suno_Song_2.mp3"]:
            open(os.path.join(tmp, f), "w").close()
        meta = {"order": ["002_Suno_Song_1.mp3", "003_Suno_Song_2.mp3"]}
        self.app.spin_interludes.get = MagicMock(return_value="0")
        self.app.spin_interludes.set.reset_mock()
        issues = self.app._sanity_check_station(tmp, meta)
        self.assertTrue(any("intro" in i.lower() for i in issues))
        self.app.spin_interludes.set.assert_called_with("1")

    def test_sanity_no_intro_spin_already_set(self):
        """Does not override spin_interludes if already > 0."""
        tmp = self._make_temp_dir()
        for f in ["002_Suno_Song_1.mp3"]:
            open(os.path.join(tmp, f), "w").close()
        meta = {"order": ["002_Suno_Song_1.mp3"]}
        self.app.spin_interludes.get = MagicMock(return_value="2")
        self.app.spin_interludes.set.reset_mock()
        issues = self.app._sanity_check_station(tmp, meta)
        self.assertTrue(any("intro" in i.lower() for i in issues))
        # Should NOT have been called since current=2 > 0
        # (it may have been called during __init__ with "1", so reset before the test)
        for call_args in self.app.spin_interludes.set.call_args_list:
            self.assertNotEqual(call_args[0][0], "1",
                                "set('1') should not have been called")

    def test_sanity_missing_files_more_than_3(self):
        """Truncates long missing-files lists."""
        tmp = self._make_temp_dir()
        open(os.path.join(tmp, "001_Intro.mp3"), "w").close()
        meta = {"order": ["001_Intro.mp3"] + [f"00{i}_Missing.mp3" for i in range(2, 8)]}
        issues = self.app._sanity_check_station(tmp, meta)
        missing_issues = [i for i in issues if "missing" in i]
        self.assertTrue(len(missing_issues) >= 1)
        self.assertIn("(+", missing_issues[0])

    def test_sanity_orphans_more_than_3(self):
        """Truncates long orphan lists."""
        tmp = self._make_temp_dir()
        meta = {"order": ["001_Intro.mp3"]}
        open(os.path.join(tmp, "001_Intro.mp3"), "w").close()
        for i in range(2, 8):
            open(os.path.join(tmp, f"orphan_{i}.mp3"), "w").close()
        issues = self.app._sanity_check_station(tmp, meta)
        orphan_issues = [i for i in issues if "orphan" in i.lower() or "not in metadata" in i]
        self.assertTrue(len(orphan_issues) >= 1)
        self.assertIn("(+", orphan_issues[0])

    def test_sanity_cover_no_meta(self):
        """cover.jpg exists without metadata.json file → issues."""
        tmp = self._make_temp_dir()
        open(os.path.join(tmp, "cover.jpg"), "w").close()
        open(os.path.join(tmp, "001_Anchorman_Intro.mp3"), "w").close()
        meta = {"order": ["001_Anchorman_Intro.mp3"]}
        issues = self.app._sanity_check_station(tmp, meta)
        self.assertTrue(any("cover" in i.lower() for i in issues))

    # ━━━━━━━━━━━━ _refresh_station_status (5 tests) ━━━━━━━━━━━━━━━━━━━━

    def test_refresh_shows_frame_when_meta_exists(self):
        """continue_frame packed when meta found."""
        tmp = self._make_temp_dir()
        self._set_station_output_dir(tmp)
        with open(os.path.join(tmp, "metadata.json"), "w") as f:
            json.dump({"displayName": "Test", "order": ["001_Intro.mp3"]}, f)
        open(os.path.join(tmp, "001_Intro.mp3"), "w").close()
        from audio_processor import read_radioext_metadata as real_read_meta
        with patch("app_gui.read_radioext_metadata", side_effect=real_read_meta):
            self.app._refresh_station_status()
            self.app.continue_frame.pack.assert_called()

    def test_refresh_hides_frame_when_no_meta(self):
        """continue_frame hidden when no meta."""
        tmp = self._make_temp_dir()
        self._set_station_output_dir(tmp)
        self.app.continue_frame.pack_forget.reset_mock()
        self._mocks["app_gui.read_radioext_metadata"].return_value = None
        self.app._refresh_station_status()
        self.app.continue_frame.pack_forget.assert_called()

    def test_refresh_shows_green_when_ok(self):
        """text_color='#4CAF50' when no issues."""
        tmp = self._make_temp_dir()
        self._set_station_output_dir(tmp)
        with open(os.path.join(tmp, "metadata.json"), "w") as f:
            json.dump({"displayName": "Test", "order": ["001_Intro.mp3"]}, f)
        open(os.path.join(tmp, "001_Intro.mp3"), "w").close()
        from audio_processor import read_radioext_metadata as real_read_meta
        with patch("app_gui.read_radioext_metadata", side_effect=real_read_meta):
            self.app.lbl_station_status.configure.reset_mock()
            self.app._refresh_station_status()
            kwargs = self.app.lbl_station_status.configure.call_args[1]
            self.assertEqual(kwargs.get("text_color"), "#4CAF50")

    def test_refresh_shows_yellow_when_issues(self):
        """text_color='#ffcc00' when issues exist."""
        tmp = self._make_temp_dir()
        self._set_station_output_dir(tmp)
        with open(os.path.join(tmp, "metadata.json"), "w") as f:
            json.dump({"displayName": "Test", "order": ["001_Intro.mp3", "002_Missing.mp3"]}, f)
        open(os.path.join(tmp, "001_Intro.mp3"), "w").close()
        from audio_processor import read_radioext_metadata as real_read_meta
        with patch("app_gui.read_radioext_metadata", side_effect=real_read_meta):
            self.app.lbl_station_status.configure.reset_mock()
            self.app._refresh_station_status()
            kwargs = self.app.lbl_station_status.configure.call_args[1]
            self.assertEqual(kwargs.get("text_color"), "#ffcc00")

    def test_refresh_shows_track_count(self):
        """Text contains 'has N track(s)'."""
        tmp = self._make_temp_dir()
        self._set_station_output_dir(tmp)
        with open(os.path.join(tmp, "metadata.json"), "w") as f:
            json.dump({"displayName": "Test", "order": ["001_Intro.mp3"]}, f)
        open(os.path.join(tmp, "001_Intro.mp3"), "w").close()
        from audio_processor import read_radioext_metadata as real_read_meta
        with patch("app_gui.read_radioext_metadata", side_effect=real_read_meta):
            self.app.lbl_station_status.configure.reset_mock()
            self.app._refresh_station_status()
            text = self.app.lbl_station_status.configure.call_args[1]["text"]
            self.assertIn("1 track", text)

    # ━━━━━━━━━━━━ save_settings (8 tests) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def test_save_settings_stores_values(self):
        """Config updated from entry fields."""
        self.app.save_settings()
        self.assertEqual(self.app.config["elevenlabs_api_key"], "el_test_key")
        self.assertEqual(self.app.config["suno_api_key"], "sn_test_key")
        self.assertEqual(self.app.config["llm_provider"], "LM Studio")
        self.assertEqual(self.app.config["llm_api_url"], "http://localhost:1234/v1")
        self.assertEqual(self.app.config["station_name"], "TestStation")
        self.assertEqual(self.app.config["station_frequency"], "99.7")

    def test_save_settings_voice_id(self):
        """Stores result of _get_voice_id."""
        self.app._get_voice_id = MagicMock(return_value="v1_custom")
        self.app.save_settings()
        self.assertEqual(self.app.config["elevenlabs_voice_id"], "v1_custom")

    def test_save_settings_song_count_int(self):
        """Parses integer song_count."""
        self.app.entry_song_count.get = MagicMock(return_value="5")
        self.app.save_settings()
        self.assertEqual(self.app.config["song_count"], 5)

    def test_save_settings_song_count_min_1(self):
        """max(1, value) applied."""
        self.app.entry_song_count.get = MagicMock(return_value="0")
        self.app.save_settings()
        self.assertEqual(self.app.config["song_count"], 1)

    def test_save_settings_song_count_invalid_fallback(self):
        """ValueError → defaults to 3."""
        self.app.entry_song_count.get = MagicMock(return_value="not_a_number")
        self.app.save_settings()
        self.assertEqual(self.app.config["song_count"], 3)

    def test_save_settings_extracts_styles(self):
        """Parses song_styles from textbox."""
        self.app.text_song_styles.get = MagicMock(return_value="synthwave\nindustrial\n\n")
        self.app.save_settings()
        self.assertEqual(self.app.config["song_styles"], ["synthwave", "industrial"])

    def test_save_settings_calls_save_config(self):
        """save_config called with updated config."""
        self.app.save_settings()
        self._mocks["app_gui.save_config"].assert_called_once_with(self.app.config)

    def test_save_settings_logs(self):
        """Logs save confirmation."""
        self.app.console.insert.reset_mock()
        self.app.save_settings()
        self.assertIn("✅ Settings saved!", str(self.app.console.insert.call_args_list))

    # ━━━━━━━━━━━━ test_elevenlabs (3 tests) ━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def test_elevenlabs_no_key(self):
        """Logs 'No API key' when key empty."""
        self.app.entry_el_key.get = MagicMock(return_value="")
        self.app.console.insert.reset_mock()
        self.app.test_elevenlabs()
        logs = str(self.app.console.insert.call_args_list)
        self.assertIn("No API key entered", logs)

    def test_elevenlabs_ok(self):
        """Logs credits and voices, updates label."""
        self._mocks["app_gui.get_user_info"].return_value = (True, 5000, 10000)
        self._mocks["app_gui.list_voices"].return_value = (True, [
            {"voice_id": "v1", "name": "Charlie", "category": "premade"},
        ])
        self.app.console.insert.reset_mock()
        self.app.lbl_el_credits.configure.reset_mock()
        self.app.test_elevenlabs()
        logs = str(self.app.console.insert.call_args_list)
        self.assertIn("Connected", logs)
        self.app.lbl_el_credits.configure.assert_called_with(
            text="ElevenLabs: 5000/10000 chars",
            text_color="#4CAF50",
        )

    def test_elevenlabs_invalid_key(self):
        """Logs 'invalid key', sets label."""
        self._mocks["app_gui.get_user_info"].return_value = (False, "invalid_key", "Invalid")
        self.app.console.insert.reset_mock()
        self.app.lbl_el_credits.configure.reset_mock()
        self.app.test_elevenlabs()
        logs = str(self.app.console.insert.call_args_list)
        self.assertIn("invalid", logs.lower())
        self.app.lbl_el_credits.configure.assert_called_with(
            text="ElevenLabs: invalid key",
            text_color="#f44336",
        )

    # ━━━━━━━━━━━━ test_suno (3 tests) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def test_suno_no_key(self):
        """Logs 'No Suno API key' when key empty."""
        self.app.entry_suno_key.get = MagicMock(return_value="")
        self.app.console.insert.reset_mock()
        self.app.test_suno()
        logs = str(self.app.console.insert.call_args_list)
        self.assertIn("No Suno API key", logs)

    def test_suno_ok(self):
        """Logs credits, sets label."""
        self._mocks["app_gui.get_suno_credits"].return_value = (True, 30, "OK")
        self.app.console.insert.reset_mock()
        self.app.lbl_suno_credits.configure.reset_mock()
        self.app.test_suno()
        logs = str(self.app.console.insert.call_args_list)
        self.assertIn("30", logs)
        self.app.lbl_suno_credits.configure.assert_called_with(
            text="Suno: 30 credits",
            text_color="#4CAF50",
        )

    def test_suno_error(self):
        """Logs error, sets label."""
        self._mocks["app_gui.get_suno_credits"].return_value = (False, 0, "rate limited")
        self.app.console.insert.reset_mock()
        self.app.lbl_suno_credits.configure.reset_mock()
        self.app.test_suno()
        logs = str(self.app.console.insert.call_args_list)
        self.assertIn("rate limited", logs.lower())
        self.app.lbl_suno_credits.configure.assert_called_with(
            text="Suno: unreachable",
            text_color="#f44336",
        )

    # ━━━━━━━━━━━━ test_llm (3 tests) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def test_llm_connection_ok(self):
        """Logs 'SUCCESS'."""
        mock_resp = MagicMock(status_code=200)
        self.mock_requests_get.return_value = mock_resp
        self.app.console.insert.reset_mock()
        self.app.test_llm()
        logs = str(self.app.console.insert.call_args_list)
        self.assertIn("SUCCESS", logs)

    def test_llm_connection_fail(self):
        """Logs status code."""
        mock_resp = MagicMock(status_code=503)
        self.mock_requests_get.return_value = mock_resp
        self.app.console.insert.reset_mock()
        self.app.test_llm()
        logs = str(self.app.console.insert.call_args_list)
        self.assertIn("503", logs)

    def test_llm_connection_exception(self):
        """Logs 'Could not connect'."""
        self.mock_requests_get.side_effect = Exception("refused")
        self.app.console.insert.reset_mock()
        self.app.test_llm()
        logs = str(self.app.console.insert.call_args_list)
        self.assertIn("Could not connect", logs)

    # ━━━━━━━━━━━━ start_generation (6 tests) ━━━━━━━━━━━━━━━━━━━━━━━━━━

    def test_generation_no_keys_warning(self):
        """Warnings shown for missing keys (shown via dialog, not log)."""
        self.app.entry_el_key.get = MagicMock(return_value="")
        self.app.entry_suno_key.get = MagicMock(return_value="")
        tk_mock.messagebox.askyesno.reset_mock()
        self.app.start_generation()
        tk_mock.messagebox.askyesno.assert_called()
        msg = tk_mock.messagebox.askyesno.call_args[1].get("message", "")
        self.assertIn("No ElevenLabs", msg)
        self.assertIn("manual music", msg.lower())

    def test_generation_proceeds_after_yes(self):
        """Calls pipeline when user says yes (or no warnings shown)."""
        self._mocks["app_gui.run_generation_pipeline"].reset_mock()
        self.app.start_generation()
        self._mocks["app_gui.run_generation_pipeline"].assert_called_once()

    def test_generation_cancelled(self):
        """Does not call pipeline when user says no (low credits trigger warning dialog)."""
        self._mocks["app_gui.get_user_info"].return_value = (True, 50, 10000)
        self._mocks["app_gui.get_suno_credits"].return_value = (True, 1, "OK")
        self._mocks["app_gui.run_generation_pipeline"].reset_mock()
        self.app.start_generation()
        self._mocks["app_gui.run_generation_pipeline"].assert_not_called()

    def test_generation_disables_button(self):
        """Sets button to disabled while generating."""
        tk_mock.messagebox.askyesno.return_value = True
        self.app.btn_generate.configure.reset_mock()
        self.app.start_generation()
        self.app.btn_generate.configure.assert_any_call(
            state="disabled", text="GENERATING..."
        )

    def test_generation_reenables_button(self):
        """Re-enables button after completion."""
        tk_mock.messagebox.askyesno.return_value = True
        self.app.btn_generate.configure.reset_mock()
        self.app.start_generation()
        self.app.btn_generate.configure.assert_any_call(
            state="normal", text="GENERATE RADIO STATION"
        )

    def test_generation_logs_result(self):
        """Logs complete/partial/failed."""
        tk_mock.messagebox.askyesno.return_value = True
        for result, expected_substr in [
            ("complete", "COMPLETE"),
            ("partial", "WITH ISSUES"),
            ("failed", "FAILED"),
        ]:
            with self.subTest(result=result):
                self._mocks["app_gui.run_generation_pipeline"].return_value = result
                self.app.console.insert.reset_mock()
                self.app.start_generation()
                logs = str(self.app.console.insert.call_args_list)
                self.assertIn(
                    expected_substr,
                    logs,
                    f"'{expected_substr}' not logged for result='{result}'",
                )

    # ━━━━━━━━━━━━ start_over (3 tests) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def test_start_over_deletes_files(self):
        """Removes files in output dir."""
        tmp = self._make_temp_dir()
        self._set_station_output_dir(tmp)
        open(os.path.join(tmp, "001_Intro.mp3"), "w").close()
        open(os.path.join(tmp, "metadata.json"), "w").close()
        tk_mock.messagebox.askyesno.return_value = True
        self.app.start_over()
        self.assertFalse(os.path.exists(os.path.join(tmp, "001_Intro.mp3")))
        self.assertFalse(os.path.exists(os.path.join(tmp, "metadata.json")))

    def test_start_over_cancelled(self):
        """Does not delete when user says no."""
        tmp = self._make_temp_dir()
        self._set_station_output_dir(tmp)
        fpath = os.path.join(tmp, "001_Intro.mp3")
        open(fpath, "w").close()
        tk_mock.messagebox.askyesno.return_value = False
        self.app.start_over()
        self.assertTrue(os.path.exists(fpath))

    def test_start_over_refreshes_status(self):
        """Calls _refresh_station_status after deletion."""
        tmp = self._make_temp_dir()
        self._set_station_output_dir(tmp)
        tk_mock.messagebox.askyesno.return_value = True
        original = self.app._refresh_station_status
        self.app._refresh_station_status = MagicMock()
        try:
            self.app.start_over()
            self.app._refresh_station_status.assert_called_once()
        finally:
            self.app._refresh_station_status = original

    # ━━━━━━━━━━━━ repair_station (3 tests) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def test_repair_no_meta(self):
        """Logs 'Nothing to repair' when no metadata."""
        self._mocks["app_gui.read_radioext_metadata"].return_value = None
        self.app.console.insert.reset_mock()
        self.app.repair_station()
        logs = str(self.app.console.insert.call_args_list)
        self.assertIn("Nothing to repair", logs)

    def test_repair_generates_intro_if_missing(self):
        """Calls generate_script and generate_voice when intro missing."""
        tmp = self._make_temp_dir()
        self._set_station_output_dir(tmp)
        with open(os.path.join(tmp, "metadata.json"), "w") as f:
            json.dump({"displayName": "Test", "order": ["002_Suno_Song_1.mp3"]}, f)
        open(os.path.join(tmp, "002_Suno_Song_1.mp3"), "w").close()
        from audio_processor import read_radioext_metadata as real_read_meta
        with patch("app_gui.read_radioext_metadata", side_effect=real_read_meta):
            with patch("llm_client.generate_script",
                       return_value="Good morning Night City!") as mock_script:
                with patch("tts_client.generate_voice",
                           return_value=(True, "ok")) as mock_voice:
                    with patch("audio_processor.apply_radio_effect",
                               return_value=(True, "ok")):
                        with patch("audio_processor.create_radioext_metadata",
                                   return_value=True):
                            self.app.repair_station()
                            mock_script.assert_called_once()
                            mock_voice.assert_called_once()

    def test_repair_rebuilds_metadata(self):
        """Calls create_radioext_metadata after repair."""
        tmp = self._make_temp_dir()
        self._set_station_output_dir(tmp)
        with open(os.path.join(tmp, "metadata.json"), "w") as f:
            json.dump({"displayName": "Test", "order": ["001_Anchorman_Intro.mp3"]}, f)
        open(os.path.join(tmp, "001_Anchorman_Intro.mp3"), "w").close()
        from audio_processor import read_radioext_metadata as real_read_meta
        with patch("app_gui.read_radioext_metadata", side_effect=real_read_meta):
            with patch("llm_client.generate_script", return_value="Hello"):
                with patch("tts_client.generate_voice", return_value=(True, "ok")):
                    with patch("audio_processor.apply_radio_effect",
                               return_value=(True, "ok")):
                        with patch("audio_processor.create_radioext_metadata",
                                   return_value=True) as mock_create:
                            self.app.repair_station()
                            mock_create.assert_called_once()

    # ━━━━━━━━━━━━ start_continuation (6 tests) ━━━━━━━━━━━━━━━━━━━━━━━━

    def test_continuation_no_meta(self):
        """Logs 'No existing tracks'."""
        self._mocks["app_gui.read_radioext_metadata"].return_value = None
        self.app.console.insert.reset_mock()
        self.app.start_continuation()
        logs = str(self.app.console.insert.call_args_list)
        self.assertIn("No existing tracks", logs)

    def test_continuation_zero_interludes_and_songs(self):
        """Logs 'Set at least 1' when both are 0."""
        tmp = self._make_temp_dir()
        self._set_station_output_dir(tmp)
        with open(os.path.join(tmp, "metadata.json"), "w") as f:
            json.dump({"displayName": "Test", "order": ["001_Intro.mp3"]}, f)
        open(os.path.join(tmp, "001_Intro.mp3"), "w").close()
        from audio_processor import read_radioext_metadata as real_read_meta
        self.app.spin_interludes.get = MagicMock(return_value="0")
        self.app.spin_songs.get = MagicMock(return_value="0")
        self.app.console.insert.reset_mock()
        with patch("app_gui.read_radioext_metadata", side_effect=real_read_meta):
            self.app.start_continuation()
            logs = str(self.app.console.insert.call_args_list)
            self.assertIn("Set at least 1", logs)

    def test_continuation_zero_interludes_and_songs_returns_early(self):
        """Returns early when both are 0."""
        tmp = self._make_temp_dir()
        self._set_station_output_dir(tmp)
        with open(os.path.join(tmp, "metadata.json"), "w") as f:
            json.dump({"displayName": "Test", "order": ["001_Intro.mp3"]}, f)
        open(os.path.join(tmp, "001_Intro.mp3"), "w").close()
        from audio_processor import read_radioext_metadata as real_read_meta
        self.app.spin_interludes.get = MagicMock(return_value="0")
        self.app.spin_songs.get = MagicMock(return_value="0")
        with patch("app_gui.read_radioext_metadata", side_effect=real_read_meta):
            self.app.start_continuation()
            self._mocks["app_gui.run_generation_pipeline"].assert_not_called()

    def test_continuation_calls_pipeline(self):
        """Calls run_generation_pipeline with mode='continue'."""
        tmp = self._make_temp_dir()
        self._set_station_output_dir(tmp)
        with open(os.path.join(tmp, "metadata.json"), "w") as f:
            json.dump({"displayName": "Test", "order": ["001_Anchorman_Intro.mp3"]}, f)
        open(os.path.join(tmp, "001_Anchorman_Intro.mp3"), "w").close()
        tk_mock.messagebox.askyesno.return_value = True
        self._mocks["app_gui.run_generation_pipeline"].reset_mock()
        from audio_processor import read_radioext_metadata as real_read_meta
        with patch("app_gui.read_radioext_metadata", side_effect=real_read_meta):
            self.app.start_continuation()
            self._mocks["app_gui.run_generation_pipeline"].assert_called_once()
            kwargs = self._mocks["app_gui.run_generation_pipeline"].call_args[1]
            self.assertEqual(kwargs.get("mode"), "continue")
            self.assertEqual(kwargs.get("new_interludes"), 1)
            self.assertEqual(kwargs.get("new_songs"), 1)
            self.assertEqual(
                kwargs.get("existing_tracks"), ["001_Anchorman_Intro.mp3"]
            )

    def test_continuation_logs_result(self):
        """Logs complete/partial/failed after continuation."""
        tmp = self._make_temp_dir()
        self._set_station_output_dir(tmp)
        with open(os.path.join(tmp, "metadata.json"), "w") as f:
            json.dump({"displayName": "Test", "order": ["001_Intro.mp3"]}, f)
        open(os.path.join(tmp, "001_Intro.mp3"), "w").close()
        tk_mock.messagebox.askyesno.return_value = True
        from audio_processor import read_radioext_metadata as real_read_meta
        for result, expected in [
            ("complete", "ADDED SUCCESSFULLY"),
            ("partial", "WITH ISSUES"),
            ("failed", "FAILED"),
        ]:
            with self.subTest(result=result):
                self._mocks["app_gui.run_generation_pipeline"].return_value = result
                self.app.console.insert.reset_mock()
                with patch("app_gui.read_radioext_metadata", side_effect=real_read_meta):
                    self.app.start_continuation()
                    logs = str(self.app.console.insert.call_args_list)
                    self.assertIn(
                        expected,
                        logs,
                        f"'{expected}' not logged for result='{result}'",
                    )

    # ━━━━━━━━━━━━ check_all_credits (2 tests) ━━━━━━━━━━━━━━━━━━━━━━━━━

    def test_check_all_credits_threaded(self):
        """Launches a background thread."""
        self._thread_target = None
        self.mock_thread_class.reset_mock()
        self._thread_mock.reset_mock()
        self.app.check_all_credits()
        self.assertIsNotNone(
            self._thread_target,
            "threading.Thread should have been called with a target",
        )

    def test_check_all_credits_applies_after(self):
        """Calls _apply_credits via after on main thread."""
        self._mocks["app_gui.list_voices"].return_value = (True, [
            {"voice_id": "v1", "name": "Charlie", "category": "premade"},
        ])
        self._thread_target = None
        original_apply = self.app._apply_credits
        self.app._apply_credits = MagicMock()
        try:
            self.app.check_all_credits()
            self.app._apply_credits.assert_called_once()
            args = self.app._apply_credits.call_args[0]
            voice_data, el_data, sn_data = args
            self.assertIsNotNone(voice_data)
            self.assertIsNotNone(el_data)
            self.assertIsNotNone(sn_data)
        finally:
            self.app._apply_credits = original_apply


# ── Runner ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
