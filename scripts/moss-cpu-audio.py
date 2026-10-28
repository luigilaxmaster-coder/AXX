"""Run upstream MOSS CPU audio tools when TorchCodec cannot load FFmpeg."""
from pathlib import Path
import runpy
import sys


def main():
    if len(sys.argv) < 3 or sys.argv[2] not in ("prepare_data", "verify"):
        raise SystemExit("Usage: moss-cpu-audio.py MOSS_ROOT prepare_data|verify [arguments]")
    root = Path(sys.argv.pop(1)).resolve()
    script = root / "finetuning" / (sys.argv.pop(1) + ".py")
    if not script.is_file():
        raise SystemExit(f"MOSS preparation script not found: {script}")
    import soundfile as sf
    import torch
    import torchaudio

    def load_wav(path):
        samples, rate = sf.read(path, dtype="float32", always_2d=True)
        return torch.from_numpy(samples.T.copy()), rate

    def save_wav(path, waveform, rate):
        sf.write(path, waveform.detach().cpu().numpy().T, rate, subtype="PCM_16")

    torchaudio.load = load_wav
    torchaudio.save = save_wav
    sys.path.insert(0, str(root))
    sys.argv[0] = str(script)
    runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main()
