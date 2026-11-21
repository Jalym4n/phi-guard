"""Build a double-clickable phi-guard Studio folder for this operating system.

    python packaging/build.py [--skip-ui] [--bundle-tesseract DIR]

Steps: build the UI (needs Node.js), run PyInstaller, optionally copy a
Tesseract installation into the app (so scans can be read without installing
anything else), smoke-test the result, and zip it into
dist/phi-guard-studio-<version>-<os>.zip.

``--bundle-tesseract DIR`` copies DIR (for example ``C:\\Program Files\\Tesseract-OCR``
on Windows) to ``phi-guard-studio/tesseract/``, where Studio looks first.
"""

from __future__ import annotations

import json
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


def _post_scan(port: int) -> dict[str, object]:
    """Upload a synthetic scanned page to the frozen app and return the parsed response."""
    import io

    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("L", (1700, 600), 255)
    ImageDraw.Draw(img).text((100, 100), "Patient: Eleanor Whitfield", fill=0, font=ImageFont.load_default(size=60))
    buf = io.BytesIO()
    img.save(buf, "PDF", resolution=200)
    boundary = "phiguardsmoke"
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="scan.pdf"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
        ).encode()
        + buf.getvalue()
        + f"\r\n--{boundary}--\r\n".encode()
    )
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/extract",
        data=body,
        headers={"X-PHI-Guard-Token": "smoke", "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:  # fixed loopback URL only
            return dict(json.loads(r.read()))
    except urllib.error.HTTPError as exc:
        return dict(json.loads(exc.read()))


def smoke_test(exe: Path) -> None:
    """Start the frozen app on a fixed port and check the API answers (loopback only)."""
    env = {**os.environ, "PHI_GUARD_STUDIO_TOKEN": "smoke"}
    data = ROOT / "dist" / "smoke-data"
    proc = subprocess.Popen([str(exe), "--no-browser", "--port", "8797", "--data-dir", str(data)], env=env)
    try:
        for _ in range(60):
            try:
                req = urllib.request.Request("http://127.0.0.1:8797/api/health", headers={"X-PHI-Guard-Token": "smoke"})
                with urllib.request.urlopen(req, timeout=2) as r:  # fixed loopback URL only
                    health = json.loads(r.read())
                    print("smoke test:", health)
                break
            except OSError:
                time.sleep(1)
        else:
            raise SystemExit("smoke test failed: Studio did not answer")
        # Scanned documents: proves Pillow, PDFium and (if present) Tesseract work inside the build.
        result = _post_scan(8797)
        if health.get("ocr", {}).get("available"):
            if "Whitfield" not in str(result.get("text", "")):
                raise SystemExit(f"smoke test failed: OCR did not read the scanned page: {result}")
            print("smoke test: OCR read a scanned page")
        else:
            if "add-on" not in str(result.get("error", "")):
                raise SystemExit(f"smoke test failed: unexpected response for a scan without Tesseract: {result}")
            print("smoke test: no Tesseract in this build; scans get the install message")
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
    if "--bundle-tesseract" in sys.argv:
        source = Path(sys.argv[sys.argv.index("--bundle-tesseract") + 1])
        target = folder / "tesseract"
        shutil.copytree(source, target, dirs_exist_ok=True)
        # Tesseract is Apache-2.0 licensed: keep its licence next to it.
        (target / "BUNDLED-README.txt").write_text(
            "Tesseract OCR (https://github.com/tesseract-ocr/tesseract), Apache License 2.0.\n"
            "Bundled so phi-guard Studio can read scanned documents on this computer.\n",
            encoding="utf-8",
        )
        print("bundled Tesseract from", source)
    smoke_test(exe)
    os_name = {"Darwin": "macos", "Windows": "windows"}.get(platform.system(), "linux")
    base = ROOT / "dist" / f"phi-guard-studio-{__version__}-{os_name}"
    archive = shutil.make_archive(str(base), "zip", folder.parent, folder.name)
    print("built", archive)


if __name__ == "__main__":
    main()
