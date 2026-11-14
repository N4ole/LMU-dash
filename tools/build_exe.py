#!/usr/bin/env python3
"""Construit dist/LMU-Dash.exe (PyInstaller, un seul fichier). Utilisé par build_exe.bat et par la CI de release.

python -m pip install -r requirements-build.txt
python tools/build_exe.py
"""

import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# Modules de l'application importés dynamiquement ou chargés via sys.path : on les déclare explicitement.
HIDDEN = [
    "readers",
    "strategy",
    "endurance",
    "store",
    "flags",
    "shared",
    "updates",
    "version",
    "pyLMUSharedMemory.lmu_data",
]


def main() -> int:
    sep = ";" if os.name == "nt" else ":"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        "LMU-Dash",
        "--add-data",
        f"web{sep}web",
    ]
    for mod in HIDDEN:
        cmd += ["--hidden-import", mod]
    cmd.append("server.py")
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main())
