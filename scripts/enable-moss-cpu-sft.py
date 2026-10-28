"""Create a CPU-capable copy of upstream MOSS SFT without changing upstream code."""
from pathlib import Path
import sys


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: enable-moss-cpu-sft.py MOSS_ROOT")
    root = Path(sys.argv[1]).resolve()
    source = root / "finetuning" / "sft.py"
    target = root / "finetuning" / "sft_cpu.py"
    original = source.read_text(encoding="utf-8")
    guard = '''    if accelerator.device.type != "cuda":
        raise EnvironmentError(
            f"MOSS-TTS-Nano finetuning requires CUDA, but Accelerate resolved device={accelerator.device}."
        )
'''
    cpu_guard = '''    if accelerator.device.type not in ("cpu", "cuda"):
        raise EnvironmentError(f"Unsupported MOSS training device: {accelerator.device}")
'''
    if original.count(guard) != 1:
        raise SystemExit("Upstream device guard changed; inspect before adapting")
    adapted = original.replace(guard, cpu_guard)
    compile(adapted, str(target), "exec")
    if target.exists() and target.read_text(encoding="utf-8") != adapted:
        raise SystemExit("CPU training copy differs; inspect before replacing")
    target.write_text(adapted, encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
