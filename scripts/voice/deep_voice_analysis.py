import os
import sys
import subprocess
import json
import base64
import tempfile
from pathlib import Path
import numpy as np
from faster_whisper import WhisperModel

sys.path.insert(0, r"C:\Users\luigi\Desktop\axx2")

files = {
    'Page3': r'C:\Users\luigi\.gemini\antigravity\brain\49e4d794-e15c-403e-bc2b-2725483070ae\.user_uploaded\media_1793586246328_185856b8.mp4',
    'Page_1_Spanish': r'C:\Users\luigi\.gemini\antigravity\brain\49e4d794-e15c-403e-bc2b-2725483070ae\.user_uploaded\media_1793586253170_31c780de.mp4',
    'Page_1_English': r'C:\Users\luigi\.gemini\antigravity\brain\49e4d794-e15c-403e-bc2b-2725483070ae\.user_uploaded\media_1793586253175_6d9e211f.mp4',
    'Page_2_Spanish': r'C:\Users\luigi\.gemini\antigravity\brain\49e4d794-e15c-403e-bc2b-2725483070ae\.user_uploaded\media_1793586253164_782b2b50.mp4',
    'Page_2_English': r'C:\Users\luigi\.gemini\antigravity\brain\49e4d794-e15c-403e-bc2b-2725483070ae\.user_uploaded\media_1793586253168_0902e299.mp4',
}

def analyze_audio_pcm(file_path):
    cmd = ["ffmpeg", "-v", "error", "-i", str(file_path), "-ar", "22050", "-ac", "1", "-f", "s16le", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    sr = 22050
    duration = len(samples) / sr
    
    # FFT spectral features
    fft_size = 1024
    hop = 512
    centroids = []
    rolloffs = []
    freqs = np.fft.rfftfreq(fft_size, 1.0 / sr)
    window = np.hanning(fft_size)
    
    for i in range(0, len(samples) - fft_size, hop):
        frame = samples[i:i+fft_size]
        if np.std(frame) < 150:
            continue
        mag = np.abs(np.fft.rfft(frame * window))
        total_mag = np.sum(mag)
        if total_mag > 0:
            c = np.sum(freqs * mag) / total_mag
            centroids.append(c)
            # Rolloff 85%
            cum = np.cumsum(mag)
            idx = np.searchsorted(cum, 0.85 * total_mag)
            rolloffs.append(freqs[min(idx, len(freqs)-1)])
            
    # Autocorrelation pitch F0
    frame_len = 882  # 40ms window
    hop_p = 220    # 10ms hop
    pitches = []
    for i in range(0, len(samples) - frame_len, hop_p):
        frame = samples[i:i+frame_len]
        if np.std(frame) < 250:
            continue
        corr = np.correlate(frame, frame, mode="full")[frame_len-1:]
        # lags corresponding to 75 Hz to 400 Hz: lag = sr / f
        # 22050 / 400 = ~55, 22050 / 75 = ~294
        sub = corr[55:294]
        if len(sub) == 0:
            continue
        peak_idx = 55 + np.argmax(sub)
        p = sr / peak_idx
        if 80 <= p <= 380:
            pitches.append(p)

    rms = np.sqrt(np.mean(samples**2))
    
    return {
        'duration_sec': float(duration),
        'samples_count': len(samples),
        'rms_energy': float(rms),
        'pitch': {
            'median': float(np.median(pitches)) if pitches else 0.0,
            'mean': float(np.mean(pitches)) if pitches else 0.0,
            'std': float(np.std(pitches)) if pitches else 0.0,
            'min': float(np.min(pitches)) if pitches else 0.0,
            'max': float(np.max(pitches)) if pitches else 0.0,
            'voiced_segments': len(pitches)
        },
        'timbre': {
            'spectral_centroid_mean': float(np.mean(centroids)) if centroids else 0.0,
            'spectral_centroid_std': float(np.std(centroids)) if centroids else 0.0,
            'spectral_rolloff_85_mean': float(np.mean(rolloffs)) if rolloffs else 0.0,
        }
    }

if __name__ == '__main__':
    print("Loading Whisper Model...")
    whisper = WhisperModel("resources/models/faster-whisper-tiny", device="cpu", compute_type="int8")

    print("\n================ COMPREHENSIVE VOICE & TRANSCRIPTION ANALYSIS ================\n")

    full_analysis = {}

    for name, orig_path in files.items():
        acoustics = analyze_audio_pcm(orig_path)
        
        # Pass float32 16kHz numpy array directly to whisper to bypass av.open version conflict
        raw_16k = subprocess.run(["ffmpeg", "-v", "error", "-i", str(orig_path), "-ar", "16000", "-ac", "1", "-f", "s16le", "-"],
                                 capture_output=True, check=True).stdout
        samples_16k = np.frombuffer(raw_16k, dtype=np.int16).astype(np.float32) / 32768.0
        segments, info = whisper.transcribe(samples_16k, beam_size=5)
        seg_list = []
        full_text = []
        for s in segments:
            seg_list.append({'start': round(s.start, 2), 'end': round(s.end, 2), 'text': s.text.strip()})
            full_text.append(s.text.strip())
        
        transcription = {
            'language': info.language,
            'language_probability': float(info.language_probability),
            'duration': float(info.duration),
            'text': " ".join(full_text),
            'segments_count': len(seg_list),
            'segments': seg_list
        }
        
        full_analysis[name] = {
            'acoustics': acoustics,
            'transcription': transcription
        }
        
        print(f"[{name.upper()}] (Duration: {acoustics['duration_sec']:.1f}s, Language: {info.language.upper()} {info.language_probability*100:.0f}%)")
        print(f"  Pitch F0 (Tono): Median = {acoustics['pitch']['median']:.1f} Hz | Mean = {acoustics['pitch']['mean']:.1f} Hz | Std = {acoustics['pitch']['std']:.1f} Hz")
        print(f"  Pitch Range: {acoustics['pitch']['min']:.1f} Hz - {acoustics['pitch']['max']:.1f} Hz")
        print(f"  Timbre (Centroide Espectral): {acoustics['timbre']['spectral_centroid_mean']:.1f} Hz | Rolloff 85%: {acoustics['timbre']['spectral_rolloff_85_mean']:.1f} Hz")
        print(f"  Frases detectadas ({len(seg_list)}): {transcription['text'][:140]}...\n")

    # Analyze reference axx-morcito.wav
    ref_path = Path(os.path.expandvars(r"%LOCALAPPDATA%\Axx\speech\voices\axx-morcito.wav"))
    if ref_path.is_file():
        ref_acoustics = analyze_audio_pcm(str(ref_path))
        print("[MOSS REFERENCE: axx-morcito.wav]")
        print(f"  Pitch F0: Median = {ref_acoustics['pitch']['median']:.1f} Hz | Mean = {ref_acoustics['pitch']['mean']:.1f} Hz")
        print(f"  Timbre (Centroide): {ref_acoustics['timbre']['spectral_centroid_mean']:.1f} Hz")
        print(f"  Rolloff 85%: {ref_acoustics['timbre']['spectral_rolloff_85_mean']:.1f} Hz\n")
        full_analysis['reference_moss'] = ref_acoustics

    Path("deep_voice_analysis.json").write_text(json.dumps(full_analysis, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Saved complete acoustic breakdown to deep_voice_analysis.json")

