import customtkinter as ctk
import os
import threading
from config_manager import load_config, save_config
from pipeline import run_generation_pipeline
from tts_client import get_user_info, list_voices
from suno_client import get_suno_credits
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
        try:
            self.config["song_count"] = max(1, int(self.entry_song_count.get()))
        except ValueError:
            self.config["song_count"] = 3
        raw_styles = self.text_song_styles.get("0.0", "end").strip()
        self.config["song_styles"] = [line.strip() for line in raw_styles.split("\n") if line.strip()]
        save_config(self.config)
        self.log("✅ Settings saved!")

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
