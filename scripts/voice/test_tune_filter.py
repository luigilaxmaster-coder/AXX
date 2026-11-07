import sys
import os
import pathlib
import subprocess
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from scripts.voice.compare_acoustics import get_acoustic_profile

def main():
    ref_path = pathlib.Path(r"C:\Users\luigi\AppData\Local\Axx\speech\voices\axx-morcito.wav")
    ref_profile = get_acoustic_profile(ref_path)
    print("TARGET (Girlfriend Reference):")
    print(ref_profile)
    
    from backend.speech.piper_tts import PiperSpeechService
    svc = PiperSpeechService(data_dir=pathlib.Path(r"C:\Users\luigi\AppData\Local\Axx"))
    res = svc.synthesize({"text": "Hola mi amor, te amo mucho y te estaba esperando.", "voice": "piper:axx-morcito-es"})
    
    import base64
    raw_wav = pathlib.Path("test_raw_piper.wav")
    raw_wav.write_bytes(base64.b64decode(res["audio_base64"]))
    raw_profile = get_acoustic_profile(raw_wav)
    print("\nCURRENT PIPER RAW OUTPUT:")
    print(raw_profile)
    
    # Calculate exact pitch ratio:
    pitch_ratio = ref_profile["pitch_median"] / raw_profile["pitch_median"]
    print(f"\nTarget Pitch Ratio: {pitch_ratio:.4f} (shift ~ {12 * (pitch_ratio - 1):.2f} semitones)")
    
    # Test ffmpeg rubberband + warmth EQ
    # rubberband filter changes pitch without changing speed!
    # Equalizer: boost warmth at 280Hz (+2.5dB, Q=1.2), soften nasal treble at 3600Hz (-2.5dB, Q=1.5)
    filtered_wav = pathlib.Path("test_filtered_piper.wav")
    af_filter = f"rubberband=pitch={pitch_ratio:.4f}:formant=preserved,equalizer=f=260:width_type=q:w=1.2:g=2.5,equalizer=f=3800:width_type=q:w=1.4:g=-3.0"
    
    cmd = [
        "ffmpeg", "-y", "-v", "error", "-i", str(raw_wav),
        "-af", af_filter,
        str(filtered_wav)
    ]
    subprocess.run(cmd, check=True)
    
    filtered_profile = get_acoustic_profile(filtered_wav)
    print("\nPITCH & TIMBRE TUNED PIPER OUTPUT:")
    print(filtered_profile)
    
    print("\nComparison:")
    print(f"  Target Pitch:  {ref_profile['pitch_median']:.1f} Hz -> Tuned Pitch:  {filtered_profile['pitch_median']:.1f} Hz")
    print(f"  Target Brightness (Centroid): {ref_profile['centroid_mean']:.1f} Hz -> Tuned: {filtered_profile['centroid_mean']:.1f} Hz")
    
    raw_wav.unlink(missing_ok=True)
    filtered_wav.unlink(missing_ok=True)

if __name__ == "__main__":
    main()
