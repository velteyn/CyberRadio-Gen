"""
Comprehensive unit tests for tts_client, suno_client, and llm_client modules.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock


# =============================================================================
# tts_client tests
# =============================================================================

class TestTTSGetUserInfo(unittest.TestCase):
    """Tests for tts_client.get_user_info."""

    def setUp(self):
        self.api_key = "test_key"

    @patch("tts_client.requests.get")
    def test_get_user_info_success(self, mock_get):
        """Status 200 with subscription data returns (True, count, limit)."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "subscription": {
                "character_count": 500,
                "character_limit": 10000
            }
        }
        from tts_client import get_user_info
        ok, remaining, limit = get_user_info(self.api_key)
        self.assertTrue(ok)
        self.assertEqual(remaining, 500)
        self.assertEqual(limit, 10000)

    @patch("tts_client.requests.get")
    def test_get_user_info_401(self, mock_get):
        """Status 401 returns (False, 'invalid_key', ...)."""
        mock_get.return_value.status_code = 401
        from tts_client import get_user_info
        ok, remaining, limit = get_user_info(self.api_key)
        self.assertFalse(ok)
        self.assertEqual(remaining, "invalid_key")
        self.assertIn("invalid", limit.lower())

    @patch("tts_client.requests.get")
    def test_get_user_info_connection_error(self, mock_get):
        """ConnectionError returns (False, 0, 'Could not connect to ElevenLabs.')."""
        mock_get.side_effect = __import__("requests").exceptions.ConnectionError()
        from tts_client import get_user_info
        ok, remaining, limit = get_user_info(self.api_key)
        self.assertFalse(ok)
        self.assertEqual(remaining, 0)
        self.assertIn("Could not connect", limit)

    @patch("tts_client.requests.get")
    def test_get_user_info_generic_exception(self, mock_get):
        """Generic Exception returns (False, 0, str(e))."""
        mock_get.side_effect = ValueError("something broke")
        from tts_client import get_user_info
        ok, remaining, limit = get_user_info(self.api_key)
        self.assertFalse(ok)
        self.assertEqual(remaining, 0)
        self.assertEqual(limit, "something broke")

    @patch("tts_client.requests.get")
    def test_get_user_info_missing_subscription_keys(self, mock_get):
        """Missing subscription keys defaults to 0."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"subscription": {}}
        from tts_client import get_user_info
        ok, remaining, limit = get_user_info(self.api_key)
        self.assertTrue(ok)
        self.assertEqual(remaining, 0)
        self.assertEqual(limit, 0)


class TestTTSListVoices(unittest.TestCase):
    """Tests for tts_client.list_voices."""

    def setUp(self):
        self.api_key = "test_key"

    @patch("tts_client.requests.get")
    def test_list_voices_success(self, mock_get):
        """Status 200 with voices list returns (True, voices)."""
        voices_data = [
            {"voice_id": "id1", "name": "Voice1", "category": "premade"},
            {"voice_id": "id2", "name": "Voice2", "category": "generated"}
        ]
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"voices": voices_data}
        from tts_client import list_voices
        ok, voices = list_voices(self.api_key)
        self.assertTrue(ok)
        self.assertEqual(voices, voices_data)

    @patch("tts_client.requests.get")
    def test_list_voices_empty(self, mock_get):
        """Status 200 with empty voices list returns (True, [])."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"voices": []}
        from tts_client import list_voices
        ok, voices = list_voices(self.api_key)
        self.assertTrue(ok)
        self.assertEqual(voices, [])

    @patch("tts_client.requests.get")
    def test_list_voices_exception(self, mock_get):
        """Exception returns (False, error_message)."""
        mock_get.side_effect = ConnectionError("network down")
        from tts_client import list_voices
        ok, msg = list_voices(self.api_key)
        self.assertFalse(ok)
        self.assertIn("Could not fetch voices", msg)


class TestTTSListTTSModels(unittest.TestCase):
    """Tests for tts_client.list_tts_models."""

    def setUp(self):
        self.api_key = "test_key"

    @patch("tts_client.requests.get")
    def test_list_tts_models_success(self, mock_get):
        """Success with TTS models returns (models, None)."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [
            {"model_id": "model_a", "can_do_text_to_speech": True},
            {"model_id": "model_b", "can_do_text_to_speech": False},
            {"model_id": "model_c", "can_do_text_to_speech": True},
        ]
        from tts_client import list_tts_models
        models, warn = list_tts_models(self.api_key)
        self.assertEqual(models, ["model_a", "model_c"])
        self.assertIsNone(warn)

    @patch("tts_client.requests.get")
    def test_list_tts_models_empty_tts_list(self, mock_get):
        """Success but empty TTS list returns fallback with warning."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [
            {"model_id": "m1", "can_do_text_to_speech": False}
        ]
        from tts_client import list_tts_models, FALLBACK_MODELS
        models, warn = list_tts_models(self.api_key)
        self.assertEqual(models, list(FALLBACK_MODELS))
        self.assertIsNotNone(warn)
        self.assertIn("fallback", warn.lower())

    @patch("tts_client.requests.get")
    def test_list_tts_models_connection_error(self, mock_get):
        """ConnectionError returns fallback with warning."""
        mock_get.side_effect = __import__("requests").exceptions.ConnectionError()
        from tts_client import list_tts_models, FALLBACK_MODELS
        models, warn = list_tts_models(self.api_key)
        self.assertEqual(models, list(FALLBACK_MODELS))
        self.assertIn("offline", warn.lower())

    @patch("tts_client.requests.get")
    def test_list_tts_models_timeout(self, mock_get):
        """Timeout returns fallback with warning."""
        mock_get.side_effect = __import__("requests").exceptions.Timeout()
        from tts_client import list_tts_models, FALLBACK_MODELS
        models, warn = list_tts_models(self.api_key)
        self.assertEqual(models, list(FALLBACK_MODELS))
        self.assertIn("timed out", warn.lower())

    @patch("tts_client.requests.get")
    def test_list_tts_models_generic_exception(self, mock_get):
        """Generic exception returns fallback with warning."""
        mock_get.side_effect = RuntimeError("weird error")
        from tts_client import list_tts_models, FALLBACK_MODELS
        models, warn = list_tts_models(self.api_key)
        self.assertEqual(models, list(FALLBACK_MODELS))
        self.assertIn("Failed", warn)


