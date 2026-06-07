import customtkinter as ctk
import os
import shutil
import threading
from config_manager import load_config, save_config, ICON_OPTIONS
from pipeline import run_generation_pipeline
from tts_client import get_user_info, list_voices
from suno_client import get_suno_credits
from audio_processor import read_radioext_metadata
import requests

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class CyberRadioApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("CyberRadio-Gen: Cyberpunk 2077 Radio Generator")
        self.geometry("900x750")
        
        self.config = load_config()

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # --- LEFT PANEL: Settings ---
        self.left_panel = ctk.CTkFrame(self, width=300, corner_radius=0)
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        ctk.CTkLabel(self.left_panel, text="CyberRadio-Gen", font=ctk.CTkFont(size=20, weight="bold"), text_color="#00f0ff").pack(pady=(20, 10))
        
        # ElevenLabs Settings
        ctk.CTkLabel(self.left_panel, text="ElevenLabs API Key").pack(anchor="w", padx=20)
        self.entry_el_key = ctk.CTkEntry(self.left_panel, show="*", width=250)
        self.entry_el_key.insert(0, self.config["elevenlabs_api_key"])
        self.entry_el_key.pack(pady=5, padx=20)
        
        self.show_el_key = ctk.CTkCheckBox(self.left_panel, text="Show Key", command=self.toggle_el_key)
        self.show_el_key.pack(anchor="w", padx=20, pady=(0, 10))
        
        ctk.CTkLabel(self.left_panel, text="ElevenLabs Voice").pack(anchor="w", padx=20)
        self.voice_id_map = {}
        self.voice_var = ctk.StringVar(value="(loading...)")
        self.voice_dropdown = ctk.CTkOptionMenu(self.left_panel, variable=self.voice_var, values=["(loading...)"], width=250, dynamic_resizing=False)
        self.voice_dropdown.pack(pady=5, padx=20)

        self.btn_test_eleven = ctk.CTkButton(self.left_panel, text="Test ElevenLabs & Check Credits", command=self.test_elevenlabs, fg_color="#333", hover_color="#555")
        self.btn_test_eleven.pack(pady=(0, 10), padx=20)

        # ElevenLabs credit label
        self.lbl_el_credits = ctk.CTkLabel(self.left_panel, text="", font=ctk.CTkFont(size=11), text_color="#888")
        self.lbl_el_credits.pack(anchor="w", padx=20, pady=(0, 10))

        # Suno API Settings
        ctk.CTkLabel(self.left_panel, text="Suno API Key (sunoapi.org)").pack(anchor="w", padx=20, pady=(10, 0))
        self.entry_suno_key = ctk.CTkEntry(self.left_panel, show="*", width=250)
        self.entry_suno_key.insert(0, self.config["suno_api_key"])
        self.entry_suno_key.pack(pady=5, padx=20)
        
        self.btn_test_suno = ctk.CTkButton(self.left_panel, text="Check Suno Credits", command=self.test_suno, fg_color="#333", hover_color="#555")
        self.btn_test_suno.pack(pady=(5, 2), padx=20)
        # Suno credit label
        self.lbl_suno_credits = ctk.CTkLabel(self.left_panel, text="", font=ctk.CTkFont(size=11), text_color="#888")
        self.lbl_suno_credits.pack(anchor="w", padx=20, pady=(0, 10))

        # LLM Settings
        ctk.CTkLabel(self.left_panel, text="LLM Provider").pack(anchor="w", padx=20, pady=(10, 0))
        self.llm_option = ctk.CTkOptionMenu(self.left_panel, values=["LM Studio", "Ollama"], width=250)
        self.llm_option.set(self.config["llm_provider"])
        self.llm_option.pack(pady=5, padx=20)
        
        ctk.CTkLabel(self.left_panel, text="LLM API URL").pack(anchor="w", padx=20)
        self.entry_llm_url = ctk.CTkEntry(self.left_panel, width=250)
        self.entry_llm_url.insert(0, self.config["llm_api_url"])
        self.entry_llm_url.pack(pady=5, padx=20)
        
        self.btn_test_llm = ctk.CTkButton(self.left_panel, text="Test LLM Connection", command=self.test_llm, fg_color="#333", hover_color="#555")
        self.btn_test_llm.pack(pady=10, padx=20)
        
        self.btn_save = ctk.CTkButton(self.left_panel, text="Save Settings", command=self.save_settings, fg_color="#1f538d")
        self.btn_save.pack(pady=20, padx=20)

        # Check credits + load voices on startup
        self.after(500, self.check_all_credits)
        
        # --- RIGHT PANEL: Station & Instructions ---
        self.right_panel = ctk.CTkFrame(self)
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)
        
        # Instructions
        instruction_text = """Welcome to CyberRadio-Gen!
1. Start LM Studio server.
2. Enter your ElevenLabs & Suno API keys on the left.
3. Configure your station below.
4. Click Generate. The app will auto-create your radio station!"""
        self.lbl_instructions = ctk.CTkLabel(self.right_panel, text=instruction_text, justify="left", font=ctk.CTkFont(size=14))
        self.lbl_instructions.pack(pady=20, padx=20, anchor="w")
        
        # Station Settings
        self.station_frame = ctk.CTkFrame(self.right_panel)
        self.station_frame.pack(fill="x", padx=20, pady=10)
        
        self.station_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(self.station_frame, text="Station Name:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.entry_station_name = ctk.CTkEntry(self.station_frame, width=180)
        self.entry_station_name.insert(0, self.config["station_name"])
        self.entry_station_name.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(self.station_frame, text="Frequency:").grid(row=0, column=2, padx=10, pady=10, sticky="w")
        self.entry_station_freq = ctk.CTkEntry(self.station_frame, width=70)
        self.entry_station_freq.insert(0, self.config["station_frequency"])
        self.entry_station_freq.grid(row=0, column=3, padx=(0, 5), pady=10, sticky="w")

        ctk.CTkLabel(self.station_frame, text="Songs:").grid(row=0, column=4, padx=(0, 5), pady=10, sticky="w")
        self.entry_song_count = ctk.CTkEntry(self.station_frame, width=40)
        self.entry_song_count.insert(0, str(self.config.get("song_count", 3)))
        self.entry_song_count.grid(row=0, column=4, padx=(45, 10), pady=10, sticky="w")

        ctk.CTkLabel(self.station_frame, text="Song Styles\n(one per line):").grid(row=1, column=0, padx=10, pady=(10, 0), sticky="nw")
        self.text_song_styles = ctk.CTkTextbox(self.station_frame, height=110)
        self.text_song_styles.grid(row=1, column=1, columnspan=4, padx=10, pady=(10, 0), sticky="ew")
        styles = self.config.get("song_styles", [])
        for s in styles:
            self.text_song_styles.insert("end", s + "\n")

        ctk.CTkLabel(self.station_frame, text="Station Icon:").grid(row=2, column=0, padx=10, pady=(10, 10), sticky="w")
        self.icon_var = ctk.StringVar()
        icon_labels = [name for name, _ in ICON_OPTIONS]
        self.icon_dropdown = ctk.CTkOptionMenu(self.station_frame, variable=self.icon_var, values=icon_labels, width=180, dynamic_resizing=False)
        self.icon_dropdown.grid(row=2, column=1, columnspan=3, padx=10, pady=(10, 10), sticky="w")
        current_icon = self.config.get("station_icon", "UIIcon.RadioElectronic")
        for name, val in ICON_OPTIONS:
            if val == current_icon:
                self.icon_var.set(name)
                break
        else:
            self.icon_var.set(icon_labels[0])

        # ── Continue Frame (hidden if station doesn't exist) ─────────────────
        self.continue_frame = ctk.CTkFrame(self.right_panel, fg_color="#1a1a2e")
        self.continue_frame.pack(fill="x", padx=20, pady=(5, 0))
        self.continue_frame.pack_forget()  # hidden by default

        self.lbl_station_status = ctk.CTkLabel(self.continue_frame, text="", font=ctk.CTkFont(size=13), justify="left")
        self.lbl_station_status.pack(anchor="w", padx=15, pady=(10, 5))

        add_row = ctk.CTkFrame(self.continue_frame, fg_color="transparent")
        add_row.pack(fill="x", padx=15, pady=(0, 5))

        ctk.CTkLabel(add_row, text="Add:").pack(side="left")
        ctk.CTkLabel(add_row, text="Anchor interludes", font=ctk.CTkFont(size=11)).pack(side="left", padx=(10, 4))
        self.spin_interludes = ctk.CTkOptionMenu(add_row, values=["0", "1", "2", "3", "4", "5"], width=50)
        self.spin_interludes.set("1")
        self.spin_interludes.pack(side="left", padx=(0, 15))

        ctk.CTkLabel(add_row, text="Songs", font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self.spin_songs = ctk.CTkOptionMenu(add_row, values=["0", "1", "2", "3", "4", "5"], width=50)
        self.spin_songs.set("1")
        self.spin_songs.pack(side="left")

        btn_row = ctk.CTkFrame(self.continue_frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=15, pady=(5, 10))

        self.btn_add_to_station = ctk.CTkButton(btn_row, text="ADD TO STATION", font=ctk.CTkFont(size=14, weight="bold"),
                                                  fg_color="#fcee0a", text_color="#000", hover_color="#c4b908",
                                                  command=self.start_continuation)
        self.btn_add_to_station.pack(side="left", padx=(0, 10))

        self.btn_update_meta = ctk.CTkButton(btn_row, text="Update Metadata", font=ctk.CTkFont(size=12),
                                              fg_color="#1f538d", text_color="#fff", hover_color="#143570",
                                              command=self.update_metadata)
        self.btn_update_meta.pack(side="left", padx=(0, 10))

        self.btn_repair = ctk.CTkButton(btn_row, text="🔧 Repair Station", font=ctk.CTkFont(size=12),
                                         fg_color="#e65100", text_color="#fff", hover_color="#bf360c",
                                         command=self.repair_station)
        self.btn_repair.pack(side="left", padx=(0, 10))

        self.btn_start_over = ctk.CTkButton(btn_row, text="Start Over", font=ctk.CTkFont(size=12),
                                             fg_color="#d32f2f", text_color="#fff", hover_color="#b71c1c",
                                             command=self.start_over)
        self.btn_start_over.pack(side="left")

        # Bind station name changes
        self.entry_station_name.bind("<KeyRelease>", lambda e: self._refresh_station_status())

        # Check on startup
        self.after(800, self._refresh_station_status)

        # Open Folders Buttons
        self.folder_frame = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        self.folder_frame.pack(fill="x", padx=20, pady=10)
        self.btn_open_input = ctk.CTkButton(self.folder_frame, text="Open Input Folder (Manual)", command=lambda: os.startfile("input_music"), fg_color="#333")
        self.btn_open_input.pack(side="left", padx=(0, 10))
        self.btn_open_output = ctk.CTkButton(self.folder_frame, text="Open Output Folder", command=lambda: os.startfile("output"), fg_color="#333")
        self.btn_open_output.pack(side="left")
        
        # Log Console
        self.console = ctk.CTkTextbox(self.right_panel, height=200, state="disabled")
        self.console.pack(fill="both", expand=True, padx=20, pady=10)
        
        # Generate Button
        self.btn_generate = ctk.CTkButton(self.right_panel, text="GENERATE RADIO STATION", font=ctk.CTkFont(size=18, weight="bold"), height=50, fg_color="#fcee0a", text_color="#000", hover_color="#c4b908", command=self.start_generation)
        self.btn_generate.pack(fill="x", padx=20, pady=20)
        
    def toggle_el_key(self):
        if self.show_el_key.get():
            self.entry_el_key.configure(show="")
            self.entry_suno_key.configure(show="")
        else:
            self.entry_el_key.configure(show="*")
            self.entry_suno_key.configure(show="*")
            
    def log(self, message):
        self.console.configure(state="normal")
        self.console.insert("end", message + "\n")
        self.console.see("end")
        self.console.configure(state="disabled")
        
    def check_all_credits(self):
        """Check API credits + populate voice dropdown in background."""

        def run():
            el_key = self.entry_el_key.get()
            sn_key = self.entry_suno_key.get()
            voice_data = None
            el_data = None
            sn_data = None

            # Fetch data in background thread
            if el_key:
                ok, voices = list_voices(el_key)
                if ok and voices:
                    voice_options = []
                    for v in voices:
                        cat = v.get("category", "").upper()
                        name = v.get("name", "?")
                        vid = v.get("voice_id", "?")
                        label = f"[{cat}] {name} ({vid[:8]}...)"
                        voice_options.append((label, vid))
                    voice_options.sort(key=lambda item: (
                        0 if "[PREMADE]" in item[0].upper() else 1 if "[GENERATED]" in item[0].upper() else 2,
                        item[0]
                    ))
                    voice_data = voice_options

                ok, remaining, limit = get_user_info(el_key)
                el_data = (ok, remaining, limit)

            if sn_key:
                ok, credits, msg = get_suno_credits(sn_key)
                sn_data = (ok, credits, msg)

            # Update UI on main thread
            self.after(0, self._apply_credits, voice_data, el_data, sn_data)

        threading.Thread(target=run, daemon=True).start()

    def _apply_credits(self, voice_data, el_data, sn_data):
        """Apply fetched API data to GUI (runs on main thread)."""
        if voice_data is not None:
            self.voice_id_map = dict(voice_data)
            labels = [v[0] for v in voice_data]
            self.voice_dropdown.configure(values=labels)
            current_vid = self.config.get("elevenlabs_voice_id", "")
            found = False
            for label, vid in voice_data:
                if vid == current_vid:
                    self.voice_var.set(label)
                    found = True
                    break
            if not found:
                for label, vid in voice_data:
                    if "[PREMADE]" in label:
                        self.voice_var.set(label)
                        self.config["elevenlabs_voice_id"] = vid
                        break

        if el_data is not None:
            ok, remaining, limit = el_data
            if ok:
                self.lbl_el_credits.configure(
                    text=f"ElevenLabs: {remaining}/{limit} chars",
                    text_color="#4CAF50" if remaining > 0 else "#f44336"
                )
            elif remaining == "invalid_key":
                self.lbl_el_credits.configure(text="ElevenLabs: invalid key", text_color="#f44336")
            else:
                self.lbl_el_credits.configure(text="ElevenLabs: unreachable", text_color="#888")
        else:
            self.lbl_el_credits.configure(text="")

        if sn_data is not None:
            ok, credits, msg = sn_data
            if ok:
                self.lbl_suno_credits.configure(
                    text=f"Suno: {credits} credits",
                    text_color="#4CAF50" if credits > 0 else "#f44336"
                )
            else:
                self.lbl_suno_credits.configure(
                    text="Suno: invalid key" if "Invalid" in msg else "Suno: unreachable",
                    text_color="#f44336"
                )
        else:
            self.lbl_suno_credits.configure(text="")

    def _get_voice_id(self):
        """Extract the actual voice ID from the dropdown label."""
        label = self.voice_var.get()
        return self.voice_id_map.get(label, label)

    def test_elevenlabs(self):
        self.log("Checking ElevenLabs account...")
        api_key = self.entry_el_key.get()

        def run_test():
            if not api_key:
                self.log("  ❌ No API key entered.")
                return

            ok, remaining, limit = get_user_info(api_key)
            if ok:
                self.log(f"  ✅ Connected! Credits: {remaining}/{limit} characters remaining.")
                self.lbl_el_credits.configure(
                    text=f"ElevenLabs: {remaining}/{limit} chars",
                    text_color="#4CAF50" if remaining > 0 else "#f44336"
                )
                ok2, voices = list_voices(api_key)
                if ok2 and voices:
                    self.log(f"  🎤 Available voices: {len(voices)}")
                    for v in voices:
                        cat = v.get("category", "").upper()
                        name = v.get("name", "?")
                        vid = v.get("voice_id", "?")
                        tag = "✅" if cat == "PREMADE" else "⚠️" if cat == "GENERATED" else "❌"
                        self.log(f"     {tag} [{cat}] {name} ({vid})")
                    self.log("  ✅ = works on free API  |  ⚠️ = generated  |  ❌ = paid only")
                return
            if remaining == "invalid_key":
                self.log("  ❌ API key is invalid or expired.")
                self.log("  Go to elevenlabs.io → Profile → API Keys to generate a new one.")
                self.lbl_el_credits.configure(text="ElevenLabs: invalid key", text_color="#f44336")
            else:
                self.log(f"  ❌ Could not reach ElevenLabs: {limit}")
                self.lbl_el_credits.configure(text="ElevenLabs: unreachable", text_color="#888")

        threading.Thread(target=run_test, daemon=True).start()

    def test_suno(self):
        self.log("Checking Suno credits...")
        api_key = self.entry_suno_key.get()

        def run_test():
            if not api_key:
                self.log("  ❌ No Suno API key entered.")
                return

            ok, credits, msg = get_suno_credits(api_key)
            if ok:
                self.log(f"  ✅ Suno connected! Credits remaining: {credits}")
                self.lbl_suno_credits.configure(
                    text=f"Suno: {credits} credits",
                    text_color="#4CAF50" if credits > 0 else "#f44336"
                )
            else:
                self.log(f"  ❌ Suno error: {msg}")
                self.lbl_suno_credits.configure(
                    text="Suno: invalid key" if "Invalid" in msg else "Suno: unreachable",
                    text_color="#f44336"
                )

        threading.Thread(target=run_test, daemon=True).start()

    def test_llm(self):
        self.log("Testing LLM Connection...")
        url = self.entry_llm_url.get()
        provider = self.llm_option.get()
        
        def run_test():
            try:
                if provider == "LM Studio":
                    res = requests.get(f"{url.rstrip('/')}/models", timeout=5)
                else:
                    res = requests.get(f"{url.rstrip('/')}/api/tags", timeout=5)
                    
                if res.status_code == 200:
                    self.log(f"  ✅ SUCCESS: Connected to {provider}!")
                else:
                    self.log(f"  ❌ FAILED: Got status {res.status_code}")
            except Exception as e:
                self.log(f"  ❌ Could not connect to {url}. Is the server running?")
                
        threading.Thread(target=run_test, daemon=True).start()

    def save_settings(self):
        self.config["elevenlabs_api_key"] = self.entry_el_key.get()
        self.config["elevenlabs_voice_id"] = self._get_voice_id()
        self.config["suno_api_key"] = self.entry_suno_key.get()
        self.config["llm_provider"] = self.llm_option.get()
        self.config["llm_api_url"] = self.entry_llm_url.get()
        self.config["station_name"] = self.entry_station_name.get()
        self.config["station_frequency"] = self.entry_station_freq.get()
        icon_label = self.icon_var.get()
        for name, val in ICON_OPTIONS:
            if name == icon_label:
                self.config["station_icon"] = val
                break
        try:
            self.config["song_count"] = max(1, int(self.entry_song_count.get()))
        except ValueError:
            self.config["song_count"] = 3
        raw_styles = self.text_song_styles.get("0.0", "end").strip()
        self.config["song_styles"] = [line.strip() for line in raw_styles.split("\n") if line.strip()]
        save_config(self.config)
        self.log("✅ Settings saved!")

    def _station_output_dir(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "output", self.entry_station_name.get().replace(" ", "_"))

    def _sanity_check_station(self, output_dir, meta):
        """Inspect existing station for missing/inconsistent files. Returns a list of issue strings."""
        issues = []
        if not meta or not meta.get("order"):
            return issues

        listed = meta.get("order", [])

        # Check 1: files listed in metadata exist on disk
        missing_files = [t for t in listed if not os.path.exists(os.path.join(output_dir, t))]
        if missing_files:
            issues.append(f"❌ {len(missing_files)} track(s) missing from disk: {', '.join(missing_files[:3])}")
            if len(missing_files) > 3:
                issues[-1] += f" (+{len(missing_files) - 3} more)"

        # Check 2: orphaned MP3s on disk not in metadata
        on_disk = set(f for f in os.listdir(output_dir) if f.lower().endswith(".mp3"))
        in_meta = set(listed)
        orphans = sorted(on_disk - in_meta)
        if orphans:
            issues.append(f"📁 {len(orphans)} track(s) on disk not in metadata: {', '.join(orphans[:3])}")
            if len(orphans) > 3:
                issues[-1] += f" (+{len(orphans) - 3} more)"

        # Check 3: station has music but no anchor intro
        has_music = any("Suno_Song" in t or "Music_" in t for t in listed)
        has_intro = any("Anchorman_Intro" in t for t in listed)
        if has_music and not has_intro:
            issues.append("🎙️ No anchor intro — station has music but no voice. Add one!")
            # Auto-suggest adding an interlude
            try:
                current = int(self.spin_interludes.get())
                if current == 0:
                    self.spin_interludes.set("1")
            except ValueError:
                self.spin_interludes.set("1")

        # Check 4: orphaned cover.jpg not in metadata (non-critical, just note)
        cover = os.path.join(output_dir, "cover.jpg")
        if os.path.exists(cover) and not os.path.exists(os.path.join(output_dir, "metadata.json")):
            issues.append("🖼️  cover.jpg found but no metadata.json")

        return issues

    def _refresh_station_status(self):
        output_dir = self._station_output_dir()
        meta = read_radioext_metadata(output_dir)
        if meta and meta.get("order"):
            count = len(meta["order"])
            name = meta.get("displayName", f"{self.entry_station_freq.get()} {self.entry_station_name.get()}")

            issues = self._sanity_check_station(output_dir, meta)
            lines = [f"📀 Station \"{name}\" has {count} track(s)."]
            if issues:
                lines.extend(issues)
                lines.append("     Use the controls below to repair or expand.")
            else:
                lines.append("     ✅ All tracks accounted for.")
                lines.append("     Add more content or start a fresh station.")

            self.lbl_station_status.configure(
                text="\n".join(lines),
                text_color="#ffcc00" if issues else "#4CAF50",
                justify="left"
            )
            self.continue_frame.pack(fill="x", padx=20, pady=(5, 0), before=self.folder_frame)

            # Only show repair button when there are actual issues
            if issues:
                self.btn_repair.pack(side="left", padx=(0, 10))
            else:
                self.btn_repair.pack_forget()
        else:
            self.continue_frame.pack_forget()

    def repair_station(self):
        """Auto-detect and fix station issues in a background thread."""
        self.save_settings()
        output_dir = self._station_output_dir()
        meta = read_radioext_metadata(output_dir)
        if not meta or not meta.get("order"):
            self.log("❌ Nothing to repair — no station metadata found.")
            return

        def run_repair():
            from llm_client import generate_script
            from tts_client import generate_voice
            from audio_processor import apply_radio_effect, create_radioext_metadata

            listed = meta.get("order", [])
            intro_missing = not any("Anchorman_Intro" in t for t in listed)

            # ── FIX: Generate intro if missing ──────────────────────────────
            if intro_missing:
                self.after(0, lambda: self.log("🎙️  Intro missing — generating now..."))

                system_prompt = self.config.get("host_prompt",
                    "You are a cynical, dynamic radio host in Night City.")
                user_prompt = (
                    "Write a high-energy, theatrical radio intro for a Night City cyberpunk station. "
                    "Start with a greeting like 'Good morning Night City!' "
                    "Be charismatic, sarcastic, and street-smart. Reference current events "
                    "(corpo wars, cyberpsychos, braindance craze, the latest gang dispute). "
                    "End by hinting at the first song. Output ONLY the 3-4 spoken sentences."
                )

                script = generate_script(
                    self.config["llm_api_url"],
                    self.config["llm_provider"],
                    system_prompt,
                    user_prompt
                )

                if script.startswith("Error"):
                    self.after(0, lambda: self.log(f"  ❌ Intro script failed — {script}"))
                else:
                    self.after(0, lambda: self.log(f"  ✅ Intro script ({len(script)} chars): {script[:80].strip()}..."))

                    import tempfile as tf
                    temp_raw = os.path.join(tf.gettempdir(), "cyberradio_repair_intro.mp3")
                    success, msg = generate_voice(
                        self.config["elevenlabs_api_key"],
                        self.config["elevenlabs_voice_id"],
                        script,
                        temp_raw
                    )

                    if not success:
                        self.after(0, lambda: self.log(f"  ❌ Intro voice failed — {msg}"))
                        return

                    self.after(0, lambda: self.log(f"  {msg}"))

                    # Save intro as 001 — existing tracks keep their numbers
                    exists = [f for f in os.listdir(output_dir) if f.lower().endswith(".mp3")]
                    if any(f.startswith("001_") for f in exists):
                        # Rare: 001 taken by non-intro file. Shift everything up.
                        mp3s = sorted(exists, key=lambda x: int(x[:3]) if x[:3].isdigit() else 0, reverse=True)
                        for f in mp3s:
                            if f[:3].isdigit():
                                num = int(f[:3])
                                new_name = f"{str(num + 1).zfill(3)}{f[3:]}"
                                os.rename(os.path.join(output_dir, f), os.path.join(output_dir, new_name))
                                self.after(0, lambda old=f, new=new_name: self.log(f"  🔄 {old} → {new}"))

                    out_path = os.path.join(output_dir, "001_Anchorman_Intro.mp3")
                    ok, _ = apply_radio_effect(temp_raw, out_path)
                    if not ok:
                        import shutil as sh
                        sh.copy(temp_raw, out_path)
                    self.after(0, lambda: self.log("  ✅ 001_Anchorman_Intro.mp3 saved."))

                    try:
                        os.remove(temp_raw)
                    except Exception:
                        pass

            # ── Always rebuild metadata from actual files on disk ────────────
            final_tracks = sorted(
                [f for f in os.listdir(output_dir) if f.lower().endswith(".mp3")],
                key=lambda x: int(x[:3]) if x[:3].isdigit() else 999
            )
            create_radioext_metadata(
                self.config["station_name"],
                self.config["station_frequency"],
                self.config["station_volume"],
                final_tracks,
                output_dir,
                self.config.get("station_icon", "UIIcon.RadioElectronic")
            )
            self.after(0, lambda: self.log(f"  ✅ metadata.json rebuilt with {len(final_tracks)} track(s)."))

            self.after(0, lambda: self.log("🔧 Repair complete."))
            self.after(0, self._refresh_station_status)

        threading.Thread(target=run_repair, daemon=True).start()

    def update_metadata(self):
        """Rewrite metadata.json with current settings — no API calls, instant."""
        self.save_settings()
        output_dir = self._station_output_dir()
        if not os.path.isdir(output_dir):
            self.log("❌ No station folder found. Generate a station first.")
            return

        actual_tracks = sorted(
            [f for f in os.listdir(output_dir) if f.lower().endswith(".mp3")],
            key=lambda x: int(x[:3]) if x[:3].isdigit() else 999
        )
        if not actual_tracks:
            self.log("❌ No MP3 files found in station folder.")
            return

        from audio_processor import create_radioext_metadata
        ok = create_radioext_metadata(
            self.config["station_name"],
            self.config["station_frequency"],
            self.config["station_volume"],
            actual_tracks,
            output_dir,
            self.config.get("station_icon", "UIIcon.RadioElectronic")
        )
        if ok:
            self.log(f"✅ Metadata updated — icon, name, frequency applied to {len(actual_tracks)} track(s).")
        else:
            self.log("❌ Failed to write metadata.json.")
        self._refresh_station_status()

    def start_continuation(self):
        self.save_settings()
        existing_meta = read_radioext_metadata(self._station_output_dir())
        if not existing_meta or not existing_meta.get("order"):
            self.log("❌ No existing tracks found in this station folder.")
            return

        existing_tracks = existing_meta.get("order", [])
        try:
            interludes = int(self.spin_interludes.get())
        except ValueError:
            interludes = 0
        try:
            songs = int(self.spin_songs.get())
        except ValueError:
            songs = 0

        if interludes + songs == 0:
            self.log("⚠️  Set at least 1 interlude or 1 song to add.")
            return

        # Reset any "fresh" generation config flags
        self.log("")
        self.log("===============================")
        self.log(f"Adding {interludes} interlude(s) + {songs} song(s)...")

        def check_and_run():
            el_key = self.config.get("elevenlabs_api_key", "")
            sn_key = self.config.get("suno_api_key", "")

            warnings = []
            if el_key and interludes > 0:
                ok, remaining, limit = get_user_info(el_key)
                if ok and remaining < 300 * interludes:
                    warnings.append(
                        f"⚠️  ElevenLabs may not have enough chars\n"
                        f"    for {interludes} interlude(s) ({remaining}/{limit} left)."
                    )
                elif ok and remaining <= 0:
                    warnings.append("❌ ElevenLabs: 0 chars. Interludes will be skipped.")
                elif not ok and remaining != "invalid_key":
                    warnings.append(f"⚠️  Could not reach ElevenLabs.")
            if sn_key and songs > 0:
                ok, credits, msg = get_suno_credits(sn_key)
                if ok and credits < songs:
                    warnings.append(
                        f"⚠️  Suno only has {credits} credits but you need {songs}."
                    )
                elif not ok:
                    warnings.append(f"❌ Suno error: {msg}")

            if warnings:
                from tkinter import messagebox
                msg = "Continue Check:\n\n" + "\n\n".join(warnings)
                msg += "\n\nProceed anyway?"
                if not messagebox.askyesno("CyberRadio-Gen — Continue Check", msg, icon="warning"):
                    self.log("⏹️  Continue cancelled by user.")
                    return

            self.btn_add_to_station.configure(state="disabled", text="ADDING...")
            self.log("Starting continuation process...")

            try:
                result = run_generation_pipeline(
                    self.config, self.log,
                    mode="continue",
                    existing_tracks=existing_tracks,
                    new_interludes=interludes,
                    new_songs=songs
                )
                self.log("")
                if result == "complete":
                    self.log("🎉 TRACKS ADDED SUCCESSFULLY!")
                elif result == "partial":
                    self.log("⚠️  ADDING FINISHED WITH ISSUES — see details above.")
                else:
                    self.log("❌ ADDING FAILED — check errors above.")
            except Exception as e:
                self.log(f"💥 UNEXPECTED CRASH: {str(e)}")
                import traceback
                self.log(traceback.format_exc())
            finally:
                self.btn_add_to_station.configure(state="normal", text="ADD TO STATION")
                self._refresh_station_status()

        threading.Thread(target=check_and_run, daemon=True).start()

    def start_over(self):
        from tkinter import messagebox
        name = self.entry_station_name.get()
        if not messagebox.askyesno(
            "Start Over",
            f"⚠️  This will DELETE all existing tracks for \"{name}\".\n\n"
            f"    Folder: {self._station_output_dir()}\n\n"
            f"    This cannot be undone. Continue?",
            icon="warning"
        ):
            return

        output_dir = self._station_output_dir()
        if os.path.exists(output_dir):
            try:
                for f in os.listdir(output_dir):
                    fp = os.path.join(output_dir, f)
                    if os.path.isfile(fp):
                        os.remove(fp)
                self.log(f"🗑️  Deleted existing tracks in {output_dir}")
            except Exception as e:
                self.log(f"⚠️  Could not delete folder: {e}")

        self._refresh_station_status()
        self.log("✅ Station is cleared. You can now generate a fresh station.")

    def start_generation(self):
        self.save_settings()
        self.log("===============================")
        self.log("Checking credits before starting...")

        def check_and_run():
            el_key = self.config.get("elevenlabs_api_key", "")
            sn_key = self.config.get("suno_api_key", "")

            warnings = []
            el_ok = False
            sn_ok = False

            # Check ElevenLabs
            if el_key:
                ok, remaining, limit = get_user_info(el_key)
                if ok:
                    el_ok = True
                    if remaining < 500:
                        warnings.append(
                            f"⚠️  ElevenLabs only has {remaining}/{limit} characters left.\n"
                            f"    The anchor voice needs ~300-500 chars. You may run out mid-generation."
                        )
                elif remaining == "invalid_key":
                    warnings.append("❌ ElevenLabs API key is invalid or expired.")
                else:
                    warnings.append(f"⚠️  Could not reach ElevenLabs ({limit}). Generation may fail.")
            else:
                warnings.append("❌ No ElevenLabs API key. The anchor voice will be skipped.")

            # Check Suno
            if sn_key:
                ok, credits, msg = get_suno_credits(sn_key)
                if ok:
                    sn_ok = True
                    if credits < 2:
                        warnings.append(
                            f"⚠️  Suno only has {credits} credits left.\n"
                            f"    Each song costs ~1 credit. You may not get a full track."
                        )
                    elif credits < 5:
                        warnings.append(
                            f"⚠️  Suno credits are low ({credits} remaining).\n"
                            f"    Generation may fail if the API deducts more than expected."
                        )
                else:
                    warnings.append(f"❌ Suno API error: {msg}")
            else:
                warnings.append("ℹ️  No Suno API key — will use manual music mode.")

            # Show confirmation dialog if there are warnings
            if warnings:
                msg = "Credit Check Warnings:\n\n" + "\n\n".join(warnings)
                msg += "\n\nDo you want to proceed anyway?"
                msg += "\n(If generation fails midway, credits from successful steps are spent.)"

                from tkinter import messagebox
                proceed = messagebox.askyesno(
                    title="CyberRadio-Gen — Credit Check",
                    message=msg,
                    icon="warning" if any("❌" in w or "⚠️" in w for w in warnings) else "info"
                )
                if not proceed:
                    self.log("⏹️  Generation cancelled by user.")
                    return

            # Start the pipeline
            self.btn_generate.configure(state="disabled", text="GENERATING...")
            self.log("===============================")
            self.log("Starting Generation Process...")

            try:
                result = run_generation_pipeline(self.config, self.log)
                self.log("")
                if result == "complete":
                    self.log("🎉 GENERATION COMPLETE — your radio station is ready!")
                elif result == "partial":
                    self.log("⚠️  GENERATION FINISHED WITH ISSUES — see details above.")
                    self.log("    The station was partially created (some tracks may be missing).")
                else:
                    self.log("❌ GENERATION FAILED — check errors above.")
            except Exception as e:
                self.log(f"💥 UNEXPECTED CRASH: {str(e)}")
                import traceback
                self.log(traceback.format_exc())
            finally:
                self.btn_generate.configure(state="normal", text="GENERATE RADIO STATION")

        threading.Thread(target=check_and_run, daemon=True).start()
