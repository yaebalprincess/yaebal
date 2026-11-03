import os
import time
from pathlib import Path

_BOOT_STARTED = time.perf_counter()
try:
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")) / "SmartOrder" / "logs"
    base.mkdir(parents=True, exist_ok=True)
    with (base / "startup.log").open("a", encoding="utf-8") as fh:
        from datetime import datetime
        fh.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 0.0 ms | python-entry\n")
except Exception:
    pass

from smartorder.app import main

if __name__ == "__main__":
    raise SystemExit(main(_BOOT_STARTED))
