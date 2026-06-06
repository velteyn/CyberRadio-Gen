import requests

ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1"

# Fallback static model list — used only if the API model query fails
FALLBACK_MODELS = [
    "eleven_flash_v2_5",
    "eleven_flash_v2",
    "eleven_multilingual_v2",
    "eleven_turbo_v2_5",
]


def get_user_info(api_key):
    """Fetch ElevenLabs account info including remaining character credits."""
    headers = {"xi-api-key": api_key}
    try:
        r = requests.get(f"{ELEVENLABS_API_URL}/user", headers=headers, timeout=10)
        if r.status_code == 401:
            return False, "invalid_key", "API key is invalid or expired."
        r.raise_for_status()
        data = r.json()
        remaining = data.get("subscription", {}).get("character_count", 0)
        limit = data.get("subscription", {}).get("character_limit", 0)
        return True, remaining, limit
    except requests.exceptions.ConnectionError:
        return False, 0, "Could not connect to ElevenLabs."
    except Exception as e:
        return False, 0, str(e)


def list_voices(api_key):
    """Fetch available voices from ElevenLabs for this account."""
    headers = {"xi-api-key": api_key}
    try:
        response = requests.get(f"{ELEVENLABS_API_URL}/voices", headers=headers, timeout=10)
        response.raise_for_status()
        voices = response.json().get("voices", [])
        return True, voices
    except Exception as e:
        return False, f"Could not fetch voices: {str(e)}"


def list_tts_models(api_key):
    """
    Query ElevenLabs for models that support text-to-speech on this account.
    Returns (models_list, warning_or_none).
    Falls back to FALLBACK_MODELS silently; warning message explains why.
    """
    headers = {"xi-api-key": api_key}
    try:
        r = requests.get(f"{ELEVENLABS_API_URL}/models", headers=headers, timeout=10)
        r.raise_for_status()
        all_models = r.json()
        tts = [
            m["model_id"]
            for m in all_models
            if m.get("can_do_text_to_speech", False)
        ]
        if tts:
            return tts, None
        return list(FALLBACK_MODELS), "API returned no TTS models — using fallback list."
    except requests.exceptions.ConnectionError:
        return list(FALLBACK_MODELS), "Could not query ElevenLabs models (offline?) — using fallback list."
    except requests.exceptions.Timeout:
        return list(FALLBACK_MODELS), "ElevenLabs model query timed out — using fallback list."
    except Exception as e:
        return list(FALLBACK_MODELS), f"Failed to query ElevenLabs models ({e}) — using fallback list."


def _voice_category(api_key, voice_id):
    """Look up whether a voice is premade, professional, generated, etc."""
    try:
        ok, voices = list_voices(api_key)
        if ok:
            for v in voices:
                if v.get("voice_id") == voice_id:
                    return v.get("category", "unknown"), v.get("name", voice_id)
    except Exception:
        pass
    return "unknown", voice_id


def _try_generate(api_key, voice_id, text, output_path, model_id):
    """Attempt TTS with a single model. Returns (status, message, response)."""
    url = f"{ELEVENLABS_API_URL}/text-to-speech/{voice_id}"

    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key
    }

    data = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": 0.3,
            "similarity_boost": 0.8
        }
    }

    try:
        response = requests.post(url, json=data, headers=headers, timeout=30)

        # Handle specific HTTP errors
        if response.status_code == 401:
            err = response.json().get("detail", {})
            msg = err.get("message", str(response.json()))
            return "fail", f"ElevenLabs auth error: {msg}", response

        if response.status_code == 404:
            return "skip", f"Voice ID '{voice_id}' not found.", response

        if response.status_code == 429:
            return "skip", "ElevenLabs quota exhausted for this model.", response

        if response.status_code == 402:
            try:
                err = response.json().get("detail", {})
                code = err.get("code", "")
                msg = err.get("message", "no credits")
            except Exception:
                code = ""
                msg = "no credits"

            if code in ("paid_plan_required",):
                cat, vname = _voice_category(api_key, voice_id)
                return "fail", (
                    f"Voice '{vname}' ({cat}) requires a paid ElevenLabs plan.\n"
                    f"  Free API tier only supports PREMADE voices like:\n"
                    f"    Roger, Sarah, Charlie, Alice, Adam, Daniel, Bella, etc.\n"
                    f"  Change the Voice ID in settings to a premade voice."
                ), response

            if "library" in msg.lower():
                return "fail", (
                    f"Library voices cannot be used via the API on the free tier.\n"
                    f"  Use a premade voice instead (e.g. Charlie, Sarah, Roger)."
                ), response

            return "skip", f"Model '{model_id}' not available on your plan ({msg})", response

        response.raise_for_status()

        # Validate we actually got audio back
        content_type = response.headers.get("Content-Type", "")
        if "audio" not in content_type:
            return "skip", f"Expected audio response, got {content_type}", response

        with open(output_path, 'wb') as f:
            f.write(response.content)

        size_kb = len(response.content) // 1024
        return "ok", f"Voice generated ({size_kb} KB) with model '{model_id}'.", response

    except requests.exceptions.ConnectionError:
        return "fail", "Could not connect to ElevenLabs.", None
    except requests.exceptions.Timeout:
        return "fail", "ElevenLabs request timed out.", None
    except Exception as e:
        return "fail", f"ElevenLabs error: {str(e)}", None


def generate_voice(api_key, voice_id, text, output_path):
    """
    Calls ElevenLabs API to generate TTS audio with dynamic model fallback.
    Queries the API for models YOUR account supports, then tries each.
    """
    if not api_key:
        return False, "ElevenLabs API Key is missing."
    if not voice_id:
        return False, "ElevenLabs Voice ID is missing."

    # First check remaining credits
    ok, remaining, limit = get_user_info(api_key)
    if ok:
        if remaining <= 0:
            return False, (
                f"ElevenLabs: 0/{limit} monthly characters remaining. "
                "Your free tier credits are used up this month, or your API key has no quota."
            )
    elif remaining == "invalid_key":
        return False, "ElevenLabs API Key is invalid or expired."

    # Dynamically get models this account can use
    models, models_warn = list_tts_models(api_key)

    last_error = "All available models failed."
    if models_warn:
        last_error = models_warn

    for model_id in models:
        status, msg, _ = _try_generate(api_key, voice_id, text, output_path, model_id)
        if status == "ok":
            if models_warn:
                msg += " " + models_warn
            return True, msg
        if status == "fail":
            last_error = msg
            break  # hard failure — don't fallback further
        if status == "skip" and "not found" in msg.lower():
            last_error = msg  # voice-level error beats model-level warning
        last_error = msg

    return False, last_error
