# CyberRadio-Gen 📻⚡

CyberRadio-Gen is a lightweight, fully automated Python desktop application designed to generate dynamic, immersive custom radio stations for **Cyberpunk 2077**.

Using local LLMs (like LM Studio or Ollama) combined with ElevenLabs TTS and the Suno AI API, the tool automatically writes scripts, synthesizes a cynical dystopian radio host, generates custom dark synthwave music tracks, applies realistic in-car FM radio effects via FFmpeg, and packages the entire station perfectly for the **RadioExt** Cyberpunk 2077 mod.

## Features
- **Modern Cyberpunk UI**: A beautiful dark-mode desktop interface built with CustomTkinter.
- **Local AI Brain**: Interacts directly with your local LM Studio or Ollama instance for limitless, private, and free script and lyric generation.
- **Fully Automated Audio**: Leverages ElevenLabs for human-like anchors and `sunoapi.org` for completely automatic AI music generation.
- **Retro FM Radio Effects**: Automatically processes clean studio audio with High-Pass/Low-Pass filters and Dynamic Range Compression to mimic cheap dystopian car speakers.
- **RadioExt Ready**: Automatically generates the `metadata.json` and outputs sequentially numbered tracks that you can drop straight into your Cyberpunk 2077 game directory.

---

## Prerequisites

1. **Python 3.10+** (Tested on Python 3.14).
2. **FFmpeg**: Must be installed on your Windows system and added to your system PATH to apply the radio EQ effects. If FFmpeg is not found, the tool will gracefully copy the clean audio instead.
3. **LM Studio** or **Ollama** running locally on your machine.
4. **API Keys**:
   - ElevenLabs API Key (Free tier works perfectly)
   - Suno API Key (via sunoapi.org)

---

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/CyberRadio-Gen.git
   cd CyberRadio-Gen
   ```

2. **Install the required Python packages**:
   ```bash
   pip install -r requirements.txt
   ```
   *Note: Ensure you are using `pip` from your chosen Python environment.*

---

## Usage

1. **Start your Local LLM**:
   - Open **LM Studio**, load your favorite model (e.g., Llama 3 or Mistral), and click **Start Server** on the Local Server tab (defaults to `http://localhost:1234/v1`).
   - *Alternatively, ensure Ollama is running in the background.*

2. **Launch the App**:
   ```bash
   python main.py
   ```

3. **Configure the Application**:
   - In the left panel, paste your ElevenLabs and Suno API keys.
   - Click "Test LLM Connection" to ensure the app can talk to your local model.
   - Adjust your Station Name, FM Frequency (e.g., 99.7), and set a prompt for the radio host's personality.
   - Click "Save Settings".

4. **Generate the Station**:
   - Click the **GENERATE RADIO STATION** button.
   - Watch the live log console as the app writes scripts, synthesizes voices, generates music, applies filters, and exports the files.
   - Once complete, click **Open Output Folder**.

5. **Install into Cyberpunk 2077**:
   - Open your Cyberpunk 2077 installation folder.
   - Ensure you have **Cyber Engine Tweaks** and **RadioExt** installed.
   - Copy your new station folder from the generator's `output/` directory into:
     `Cyberpunk 2077\bin\x64\plugins\cyber_engine_tweaks\mods\radioExt\radios\`
   - Launch the game, hop into a Rayfield Caliburn, and tune in!

---

## Manual Music Mode
If you run out of Suno API credits, the application supports a fully free Manual Mode!
Simply click **Open Input Folder** in the app, drop your manually downloaded `.mp3` files from the Suno Web interface into the `/input_music/` folder, leave the Suno API key blank, and click Generate. The app will sequence your manual songs alongside the AI-generated host!

## License
MIT License
