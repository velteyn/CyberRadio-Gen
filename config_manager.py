import json
import os

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "elevenlabs_api_key": "",
    "elevenlabs_voice_id": "IKne3meq5aSn9XLyUdCD",  # Charlie - Deep, Confident, Energetic (ElevenLabs free tier)
    "suno_api_key": "",
    "llm_provider": "LM Studio",  # "LM Studio" or "Ollama"
    "llm_api_url": "http://localhost:1234/v1",
    "station_name": "CyberRadio",
    "station_frequency": "99.7",
    "station_volume": 1.0,
    "host_prompt": "You are a cynical, dynamic, fast-talking street-smart radio host in Night City.",
    "song_count": 3,
    "song_styles": [
        "synth-pop, cyberpop, 102 BPM, female-led vocals, octave-doubled hook, arpeggiated analog synth, detuned polysynth chords, punchy drum machine, gated snare reverb, sidechain compression, sub bass pulse, stereo synth leads, call-and-response chorus, neon noir, rebellious triumph, rising breakdown, spacious bridge, hi-fi gloss",
        "industrial metal, 140 BPM, distorted guitar riffs, aggressive female vocals, heavy kick drums, glitch breaks, cybernetic breakdown, shouted chorus, metallic percussion, digital noise",
        "dark synthwave, 100 BPM, minor key arpeggios, heavy reverb, pulsing analog bass, melodic leads, cinematic pads, dystopian atmosphere, driving drums, haunting vocals",
        "cyberpop, 128 BPM, catchy synth hooks, autotuned vocals, four-on-the-floor, bright leads, sidechain pumping, polished production, energetic, futuristic, neon-soaked",
        "glitch hop, 95 BPM, broken beats, vinyl crackle, deep sub-bass, sampled vocals, lo-fi synths, moody atmosphere, tight drums, dystopian vibe",
        "trip-hop, 85 BPM, slow drums, moody samples, ethereal female vocals, heavy sub-bass, dark atmosphere, cinematic strings, haunting, nocturnal",
        "cyberpunk hip-hop, 90 BPM, 808s, lo-fi synths, spoken word verses, dystopian samples, hard snares, deep bass, streetwise, nocturnal",
        "industrial dance, 130 BPM, driving bassline, looped vocal samples, sidechain pumping, metallic percussion, aggressive, energetic, club-ready"
    ]
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            # Ensure all keys exist
            for key, value in DEFAULT_CONFIG.items():
                if key not in config:
                    config[key] = value
            return config
    except Exception as e:
        print(f"Error loading config: {e}")
        return DEFAULT_CONFIG

def save_config(config_data):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config_data, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False
