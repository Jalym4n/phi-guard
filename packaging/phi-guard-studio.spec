# PyInstaller spec: one-folder build of phi-guard Studio.
#   pyinstaller packaging/phi-guard-studio.spec --noconfirm
# Build the UI first (make studio-ui) so phi_guard_studio/static is current.
# The optional spaCy NER extra is deliberately excluded to keep the download small.
# Pillow and pypdfium2 are included for reading scans; the Tesseract program itself is copied in by
# packaging/build.py --bundle-tesseract (Windows release builds) or installed separately.

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

datas = collect_data_files("phi_guard_studio", includes=["static/**/*"])
binaries = []
# PDFium (renders scanned PDF pages for OCR) ships as a native library inside pypdfium2_raw.
for pkg in ("pypdfium2", "pypdfium2_raw"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
hiddenimports = (
    collect_submodules("uvicorn")
    + collect_submodules("keyring.backends")
    + ["phi_guard_studio.app", "multipart", "python_multipart", "PIL.TiffImagePlugin", "PIL.PngImagePlugin",
       "PIL.JpegImagePlugin", "PIL.PdfImagePlugin"]
)

a = Analysis(
    ["studio_entry.py"],
    pathex=["../src"],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
    excludes=[
        "spacy", "thinc", "torch", "matplotlib", "presidio_analyzer", "faker", "tkinter", "pytest",
        "numpy", "fontTools", "reportlab", "scipy", "pandas", "IPython", "yaml",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="phi-guard-studio",
    console=True,  # keeps a small window open that shows the address and lets the user stop Studio
    icon=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="phi-guard-studio")
app = BUNDLE(coll, name="phi-guard Studio.app", bundle_identifier="org.phiguard.studio") if __import__("sys").platform == "darwin" else None