class TestTTSVoiceCategory(unittest.TestCase):
    """Tests for tts_client._voice_category."""

    def setUp(self):
        self.api_key = "test_key"

    @patch("tts_client.list_voices")
    def test_voice_category_found(self, mock_list_voices):
        """Voice found in list returns (category, name)."""
        mock_list_voices.return_value = (True, [
            {"voice_id": "vid1", "category": "premade", "name": "Charlie"},
            {"voice_id": "vid2", "category": "generated", "name": "Custom"}
        ])
        from tts_client import _voice_category
        cat, name = _voice_category(self.api_key, "vid1")
        self.assertEqual(cat, "premade")
        self.assertEqual(name, "Charlie")

    @patch("tts_client.list_voices")
    def test_voice_category_not_found(self, mock_list_voices):
        """Voice not found returns ('unknown', voice_id)."""
        mock_list_voices.return_value = (True, [
            {"voice_id": "other", "category": "premade", "name": "Other"}
        ])
        from tts_client import _voice_category
        cat, name = _voice_category(self.api_key, "missing_id")
        self.assertEqual(cat, "unknown")
        self.assertEqual(name, "missing_id")

    @patch("tts_client.list_voices")
    def test_voice_category_list_voices_fails(self, mock_list_voices):
        """list_voices failing returns ('unknown', voice_id)."""
        mock_list_voices.return_value = (False, "error")
        from tts_client import _voice_category
        cat, name = _voice_category(self.api_key, "some_id")
        self.assertEqual(cat, "unknown")
        self.assertEqual(name, "some_id")

    @patch("tts_client.list_voices")
    def test_voice_category_list_voices_raises(self, mock_list_voices):
        """list_voices raising exception returns ('unknown', voice_id)."""
        mock_list_voices.side_effect = RuntimeError("boom")
        from tts_client import _voice_category
        cat, name = _voice_category(self.api_key, "some_id")
        self.assertEqual(cat, "unknown")
        self.assertEqual(name, "some_id")


