import requests
import time
import os

SUNO_BASE_URL = "https://api.sunoapi.org"
DEFAULT_MODEL = "V4"

def get_suno_credits(api_key):
    """Check remaining credits on sunoapi.org account."""
    if not api_key:
        return False, 0, "No API key."
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        r = requests.get(f"{SUNO_BASE_URL}/api/v1/generate/credit", headers=headers, timeout=10)
        if r.status_code == 401:
            return False, 0, "Invalid API key."
        r.raise_for_status()
        data = r.json()
        if data.get("code") == 200:
            credits = data.get("data", 0)
            return True, credits, "OK"
        return False, 0, data.get("msg", "Unknown error")
    except requests.exceptions.ConnectionError:
        return False, 0, "Could not connect to Suno API."
    except Exception as e:
        return False, 0, str(e)

def generate_suno_song(api_key, lyrics, style, title, output_path, log_callback=None):
    """
    Calls api.sunoapi.org to generate a song. Returns (success, image_url, message).
    image_url can be used as the radio station cover art.
    """

    def log(msg):
        if log_callback:
            log_callback(msg)

    if not api_key:
        return False, None, "Suno API Key is missing. Please enter it in settings."

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "prompt": lyrics,
        "tags": style,
        "title": title,
        "instrumental": False,
        "model": DEFAULT_MODEL,
        "customMode": False,            # Suno generates its own lyrics from prompt + tags
        "callBackUrl": "http://localhost:8888"
    }

    log(f"  → Sending generation request to Suno (model: {DEFAULT_MODEL})...")

    try:
        response = requests.post(
            f"{SUNO_BASE_URL}/api/v1/generate",
            json=payload,
            headers=headers,
            timeout=30
        )

        if response.status_code == 401:
            return False, None, (
                "Suno API Key is invalid. Please verify your key at sunoapi.org.\n"
                "  Go to https://sunoapi.org/dashboard and create a new API key."
            )
        if response.status_code == 402:
            try:
                detail = response.json()
                return False, None, (
                    "Suno: Payment required — you may have run out of credits.\n"
                    f"  API response: {detail.get('msg', detail.get('message', str(detail)[:200]))}"
                )
            except Exception:
                return False, None, "Suno: Payment required. Check your credit balance at sunoapi.org."
        if response.status_code == 429:
            return False, None, (
                "Suno API rate limit reached. Please wait a few minutes before generating again.\n"
                "  Free/limited accounts have strict rate limits — consider upgrading."
            )

        # Non-200 response with error body → surface it
        if response.status_code != 200:
            try:
                err = response.json()
                api_msg = err.get("msg") or err.get("message") or str(err)[:200]
            except Exception:
                api_msg = response.text[:200]
            return False, None, f"Suno API error (HTTP {response.status_code}): {api_msg}"

        data = response.json()

        api_code = data.get("code", 200)
        api_msg  = data.get("msg", "")
        if api_code != 200:
            return False, None, f"Suno API rejected request: {api_msg}"

        # Response data is a dict with a taskId — we must poll
        task_data = data.get("data", {})
        task_id = task_data.get("taskId") if isinstance(task_data, dict) else None

        if not task_id:
            return False, None, "Suno did not return a task ID. Cannot retrieve track."

        log(f"  → Generation started (task: {task_id}). Waiting for completion...")

        # Poll until done (up to ~3 minutes)
        audio_url = None
        image_url = None

        for attempt in range(24):  # 24 × 8s = ~3 min
            time.sleep(8)
            poll_url = f"{SUNO_BASE_URL}/api/v1/generate/record-info?taskId={task_id}"
            poll_r = requests.get(poll_url, headers=headers, timeout=15)

            if poll_r.status_code != 200:
                try:
                    err_body = poll_r.text[:150]
                except Exception:
                    err_body = "(could not read body)"
                log(f"  → Poll attempt {attempt + 1}/24 — HTTP {poll_r.status_code}: {err_body}")
                continue

            poll_data = poll_r.json().get("data", {})
            status    = poll_data.get("status", "PENDING")
            log(f"  → Poll attempt {attempt + 1}/24 — status: {status}")

            if status in ("SUCCESS", "success", "completed"):
                clips = poll_data.get("response", {}).get("sunoData", [])
                if clips:
                    # audioUrl is the correct camelCase field name
                    audio_url = clips[0].get("audioUrl")
                    image_url = clips[0].get("imageUrl")  # bonus: cover art for the station
                break

            elif status in ("FAILED", "failed", "error"):
                err = poll_data.get("errorMessage", "Unknown error")
                return False, None, f"Suno generation failed: {err}"

        if not audio_url:
            return False, None, (
                "Timed out waiting for Suno (3 min / 24 polls).\n"
                "  The generation may still be in progress on sunoapi.org.\n"
                "  Possible causes: heavy server load, or your account has limited queue priority.\n"
                "  Wait a moment and check your balance, or try again later."
            )

        # Download the MP3
        log(f"  → Downloading generated MP3...")
        audio_response = requests.get(audio_url, timeout=60)
        if audio_response.status_code != 200:
            return False, None, f"Failed to download audio (HTTP {audio_response.status_code})."

        with open(output_path, 'wb') as f:
            f.write(audio_response.content)

        size_kb = len(audio_response.content) // 1024
        return True, image_url, f"Music downloaded successfully ({size_kb} KB)."

    except requests.exceptions.ConnectionError:
        return False, None, "Could not connect to Suno API. Check your internet connection."
    except requests.exceptions.Timeout:
        return False, None, "Suno API request timed out. The server may be busy, please try again."
    except Exception as e:
        return False, None, f"Suno unexpected error: {str(e)}"
