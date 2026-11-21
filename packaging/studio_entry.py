"""Entry point for the frozen (PyInstaller) build: double-click to start Studio."""

import sys

from phi_guard_studio.launcher import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
