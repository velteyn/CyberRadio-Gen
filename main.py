import os
import sys

def main():
    # Ensure working directory is correct
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Create necessary base folders
    os.makedirs("input_music", exist_ok=True)
    os.makedirs("output", exist_ok=True)
    os.makedirs("temp", exist_ok=True)
    
    # Import and run GUI
    from app_gui import CyberRadioApp
    app = CyberRadioApp()
    app.mainloop()

if __name__ == "__main__":
    main()
