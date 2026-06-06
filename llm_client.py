import requests

# Cache whether each LM Studio URL supports system roles
# so we don't retry the wrong format on every call
_system_role_supported_cache = {}


def get_loaded_model(api_url):
    """
    Queries LM Studio (or Ollama) to find the currently loaded model ID.
    Returns the model ID string, or None on failure.
    """
    try:
        r = requests.get(f"{api_url.rstrip('/')}/models", timeout=5)
        r.raise_for_status()
        models = r.json().get("data", [])
        if models:
            return models[0].get("id", None)
    except Exception:
        pass
    return None


def _call_lmstudio(endpoint, model_id, system_prompt, user_prompt):
    """
    Tries to call the LM Studio chat endpoint, automatically detecting
    whether the loaded model supports a 'system' role.
    Falls back gracefully to merging system+user if not supported.
    Returns (response_text, error_string)
    """
    global _system_role_supported_cache

    def _post(messages):
        payload = {
            "model": model_id,
            "messages": messages,
            "temperature": 0.85,
            "max_tokens": 512
        }
        return requests.post(endpoint, json=payload, timeout=120)

    # Check cache first
    supported = _system_role_supported_cache.get(endpoint)

    # If we already know system role is NOT supported, skip straight to merged
    if supported is False:
        messages = [{"role": "user", "content": f"{system_prompt}\n\n{user_prompt}"}]
        r = _post(messages)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip(), None
        return None, f"LM Studio error: {r.status_code} — {r.text[:200]}"

    # Try with system role first (supported by most models)
    messages_with_system = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt}
    ]
    r = _post(messages_with_system)

    if r.status_code == 200:
        _system_role_supported_cache[endpoint] = True
        return r.json()["choices"][0]["message"]["content"].strip(), None

    # If 400, check if it's a role/template error -> fallback to merged format
    if r.status_code == 400:
        err_text = r.text.lower()
        if any(kw in err_text for kw in ["system", "role", "template", "jinja", "only user"]):
            _system_role_supported_cache[endpoint] = False
            messages_merged = [{"role": "user", "content": f"{system_prompt}\n\n{user_prompt}"}]
            r2 = _post(messages_merged)
            if r2.status_code == 200:
                return r2.json()["choices"][0]["message"]["content"].strip(), None
            return None, f"LM Studio error after fallback: {r2.status_code} — {r2.text[:200]}"

    return None, f"LM Studio error {r.status_code}: {r.text[:200]}"


def generate_script(api_url, provider, system_prompt, user_prompt):
    """
    Generates text using the local LLM (LM Studio or Ollama).
    Fully model-agnostic:
      - Auto-detects the loaded model name from /v1/models
      - Automatically handles models that don't support the 'system' role
        by falling back to a merged user message format
    """
    if provider == "LM Studio":
        endpoint = f"{api_url.rstrip('/')}/chat/completions"

        # Auto-detect loaded model
        model_id = get_loaded_model(api_url)
        if not model_id:
            return (
                "Error communicating with LM Studio: No model detected. "
                "Make sure a model is loaded and the Local Server is running in LM Studio."
            )

        text, error = _call_lmstudio(endpoint, model_id, system_prompt, user_prompt)

        if text:
            return text
        return f"Error communicating with LM Studio: {error}"

    elif provider == "Ollama":
        # Normalize base URL (strip trailing /v1 if user copied from LM Studio)
        base_url = api_url.replace("/v1", "").rstrip("/")
        endpoint = f"{base_url}/api/generate"

        # Auto-detect the first available Ollama model
        model_id = "mistral"
        try:
            r = requests.get(f"{base_url}/api/tags", timeout=5)
            models = r.json().get("models", [])
            if models:
                model_id = models[0]["name"]
        except Exception:
            pass

        payload = {
            "model": model_id,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
            "options": {"temperature": 0.85}
        }

        try:
            r = requests.post(endpoint, json=payload, timeout=120)
            r.raise_for_status()
            return r.json()["response"].strip()
        except requests.exceptions.ConnectionError:
            return "Error communicating with Ollama: Connection refused. Is Ollama running?"
        except requests.exceptions.Timeout:
            return "Error communicating with Ollama: Request timed out."
        except Exception as e:
            return f"Error communicating with Ollama: {str(e)}"

    return "Error: Unknown LLM provider selected. Choose 'LM Studio' or 'Ollama'."
