"""Runs `adb` with fixed arguments to open/close the USB tunnel (DESIGN §7.2–7.3).

Nothing from a request is ever passed to the command line: only the configured ports and
a device serial that adb itself reported.
"""

import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from learnmarks.core.config import Settings
from learnmarks.core.errors import AppError

TUNNEL_MINUTES = 10
_timer: threading.Timer | None = None
_lock = threading.Lock()


@dataclass
class UsbStatus:
    adb_found: bool
    devices: list[dict]  # [{serial, state, model}]
    tunnel_open: bool
    message: str


def find_adb(settings: Settings) -> str | None:
    for candidate in (settings.adb_path, shutil.which("adb"), str(Path.home() / "Library/Android/sdk/platform-tools/adb")):
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def _run(adb: str, *args: str) -> str:
    try:
        r = subprocess.run([adb, *args], capture_output=True, text=True, timeout=10, check=False)
    except subprocess.TimeoutExpired as e:
        raise AppError(504, "adb didn't answer", "Unplug and re-plug the phone, then try again.") from e
    if r.returncode != 0:
        raise AppError(502, "adb failed", (r.stderr or r.stdout).strip()[:300])
    return r.stdout


def _devices(adb: str) -> list[dict]:
    out = []
    for line in _run(adb, "devices", "-l").splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            model = next((p.split(":", 1)[1] for p in parts[2:] if p.startswith("model:")), None)
            out.append({"serial": parts[0], "state": parts[1], "model": model})
    return out


def _tunnel_open(adb: str, serial: str, settings: Settings) -> bool:
    try:
        return f"tcp:{settings.sync_port}" in _run(adb, "-s", serial, "reverse", "--list")
    except AppError:
        return False


def status(settings: Settings) -> UsbStatus:
    adb = find_adb(settings)
    if adb is None:
        return UsbStatus(False, [], False, "adb not found. Install it with: brew install android-platform-tools")
    devices = _devices(adb)
    ready = [d for d in devices if d["state"] == "device"]
    if not devices:
        msg = "No phone found. Connect the cable and turn on USB debugging."
    elif any(d["state"] == "unauthorized" for d in devices):
        msg = "On the phone, tap Allow on the “Allow USB debugging?” prompt."
    elif len(ready) > 1:
        msg = "More than one device is connected. Leave only the phone plugged in."
    else:
        msg = "Phone connected."
    tunnel = len(ready) == 1 and _tunnel_open(adb, ready[0]["serial"], settings)
    return UsbStatus(True, devices, tunnel, msg)


def start(settings: Settings) -> UsbStatus:
    global _timer
    adb = find_adb(settings)
    if adb is None:
        raise AppError(503, "adb not found", "Install it with: brew install android-platform-tools")
    ready = [d for d in _devices(adb) if d["state"] == "device"]
    if len(ready) != 1:
        raise AppError(409, "Phone not ready", status(settings).message)
    serial = ready[0]["serial"]
    _run(adb, "-s", serial, "reverse", f"tcp:{settings.sync_port}", f"tcp:{settings.port}")
    with _lock:
        if _timer:
            _timer.cancel()
        _timer = threading.Timer(TUNNEL_MINUTES * 60, lambda: _safe_stop(settings))
        _timer.daemon = True
        _timer.start()
    return status(settings)


def stop(settings: Settings) -> UsbStatus:
    global _timer
    with _lock:
        if _timer:
            _timer.cancel()
            _timer = None
    adb = find_adb(settings)
    if adb is not None:
        for d in _devices(adb):
            if d["state"] == "device":
                try:
                    _run(adb, "-s", d["serial"], "reverse", "--remove", f"tcp:{settings.sync_port}")
                except AppError:
                    pass  # no tunnel to remove
    return status(settings)


def _safe_stop(settings: Settings) -> None:
    try:
        stop(settings)
    except AppError:
        pass
