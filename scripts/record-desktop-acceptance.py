"""Record the actual Windows desktop for an explicitly prepared QA scene.

Run only after test applications cover private content. This captures the real
desktop, including native windows and cursor; no canvas or browser simulation.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time
import imageio_ffmpeg

parser = argparse.ArgumentParser()
parser.add_argument('--output', required=True, type=Path)
parser.add_argument('--seconds', type=int, default=120)
args = parser.parse_args()
if not 1 <= args.seconds <= 180:
    parser.error('seconds must be between 1 and 180')
if args.output.exists():
    parser.error('output already exists; choose a new evidence file')
args.output.parent.mkdir(parents=True, exist_ok=True)
command = [imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'warning',
           '-f', 'gdigrab', '-framerate', '15', '-draw_mouse', '1', '-i', 'desktop',
           '-t', str(args.seconds), '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
           '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '24', '-pix_fmt', 'yuv420p',
           '-movflags', '+faststart', str(args.output.resolve())]
started = time.monotonic()
process = subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW,
                           stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
print(json.dumps({'capture_pid': process.pid, 'target': 'actual_windows_desktop',
                  'output': str(args.output.resolve()), 'maximum_seconds': args.seconds}), flush=True)
_, stderr = process.communicate(timeout=args.seconds + 15)
report = {'exit_code': process.returncode, 'duration_seconds': round(time.monotonic()-started, 2),
          'output': str(args.output.resolve()), 'bytes': args.output.stat().st_size if args.output.exists() else 0,
          'command': command, 'diagnostics': stderr.decode('utf-8', errors='replace')[-2000:]}
args.output.with_suffix('.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
raise SystemExit(process.returncode)
