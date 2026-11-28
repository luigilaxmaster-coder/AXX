"""Source checkout entry point; the packaged backend exposes the same adapter."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.connect.subscriptions import main

if __name__ == '__main__':
    raise SystemExit(main())