class TestTTSTryGenerate(unittest.TestCase):
    """Tests for tts_client._try_generate."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.api_key = "test_key"
        self.voice_id = "test_voice"
        self.text = "Hello Night City!"
        self.output_path = os.path.join(self.tmp, "output.mp3")
        self.model_id = "test_model"

    def tearDown(self):
        shutil.rmtree(self.tmp)

    @patch("tts_client.requests.post")
    def test_try_generate_success(self, mock_post):
        """Success (200 with audio/mpeg) writes file and returns 'ok'."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.headers = {"Content-Type": "audio/mpeg"}
        mock_post.return_value.content = b"fake_audio_data"
        from tts_client import _try_generate
        status, msg, resp = _try_generate(
            self.api_key, self.voice_id, self.text, self.output_path, self.model_id
        )
        self.assertEqual(status, "ok")
        self.assertIn("Voice generated", msg)
        self.assertIn(self.model_id, msg)
        self.assertTrue(os.path.exists(self.output_path))
        with open(self.output_path, "rb") as f:
            self.assertEqual(f.read(), b"fake_audio_data")

    @patch("tts_client.requests.post")
    def test_try_generate_401_auth(self, mock_post):
        """401 auth error returns 'fail'."""
        mock_post.return_value.status_code = 401
        mock_post.return_value.json.return_value = {
            "detail": {"message": "Invalid API key"}
        }
        from tts_client import _try_generate
        status, msg, resp = _try_generate(
            self.api_key, self.voice_id, self.text, self.output_path, self.model_id
        )
        self.assertEqual(status, "fail")
        self.assertIn("auth error", msg.lower())

    @patch("tts_client.requests.post")
    def test_try_generate_404_voice_not_found(self, mock_post):
        """404 voice not found returns 'skip'."""
        mock_post.return_value.status_code = 404
        from tts_client import _try_generate
        status, msg, resp = _try_generate(
            self.api_key, self.voice_id, self.text, self.output_path, self.model_id
        )
        self.assertEqual(status, "skip")
        self.assertIn("not found", msg.lower())

    @patch("tts_client.requests.post")
    def test_try_generate_429_quota_exhausted(self, mock_post):
        """429 quota exhausted returns 'skip'."""
        mock_post.return_value.status_code = 429
        from tts_client import _try_generate
        status, msg, resp = _try_generate(
            self.api_key, self.voice_id, self.text, self.output_path, self.model_id
        )
        self.assertEqual(status, "skip")
        self.assertIn("quota exhausted", msg.lower())

    @patch("tts_client.requests.post")
    @patch("tts_client._voice_category", return_value=("premade", "Charlie"))
    def test_try_generate_402_paid_plan_required(self, mock_cat, mock_post):
        """402 paid_plan_required returns 'fail' with voice category info."""
        mock_post.return_value.status_code = 402
        mock_post.return_value.json.return_value = {
            "detail": {"code": "paid_plan_required", "message": "upgrade"}
        }
        from tts_client import _try_generate
        status, msg, resp = _try_generate(
            self.api_key, self.voice_id, self.text, self.output_path, self.model_id
        )
        self.assertEqual(status, "fail")
        self.assertIn("requires a paid", msg.lower())

    @patch("tts_client.requests.post")
    def test_try_generate_402_library_voice(self, mock_post):
        """402 with library message returns 'fail' with library message."""
        mock_post.return_value.status_code = 402
        mock_post.return_value.json.return_value = {
            "detail": {"code": "", "message": "This library voice cannot be used on the free plan"}
        }
        from tts_client import _try_generate
        status, msg, resp = _try_generate(
            self.api_key, self.voice_id, self.text, self.output_path, self.model_id
        )
        self.assertEqual(status, "fail")
        self.assertIn("library", msg.lower())

    @patch("tts_client.requests.post")
    def test_try_generate_402_generic_code(self, mock_post):
        """402 with generic code returns 'skip' with model not available."""
        mock_post.return_value.status_code = 402
        mock_post.return_value.json.return_value = {
            "detail": {"code": "other_error", "message": "some other issue"}
        }
        from tts_client import _try_generate
        status, msg, resp = _try_generate(
            self.api_key, self.voice_id, self.text, self.output_path, self.model_id
        )
        self.assertEqual(status, "skip")
        self.assertIn("not available", msg.lower())

    @patch("tts_client.requests.post")
    def test_try_generate_connection_error(self, mock_post):
        """ConnectionError returns 'fail'."""
        mock_post.side_effect = __import__("requests").exceptions.ConnectionError()
        from tts_client import _try_generate
        status, msg, resp = _try_generate(
            self.api_key, self.voice_id, self.text, self.output_path, self.model_id
        )
        self.assertEqual(status, "fail")
        self.assertIn("Could not connect", msg)

    @patch("tts_client.requests.post")
    def test_try_generate_timeout(self, mock_post):
        """Timeout returns 'fail'."""
        mock_post.side_effect = __import__("requests").exceptions.Timeout()
        from tts_client import _try_generate
        status, msg, resp = _try_generate(
            self.api_key, self.voice_id, self.text, self.output_path, self.model_id
        )
        self.assertEqual(status, "fail")
        self.assertIn("timed out", msg.lower())

    @patch("tts_client.requests.post")
    def test_try_generate_non_audio_content_type(self, mock_post):
        """Non-audio Content-Type returns 'skip'."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.headers = {"Content-Type": "application/json"}
        mock_post.return_value.content = b"{}"
        from tts_client import _try_generate
        status, msg, resp = _try_generate(
            self.api_key, self.voice_id, self.text, self.output_path, self.model_id
        )
        self.assertEqual(status, "skip")
        self.assertIn("Expected audio", msg)

    @patch("tts_client.requests.post")
    def test_try_generate_generic_exception(self, mock_post):
        """Generic exception returns 'fail'."""
        mock_post.side_effect = RuntimeError("unexpected crash")
        from tts_client import _try_generate
        status, msg, resp = _try_generate(
            self.api_key, self.voice_id, self.text, self.output_path, self.model_id
        )
        self.assertEqual(status, "fail")
        self.assertIn("unexpected crash", msg.lower())

    @patch("tts_client.requests.post")
    def test_try_generate_402_json_decode_error(self, mock_post):
        """402 with non-JSON response body returns 'skip'."""
        mock_post.return_value.status_code = 402
        mock_post.return_value.json.side_effect = ValueError("bad json")
        from tts_client import _try_generate
        status, msg, resp = _try_generate(
            self.api_key, self.voice_id, self.text, self.output_path, self.model_id
        )
        self.assertEqual(status, "skip")


class TestTTSGenerateVoice(unittest.TestCase):
    """Tests for tts_client.generate_voice."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.output_path = os.path.join(self.tmp, "voice.mp3")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_generate_voice_missing_api_key(self):
        """Missing API key returns (False, 'missing')."""
        from tts_client import generate_voice
        ok, msg = generate_voice("", "voice_id", "text", self.output_path)
        self.assertFalse(ok)
        self.assertIn("missing", msg.lower())

    def test_generate_voice_missing_voice_id(self):
        """Missing voice ID returns (False, 'missing')."""
        from tts_client import generate_voice
        ok, msg = generate_voice("key", "", "text", self.output_path)
        self.assertFalse(ok)
        self.assertIn("missing", msg.lower())

    @patch("tts_client.get_user_info", return_value=(True, 0, 10000))
    def test_generate_voice_zero_credits(self, mock_info):
        """0 credits from get_user_info returns (False, '0/limit')."""
        from tts_client import generate_voice
        ok, msg = generate_voice("key", "voice", "text", self.output_path)
        self.assertFalse(ok)
        self.assertIn("0/10000", msg)

    @patch("tts_client.get_user_info", return_value=(False, "invalid_key", "invalid"))
    def test_generate_voice_invalid_key(self, mock_info):
        """Invalid key returns (False, 'invalid')."""
        from tts_client import generate_voice
        ok, msg = generate_voice("bad_key", "voice", "text", self.output_path)
        self.assertFalse(ok)
        self.assertIn("invalid", msg.lower())

    @patch("tts_client.get_user_info", return_value=(True, 5000, 10000))
    @patch("tts_client.list_tts_models",
           return_value=(["model_a", "model_b"], None))
    @patch("tts_client._try_generate",
           return_value=("ok", "Voice generated (50 KB) with model_a.", None))
    def test_generate_voice_success_first_model(self, mock_try, mock_models, mock_info):
        """Success with first model returns (True, ...)."""
        from tts_client import generate_voice
        ok, msg = generate_voice("key", "voice", "text", self.output_path)
        self.assertTrue(ok)
        self.assertIn("model_a", msg)
        mock_try.assert_called_once()

    @patch("tts_client.get_user_info", return_value=(True, 5000, 10000))
    @patch("tts_client.list_tts_models",
           return_value=(["model_a", "model_b"], None))
    @patch("tts_client._try_generate",
           side_effect=[
               ("skip", "Model not available", None),
               ("ok", "Voice generated with model_b.", None),
           ])
    def test_generate_voice_model_fallback(self, mock_try, mock_models, mock_info):
        """First model skips, second succeeds — returns (True, ...)."""
        from tts_client import generate_voice
        ok, msg = generate_voice("key", "voice", "text", self.output_path)
        self.assertTrue(ok)
        self.assertIn("model_b", msg)
        self.assertEqual(mock_try.call_count, 2)

    @patch("tts_client.get_user_info", return_value=(True, 5000, 10000))
    @patch("tts_client.list_tts_models",
           return_value=(["model_a", "model_b"], None))
    @patch("tts_client._try_generate",
           side_effect=[
               ("skip", "Model 'model_a' not available on your plan", None),
               ("skip", "Model 'model_b' not available on your plan", None),
           ])
    def test_generate_voice_all_models_skip(self, mock_try, mock_models, mock_info):
        """All models skip returns (False, last_error)."""
        from tts_client import generate_voice
        ok, msg = generate_voice("key", "voice", "text", self.output_path)
        self.assertFalse(ok)
        self.assertIn("not available", msg)

    @patch("tts_client.get_user_info", return_value=(True, 5000, 10000))
    @patch("tts_client.list_tts_models",
           return_value=(["model_a"], "API returned no TTS models — using fallback list."))
    @patch("tts_client._try_generate",
           return_value=("ok", "Voice generated (50 KB) with model_a.", None))
    def test_generate_voice_with_warning(self, mock_try, mock_models, mock_info):
        """Success includes models warning in message."""
        from tts_client import generate_voice
        ok, msg = generate_voice("key", "voice", "text", self.output_path)
        self.assertTrue(ok)
        self.assertIn("fallback", msg)

    @patch("tts_client.get_user_info", return_value=(True, 5000, 10000))
    @patch("tts_client.list_tts_models",
           return_value=(["model_a"], None))
    @patch("tts_client._try_generate",
           return_value=("fail", "ElevenLabs auth error: bad key", None))
    def test_generate_voice_fail_breaks(self, mock_try, mock_models, mock_info):
        """A 'fail' status breaks the loop immediately."""
        from tts_client import generate_voice
        ok, msg = generate_voice("key", "voice", "text", self.output_path)
        self.assertFalse(ok)
        self.assertIn("auth error", msg)
        mock_try.assert_called_once()

    @patch("tts_client.get_user_info", return_value=(True, 5000, 10000))
    @patch("tts_client.list_tts_models",
           return_value=(["model_a", "model_b"], None))
    @patch("tts_client._try_generate",
           side_effect=[
               ("skip", "Voice ID 'bad_voice' not found.", None),
               ("ok", "Voice generated with model_b.", None),
           ])
    def test_generate_voice_skip_not_found_then_succeeds(self, mock_try, mock_models, mock_info):
        """Skip with 'not found' message sets last_error but loop continues."""
        from tts_client import generate_voice
        ok, msg = generate_voice("key", "bad_voice", "text", self.output_path)
        self.assertTrue(ok)
        self.assertIn("model_b", msg)


