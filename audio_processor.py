import os
import subprocess
import shutil

def apply_radio_effect(input_path, output_path):
    """
    Applies a radio effect to an MP3 file to simulate in-game radio broadcast.
    Uses ffmpeg directly to apply bandpass filtering (high-pass + low-pass) and dynamic range compression.
    """
    try:
        # Check if ffmpeg is installed
        if not shutil.which("ffmpeg"):
            print("FFmpeg is not installed. Skipping audio post-processing. Copying original file.")
            shutil.copy(input_path, output_path)
            return True, "Audio processed (no effects applied due to missing FFmpeg)."

        # FFmpeg filter chain:
        # highpass: 300Hz
        # lowpass: 5000Hz
        # acompressor: compress dynamic range
        # loudnorm: normalize volume
        filter_str = "highpass=f=300,lowpass=f=5000,acompressor,loudnorm"
        
        cmd = [
            "ffmpeg",
            "-y",               # overwrite output
            "-i", input_path,
            "-af", filter_str,
            "-b:a", "192k",
            output_path
        ]
        
        # Run ffmpeg, suppress output
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        if result.returncode != 0:
            print(f"FFmpeg error: {result.stderr}")
            # Fallback to copy
            shutil.copy(input_path, output_path)
            return False, f"FFmpeg processing failed. Fallback to copy. Error: {result.stderr[-200:]}"
            
        return True, "Audio processed successfully."
    except Exception as e:
        # Ultimate fallback
        try:
            shutil.copy(input_path, output_path)
        except:
            pass
        return False, f"Audio processing failed: {str(e)}. Original file copied."

def read_radioext_metadata(output_dir):
    """Read existing metadata.json, return the dict or None."""
    import json
    path = os.path.join(output_dir, "metadata.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception:
        return None

def create_radioext_metadata(station_name, frequency, volume, track_list, output_dir):
    """
    Creates the metadata.json file required for RadioExt.
    track_list should be a list of filenames like ["001_Intro.mp3", "002_Song.mp3"]
    """
    import json
    
    metadata = {
        "displayName": station_name,
        "fm": float(frequency),
        "volume": float(volume),
        "icon": "UIIcon.RadioHipHop",
        "customIcon": {
            "useCustom": False,
            "inkAtlasPath": "",
            "inkAtlasPart": ""
        },
        "streamInfo": {
            "isStream": False,
            "streamURL": ""
        },
        "order": track_list
    }
    
    try:
        with open(os.path.join(output_dir, "metadata.json"), 'w') as f:
            json.dump(metadata, f, indent=4)
        return True
    except Exception as e:
        print(f"Error writing metadata.json: {e}")
        return False
