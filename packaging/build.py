"""Build a double-clickable phi-guard Studio folder for this operating system.

    python packaging/build.py

Steps: build the UI (needs Node.js), run PyInstaller, smoke-test the result,
and zip it into dist/phi-guard-studio-<version>-<os>.zip.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], cwd: Path = ROOT, **kw: object) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True, **kw)  # type: ignore[call-overload]


def smoke_test(exe: Path) -> None:
    """Start the frozen app on a fixed port and check the API answers (loopback only)."""
    env = {**os.environ, "PHI_GUARD_STUDIO_TOKEN": "smoke"}
    data = ROOT / "dist" / "smoke-data"
    proc = subprocess.Popen([str(exe), "--no-browser", "--port", "8797", "--data-dir", str(data)], env=env)
    try:
        for _ in range(60):
            try:
                req = urllib.request.Request("http://127.0.0.1:8797/api/health", headers={"X-PHI-Guard-Token": "smoke"})
                with urllib.request.urlopen(req, timeout=2) as r:  # noqa: S310 - fixed loopback URL
                    print("smoke test:", r.read().decode())
                    return
            except OSError:
                time.sleep(1)
        raise SystemExit("smoke test failed: Studio did not answer")
    finally:
        proc.terminate()
        proc.wait(timeout=20)
        shutil.rmtree(data, ignore_errors=True)


def main() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from phi_guard import __version__

    if "--skip-ui" not in sys.argv:
        npm = "npm.cmd" if os.name == "nt" else "npm"
        run([npm, "ci"], cwd=ROOT / "studio-ui")
        run([npm, "run", "build"], cwd=ROOT / "studio-ui")
    run([sys.executable, "-m", "PyInstaller", "packaging/phi-guard-studio.spec", "--noconfirm",
         "--distpath", "dist", "--workpath", "build/pyinstaller"])  # fmt: skip
    folder = ROOT / "dist" / "phi-guard-studio"
    exe = folder / ("phi-guard-studio.exe" if os.name == "nt" else "phi-guard-studio")
    smoke_test(exe)
    os_name = {"Darwin": "macos", "Windows": "windows"}.get(platform.system(), "linux")
    archive = shutil.make_archive(str(ROOT / "dist" / f"phi-guard-studio-{__version__}-{os_name}"), "zip", folder.parent, folder.name)
    print("built", archive)


if __name__ == "__main__":
    main()