# =============================================================================
# suno_client tests
# =============================================================================

class TestSunoGetCredits(unittest.TestCase):
    """Tests for suno_client.get_suno_credits."""

    def setUp(self):
        self.api_key = "test_key"

    @patch("suno_client.requests.get")
    def test_get_suno_credits_success(self, mock_get):
        """Success with credits data returns (True, credits, 'OK')."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"code": 200, "data": 50, "msg": "OK"}
        from suno_client import get_suno_credits
        ok, credits, msg = get_suno_credits(self.api_key)
        self.assertTrue(ok)
        self.assertEqual(credits, 50)
        self.assertEqual(msg, "OK")

    @patch("suno_client.requests.get")
    def test_get_suno_credits_success_no_code(self, mock_get):
        """Missing code key in response returns error."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"data": 30}
        from suno_client import get_suno_credits
        ok, credits, msg = get_suno_credits(self.api_key)
        self.assertFalse(ok)
        self.assertEqual(credits, 0)
        self.assertEqual(msg, "Unknown error")

    @patch("suno_client.requests.get")
    def test_get_suno_credits_401(self, mock_get):
        """401 auth error returns (False, 0, 'Invalid API key.')."""
        mock_get.return_value.status_code = 401
        from suno_client import get_suno_credits
        ok, credits, msg = get_suno_credits(self.api_key)
        self.assertFalse(ok)
        self.assertEqual(credits, 0)
        self.assertIn("Invalid", msg)

    @patch("suno_client.requests.get")
    def test_get_suno_credits_non_200_code(self, mock_get):
        """Non-200 response code returns error message."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"code": 400, "msg": "Bad request"}
        from suno_client import get_suno_credits
        ok, credits, msg = get_suno_credits(self.api_key)
        self.assertFalse(ok)
        self.assertEqual(credits, 0)
        self.assertEqual(msg, "Bad request")

    @patch("suno_client.requests.get")
    def test_get_suno_credits_connection_error(self, mock_get):
        """ConnectionError returns (False, 0, 'Could not connect to Suno API.')."""
        mock_get.side_effect = __import__("requests").exceptions.ConnectionError()
        from suno_client import get_suno_credits
        ok, credits, msg = get_suno_credits(self.api_key)
        self.assertFalse(ok)
        self.assertEqual(credits, 0)
        self.assertIn("Could not connect", msg)

    @patch("suno_client.requests.get")
    def test_get_suno_credits_no_api_key(self, mock_get):
        """No API key returns (False, 0, 'No API key.') without making request."""
        from suno_client import get_suno_credits
        ok, credits, msg = get_suno_credits("")
        self.assertFalse(ok)
        self.assertEqual(credits, 0)
        self.assertEqual(msg, "No API key.")
        mock_get.assert_not_called()

    @patch("suno_client.requests.get")
    def test_get_suno_credits_generic_exception(self, mock_get):
        """Generic exception returns (False, 0, str(e))."""
        mock_get.side_effect = RuntimeError("boom")
        from suno_client import get_suno_credits
        ok, credits, msg = get_suno_credits(self.api_key)
        self.assertFalse(ok)
        self.assertEqual(credits, 0)
        self.assertEqual(msg, "boom")


class TestSunoGenerateSong(unittest.TestCase):
    """Tests for suno_client.generate_suno_song."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.api_key = "test_key"
        self.lyrics = "Night City streets"
        self.style = "dark synthwave"
        self.title = "Cyber Track"
        self.output_path = os.path.join(self.tmp, "song.mp3")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_generate_suno_song_missing_api_key(self):
        """Missing API key returns (False, None, error_message)."""
        from suno_client import generate_suno_song
        ok, img, msg = generate_suno_song("", self.lyrics, self.style,
                                          self.title, self.output_path)
        self.assertFalse(ok)
        self.assertIsNone(img)
        self.assertIn("missing", msg.lower())

    @patch("suno_client.requests.post")
    def test_generate_suno_song_401(self, mock_post):
        """401 auth error returns specific auth error message."""
        mock_post.return_value.status_code = 401
        from suno_client import generate_suno_song
        ok, img, msg = generate_suno_song(self.api_key, self.lyrics, self.style,
                                          self.title, self.output_path)
        self.assertFalse(ok)
        self.assertIsNone(img)
        self.assertIn("invalid", msg.lower())

    @patch("suno_client.requests.post")
    def test_generate_suno_song_402(self, mock_post):
        """402 payment required returns payment error."""
        mock_post.return_value.status_code = 402
        mock_post.return_value.json.return_value = {"msg": "Insufficient credits"}
        from suno_client import generate_suno_song
        ok, img, msg = generate_suno_song(self.api_key, self.lyrics, self.style,
                                          self.title, self.output_path)
        self.assertFalse(ok)
        self.assertIn("Payment required", msg)

    @patch("suno_client.requests.post")
    def test_generate_suno_song_402_bad_json(self, mock_post):
        """402 with non-decodable JSON returns generic payment error."""
        mock_post.return_value.status_code = 402
        mock_post.return_value.json.side_effect = ValueError("bad json")
        from suno_client import generate_suno_song
        ok, img, msg = generate_suno_song(self.api_key, self.lyrics, self.style,
                                          self.title, self.output_path)
        self.assertFalse(ok)
        self.assertIn("Payment required", msg)

    @patch("suno_client.requests.post")
    def test_generate_suno_song_429(self, mock_post):
        """429 rate limit returns rate limit error."""
        mock_post.return_value.status_code = 429
        from suno_client import generate_suno_song
        ok, img, msg = generate_suno_song(self.api_key, self.lyrics, self.style,
                                          self.title, self.output_path)
        self.assertFalse(ok)
        self.assertIn("rate limit", msg.lower())

    @patch("suno_client.requests.post")
    def test_generate_suno_song_non_200_with_json_body(self, mock_post):
        """Non-200 status with JSON error body returns error message."""
        mock_post.return_value.status_code = 500
        mock_post.return_value.json.return_value = {"msg": "Internal server error"}
        from suno_client import generate_suno_song
        ok, img, msg = generate_suno_song(self.api_key, self.lyrics, self.style,
                                          self.title, self.output_path)
        self.assertFalse(ok)
        self.assertIn("Internal server error", msg)

    @patch("suno_client.requests.post")
    def test_generate_suno_song_non_200_with_text_body(self, mock_post):
        """Non-200 status with non-JSON body returns text body."""
        mock_post.return_value.status_code = 502
        mock_post.return_value.json.side_effect = ValueError("bad json")
        mock_post.return_value.text = "Bad Gateway"
        from suno_client import generate_suno_song
        ok, img, msg = generate_suno_song(self.api_key, self.lyrics, self.style,
                                          self.title, self.output_path)
        self.assertFalse(ok)
        self.assertIn("Bad Gateway", msg)

    @patch("suno_client.requests.post")
    def test_generate_suno_song_no_task_id(self, mock_post):
        """No task ID in response returns error."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"code": 200, "data": {}}
        from suno_client import generate_suno_song
        ok, img, msg = generate_suno_song(self.api_key, self.lyrics, self.style,
                                          self.title, self.output_path)
        self.assertFalse(ok)
        self.assertIn("task id", msg.lower())

    @patch("suno_client.time.sleep", return_value=None)
    @patch("suno_client.requests.post")
    @patch("suno_client.requests.get")
    def test_generate_suno_song_poll_success(self, mock_get, mock_post, mock_sleep):
        """Polling: success path with audio_url found."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "code": 200,
            "data": {"taskId": "task_123"}
        }

        poll_response = MagicMock()
        poll_response.status_code = 200
        poll_response.json.return_value = {
            "data": {
                "status": "SUCCESS",
                "response": {
                    "sunoData": [
                        {
                            "audioUrl": "https://example.com/song.mp3",
                            "imageUrl": "https://example.com/cover.jpg"
                        }
                    ]
                }
            }
        }
        download_response = MagicMock()
        download_response.status_code = 200
        download_response.content = b"audio_data"

        mock_get.side_effect = [poll_response, download_response]

        from suno_client import generate_suno_song
        ok, img, msg = generate_suno_song(self.api_key, self.lyrics, self.style,
                                          self.title, self.output_path)
        self.assertTrue(ok)
        self.assertEqual(img, "https://example.com/cover.jpg")
        self.assertIn("downloaded", msg.lower())
        self.assertTrue(os.path.exists(self.output_path))
        with open(self.output_path, "rb") as f:
            self.assertEqual(f.read(), b"audio_data")

    @patch("suno_client.time.sleep", return_value=None)
    @patch("suno_client.requests.post")
    @patch("suno_client.requests.get")
    def test_generate_suno_song_poll_failed(self, mock_get, mock_post, mock_sleep):
        """Polling: FAILED status returns error."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "code": 200,
            "data": {"taskId": "task_456"}
        }

        poll_response = MagicMock()
        poll_response.status_code = 200
        poll_response.json.return_value = {
            "data": {
                "status": "FAILED",
                "errorMessage": "Model generation error"
            }
        }
        mock_get.return_value = poll_response

        from suno_client import generate_suno_song
        ok, img, msg = generate_suno_song(self.api_key, self.lyrics, self.style,
                                          self.title, self.output_path)
        self.assertFalse(ok)
        self.assertIn("failed", msg.lower())
        self.assertIn("Model generation error", msg)

    @patch("suno_client.time.sleep", return_value=None)
    @patch("suno_client.requests.post")
    @patch("suno_client.requests.get")
    def test_generate_suno_song_poll_timeout(self, mock_get, mock_post, mock_sleep):
        """Polling: all 24 attempts exhausted returns timeout error."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "code": 200,
            "data": {"taskId": "task_789"}
        }

        def always_pending(*args, **kwargs):
            r = MagicMock()
            r.status_code = 200
            r.json.return_value = {
                "data": {"status": "PENDING"}
            }
            return r

        mock_get.side_effect = always_pending

        from suno_client import generate_suno_song
        ok, img, msg = generate_suno_song(self.api_key, self.lyrics, self.style,
                                          self.title, self.output_path)
        self.assertFalse(ok)
        self.assertIn("Timed out", msg)

    @patch("suno_client.time.sleep", return_value=None)
    @patch("suno_client.requests.post")
    @patch("suno_client.requests.get")
    def test_generate_suno_song_poll_http_error_retries(self, mock_get, mock_post, mock_sleep):
        """Non-200 poll response is skipped and retried."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "code": 200,
            "data": {"taskId": "task_999"}
        }

        bad_poll = MagicMock()
        bad_poll.status_code = 500
        bad_poll.text = "Server Error"

        good_poll = MagicMock()
        good_poll.status_code = 200
        good_poll.json.return_value = {
            "data": {
                "status": "SUCCESS",
                "response": {
                    "sunoData": [
                        {"audioUrl": "https://example.com/song.mp3"}
                    ]
                }
            }
        }

        download = MagicMock()
        download.status_code = 200
        download.content = b"data"

        mock_get.side_effect = [bad_poll, good_poll, download]

        from suno_client import generate_suno_song
        ok, img, msg = generate_suno_song(self.api_key, self.lyrics, self.style,
                                          self.title, self.output_path)
        self.assertTrue(ok)

    @patch("suno_client.requests.post")
    @patch("suno_client.requests.get")
    def test_generate_suno_song_download_failure(self, mock_get, mock_post):
        """Download failure (audio URL returns non-200) returns error."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "code": 200,
            "data": {"taskId": "task_dl"}
        }

        poll_response = MagicMock()
        poll_response.status_code = 200
        poll_response.json.return_value = {
            "data": {
                "status": "SUCCESS",
                "response": {
                    "sunoData": [
                        {"audioUrl": "https://example.com/song.mp3"}
                    ]
                }
            }
        }

        download_response = MagicMock()
        download_response.status_code = 404

        mock_get.side_effect = [poll_response, download_response]

        from suno_client import generate_suno_song
        ok, img, msg = generate_suno_song(self.api_key, self.lyrics, self.style,
                                          self.title, self.output_path)
        self.assertFalse(ok)
        self.assertIn("Failed to download", msg)

    @patch("suno_client.requests.post")
    def test_generate_suno_song_connection_error(self, mock_post):
        """ConnectionError during request returns error."""
        mock_post.side_effect = __import__("requests").exceptions.ConnectionError()
        from suno_client import generate_suno_song
        ok, img, msg = generate_suno_song(self.api_key, self.lyrics, self.style,
                                          self.title, self.output_path)
        self.assertFalse(ok)
        self.assertIn("Could not connect", msg)

    @patch("suno_client.requests.post")
    def test_generate_suno_song_timeout(self, mock_post):
        """Timeout during request returns error."""
        mock_post.side_effect = __import__("requests").exceptions.Timeout()
        from suno_client import generate_suno_song
        ok, img, msg = generate_suno_song(self.api_key, self.lyrics, self.style,
                                          self.title, self.output_path)
        self.assertFalse(ok)
        self.assertIn("timed out", msg.lower())

    @patch("suno_client.requests.post")
    def test_generate_suno_song_generic_exception(self, mock_post):
        """Generic exception returns error."""
        mock_post.side_effect = RuntimeError("unexpected error")
        from suno_client import generate_suno_song
        ok, img, msg = generate_suno_song(self.api_key, self.lyrics, self.style,
                                          self.title, self.output_path)
        self.assertFalse(ok)
        self.assertIn("unexpected error", msg)

    @patch("suno_client.time.sleep", return_value=None)
    @patch("suno_client.requests.post")
    @patch("suno_client.requests.get")
    def test_generate_suno_song_multiple_clips_picks_first(self, mock_get, mock_post, mock_sleep):
        """Multiple clips returned, picks first audioUrl."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "code": 200,
            "data": {"taskId": "task_multi"}
        }

        poll_response = MagicMock()
        poll_response.status_code = 200
        poll_response.json.return_value = {
            "data": {
                "status": "SUCCESS",
                "response": {
                    "sunoData": [
                        {"audioUrl": "https://example.com/first.mp3", "imageUrl": "img1"},
                        {"audioUrl": "https://example.com/second.mp3", "imageUrl": "img2"},
                    ]
                }
            }
        }

        download_response = MagicMock()
        download_response.status_code = 200
        download_response.content = b"first_audio"

        mock_get.side_effect = [poll_response, download_response]

        from suno_client import generate_suno_song
        ok, img, msg = generate_suno_song(self.api_key, self.lyrics, self.style,
                                          self.title, self.output_path)
        self.assertTrue(ok)
        self.assertEqual(img, "img1")
        self.assertTrue(os.path.exists(self.output_path))
        with open(self.output_path, "rb") as f:
            self.assertEqual(f.read(), b"first_audio")


# =============================================================================
# llm_client tests
# =============================================================================

class TestLLMGetLoadedModel(unittest.TestCase):
    """Tests for llm_client.get_loaded_model."""

    @patch("llm_client.requests.get")
    def test_get_loaded_model_success(self, mock_get):
        """Success with model ID returns the model ID string."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "data": [{"id": "gpt-3.5-turbo"}]
        }
        from llm_client import get_loaded_model
        model = get_loaded_model("http://localhost:1234/v1")
        self.assertEqual(model, "gpt-3.5-turbo")

    @patch("llm_client.requests.get")
    def test_get_loaded_model_empty_list(self, mock_get):
        """Empty models list returns None."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"data": []}
        from llm_client import get_loaded_model
        model = get_loaded_model("http://localhost:1234/v1")
        self.assertIsNone(model)

    @patch("llm_client.requests.get")
    def test_get_loaded_model_no_id_field(self, mock_get):
        """Model entry without 'id' field returns None."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "data": [{"model": "llama"}]
        }
        from llm_client import get_loaded_model
        model = get_loaded_model("http://localhost:1234/v1")
        self.assertIsNone(model)

    @patch("llm_client.requests.get")
    def test_get_loaded_model_exception(self, mock_get):
        """Exception returns None."""
        mock_get.side_effect = ConnectionError("refused")
        from llm_client import get_loaded_model
        model = get_loaded_model("http://localhost:1234/v1")
        self.assertIsNone(model)

    @patch("llm_client.requests.get")
    def test_get_loaded_model_non_200(self, mock_get):
        """Non-200 status returns None."""
        mock_get.return_value.status_code = 500
        import requests as req
        mock_get.return_value.raise_for_status.side_effect = req.exceptions.HTTPError(
            "500 Error"
        )
        from llm_client import get_loaded_model
        model = get_loaded_model("http://localhost:1234/v1")
        self.assertIsNone(model)


class TestLLMCallLMStudio(unittest.TestCase):
    """Tests for llm_client._call_lmstudio."""

    def setUp(self):
        self.endpoint = "http://localhost:1234/v1/chat/completions"
        self.model_id = "test-model"
        self.system_prompt = "You are a radio host."
        self.user_prompt = "Write an intro."
        # Clear any cached system-role state from other tests
        import llm_client
        llm_client._system_role_supported_cache.clear()

    def tearDown(self):
        import llm_client
        llm_client._system_role_supported_cache.clear()

    @patch("llm_client.requests.post")
    def test_call_lmstudio_system_role_supported(self, mock_post):
        """System role supported (200 response) returns text."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "choices": [{"message": {"content": "Good morning Night City!"}}]
        }
        from llm_client import _call_lmstudio
        text, err = _call_lmstudio(
            self.endpoint, self.model_id, self.system_prompt, self.user_prompt
        )
        self.assertEqual(text, "Good morning Night City!")
        self.assertIsNone(err)

    @patch("llm_client.requests.post")
    def test_call_lmstudio_system_not_supported_fallback_succeeds(self, mock_post):
        """400 with role-related error, fallback succeeds."""
        first_response = MagicMock()
        first_response.status_code = 400
        first_response.text = '{"error": "system role not supported"}'

        second_response = MagicMock()
        second_response.status_code = 200
        second_response.json.return_value = {
            "choices": [{"message": {"content": "Fallback intro text"}}]
        }

        mock_post.side_effect = [first_response, second_response]

        from llm_client import _call_lmstudio
        text, err = _call_lmstudio(
            self.endpoint, self.model_id, self.system_prompt, self.user_prompt
        )
        self.assertEqual(text, "Fallback intro text")
        self.assertIsNone(err)
        self.assertEqual(mock_post.call_count, 2)

    @patch("llm_client.requests.post")
    def test_call_lmstudio_system_not_supported_fallback_fails(self, mock_post):
        """400 with role-related error, fallback also fails."""
        first_response = MagicMock()
        first_response.status_code = 400
        first_response.text = '{"error": "system role not supported"}'

        second_response = MagicMock()
        second_response.status_code = 500
        second_response.text = "Internal error"

        mock_post.side_effect = [first_response, second_response]

        from llm_client import _call_lmstudio
        text, err = _call_lmstudio(
            self.endpoint, self.model_id, self.system_prompt, self.user_prompt
        )
        self.assertIsNone(text)
        self.assertIsNotNone(err)
        self.assertIn("fallback", err.lower())

    @patch("llm_client.requests.post")
    def test_call_lmstudio_400_non_role_error(self, mock_post):
        """400 error NOT related to roles returns error without fallback."""
        mock_post.return_value.status_code = 400
        mock_post.return_value.text = '{"error": "invalid parameters"}'
        from llm_client import _call_lmstudio
        text, err = _call_lmstudio(
            self.endpoint, self.model_id, self.system_prompt, self.user_prompt
        )
        self.assertIsNone(text)
        self.assertIsNotNone(err)
        self.assertNotIn("fallback", err.lower())

    @patch("llm_client.requests.post")
    def test_call_lmstudio_cached_no_system(self, mock_post):
        """Cached False skips system role, uses merged format directly."""
        import llm_client
        llm_client._system_role_supported_cache[self.endpoint] = False
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "choices": [{"message": {"content": "Merged prompt output"}}]
        }
        text, err = llm_client._call_lmstudio(
            self.endpoint, self.model_id, self.system_prompt, self.user_prompt
        )
        self.assertEqual(text, "Merged prompt output")
        self.assertIsNone(err)
        # Verify the payload used merged format (single user role)
        call_args = mock_post.call_args[1]
        messages = call_args["json"]["messages"]
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["role"], "user")
        del llm_client._system_role_supported_cache[self.endpoint]

    @patch("llm_client.requests.post")
    def test_call_lmstudio_non_400_error(self, mock_post):
        """Non-400 non-200 status code returns error."""
        mock_post.return_value.status_code = 503
        mock_post.return_value.text = "Service Unavailable"
        from llm_client import _call_lmstudio
        text, err = _call_lmstudio(
            self.endpoint, self.model_id, self.system_prompt, self.user_prompt
        )
        self.assertIsNone(text)
        self.assertIn("503", err)


class TestLLMGenerateScript(unittest.TestCase):
    """Tests for llm_client.generate_script."""

    def setUp(self):
        self.api_url = "http://localhost:1234/v1"
        self.system_prompt = "You are a radio host."
        self.user_prompt = "Write an intro."

    @patch("llm_client.get_loaded_model", return_value="test-model")
    @patch("llm_client._call_lmstudio",
           return_value=("Good morning Night City!", None))
    def test_generate_script_lmstudio_success(self, mock_call, mock_model):
        """LM Studio: success path returns generated text."""
        from llm_client import generate_script
        result = generate_script(self.api_url, "LM Studio",
                                 self.system_prompt, self.user_prompt)
        self.assertEqual(result, "Good morning Night City!")

    @patch("llm_client.get_loaded_model", return_value=None)
    def test_generate_script_lmstudio_no_model(self, mock_model):
        """LM Studio: get_loaded_model returns None → error message."""
        from llm_client import generate_script
        result = generate_script(self.api_url, "LM Studio",
                                 self.system_prompt, self.user_prompt)
        self.assertIn("No model detected", result)

    @patch("llm_client.get_loaded_model", return_value="test-model")
    @patch("llm_client._call_lmstudio",
           return_value=(None, "LM Studio error: 500 — internal error"))
    def test_generate_script_lmstudio_call_error(self, mock_call, mock_model):
        """LM Studio: _call_lmstudio returns error → prefixed error."""
        from llm_client import generate_script
        result = generate_script(self.api_url, "LM Studio",
                                 self.system_prompt, self.user_prompt)
        self.assertIn("Error communicating", result)
        self.assertIn("500", result)

    @patch("llm_client.requests.post")
    @patch("llm_client.requests.get")
    def test_generate_script_ollama_success(self, mock_get, mock_post):
        """Ollama: success path returns generated text."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "models": [{"name": "mistral:latest"}]
        }
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"response": "Ollama intro text"}
        from llm_client import generate_script
        result = generate_script("http://localhost:11434", "Ollama",
                                 self.system_prompt, self.user_prompt)
        self.assertEqual(result, "Ollama intro text")

    @patch("llm_client.requests.post")
    def test_generate_script_ollama_connection_error(self, mock_post):
        """Ollama: ConnectionError returns specific error message."""
        mock_post.side_effect = __import__("requests").exceptions.ConnectionError()
        from llm_client import generate_script
        result = generate_script("http://localhost:11434", "Ollama",
                                 self.system_prompt, self.user_prompt)
        self.assertIn("Connection refused", result)

    @patch("llm_client.requests.post")
    def test_generate_script_ollama_timeout(self, mock_post):
        """Ollama: Timeout returns specific error message."""
        mock_post.side_effect = __import__("requests").exceptions.Timeout()
        from llm_client import generate_script
        result = generate_script("http://localhost:11434", "Ollama",
                                 self.system_prompt, self.user_prompt)
        self.assertIn("timed out", result.lower())

    @patch("llm_client.requests.post")
    def test_generate_script_ollama_generic_exception(self, mock_post):
        """Ollama: generic exception returns error message."""
        mock_post.side_effect = RuntimeError("unexpected failure")
        from llm_client import generate_script
        result = generate_script("http://localhost:11434", "Ollama",
                                 self.system_prompt, self.user_prompt)
        self.assertIn("unexpected failure", result)

    def test_generate_script_unknown_provider(self):
        """Unknown provider returns error message."""
        from llm_client import generate_script
        result = generate_script(self.api_url, "Claude",
                                 self.system_prompt, self.user_prompt)
        self.assertIn("Unknown", result)

    @patch("llm_client.requests.get")
    def test_generate_script_ollama_tags_fails_uses_default(self, mock_get,):
        """Ollama: tags endpoint fails, uses default model name."""
        mock_get.side_effect = ConnectionError("refused")

        mock_post = MagicMock()
        mock_post.status_code = 200
        mock_post.json.return_value = {"response": "Default model worked"}

        with patch("llm_client.requests.post", return_value=mock_post):
            from llm_client import generate_script
            result = generate_script("http://localhost:11434", "Ollama",
                                     self.system_prompt, self.user_prompt)
            self.assertEqual(result, "Default model worked")

    @patch("llm_client.requests.get")
    @patch("llm_client.requests.post")
    def test_generate_script_ollama_normalizes_url(self, mock_post, mock_get):
        """Ollama: strips trailing /v1 from URL."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "models": [{"name": "llama3"}]
        }
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"response": "ok"}
        from llm_client import generate_script
        result = generate_script("http://localhost:11434/v1", "Ollama",
                                 self.system_prompt, self.user_prompt)
        # Verify the tags call used the normalized URL (no /v1)
        called_url = mock_get.call_args[0][0]
        self.assertNotIn("/v1", called_url)
        self.assertIn("/api/tags", called_url)


# =============================================================================
# Runner
# =============================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
