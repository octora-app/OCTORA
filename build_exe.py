#!/usr/bin/env python3
"""Build a Windows .exe for OCTORA with PyInstaller.

IMPORTANT: PyInstaller cannot cross-compile. Run this script ON A WINDOWS PC
with Python 3.10+ installed. See README.md -> "Building the Windows EXE".

Usage (on Windows):
    pip install -r requirements.txt
    pip install pyinstaller
    python build_exe.py --onedir                 # dist/OCTORA/  (recommended)
    python build_exe.py --onefile                # dist/OCTORA.exe (single file)
    python build_exe.py --onedir --obfuscate     # + PyArmor obfuscation (if installed)

Anti-crack notes: the license system itself is cryptographic (RSA-signed keys,
HWID binding verified on every launch, server-side revocation) — keys cannot
be forged or shared between PCs. --obfuscate additionally scrambles the
shipped Python bytecode so the checks are much harder to locate and patch out.
No desktop app is literally uncrackable, but this is the strongest practical
setup for a Python product.
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP_NAME = "OCTORA"


def check():
    if os.name != "nt":
        print("WARNING: you are not on Windows. PyInstaller builds for the OS it runs on,")
        print("so this will produce a Linux/macOS binary, NOT a Windows .exe.")
        print("Copy this folder to a Windows PC and run build_exe.py there.\n")
        ans = input("Continue anyway? [y/N] ").strip().lower()
        if ans != "y":
            sys.exit(1)
    if shutil.which("pyinstaller") is None and not _has_pyinstaller():
        print("ERROR: PyInstaller not installed. Run:  pip install pyinstaller")
        sys.exit(1)


def _has_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
        return True
    except ImportError:
        return False


def build(mode: str, obfuscate: bool = False):
    src = HERE
    if obfuscate:
        obf = _obfuscate_copy(HERE)
        if obf is not None:
            src = obf
        else:
            print("Continuing WITHOUT obfuscation.")
    sep = ";" if os.name == "nt" else ":"
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--name", APP_NAME,
        "--windowed",
        f"--icon={src / 'assets' / 'icon.ico'}",
        f"--add-data={src / 'assets'}{sep}assets",
        # UI artwork referenced as resource_path("octora/assets/...") — without
        # this the frozen app ships without logos, backgrounds and the QR code.
        f"--add-data={src / 'octora' / 'assets'}{sep}octora/assets",
        # seller OAuth credentials (fill octora/seller_config.json BEFORE building!)
        f"--add-data={src / 'octora' / 'seller_config.json'}{sep}octora",
        "--hidden-import=PyQt6.QtWidgets",
        "--hidden-import=PyQt6.QtCore",
        "--hidden-import=PyQt6.QtGui",
        "--collect-submodules=matplotlib",
        "--exclude-module=tkinter",
    ]
    if mode == "onefile":
        cmd.append("--onefile")
    # keep the license + platform plugin packages importable when frozen
    cmd += ["--hidden-import=octora.platforms.youtube"]
    cmd.append(str(src / "main.py"))
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, cwd=src, check=True)
    out = src / "dist" / (f"{APP_NAME}.exe" if mode == "onefile" else APP_NAME)
    print(f"\nBuild complete: {out}")
    if mode == "onedir":
        print("Ship the whole OCTORA folder, or wrap it with installer.iss (Inno Setup).")


def _obfuscate_copy(root: Path) -> Path | None:
    """Best-effort PyArmor obfuscation on a COPY of the source tree.

    Returns the copy's path, or None when pyarmor is unavailable / failed
    (the caller then falls back to a plain build — never fail the build
    because of obfuscation).
    """
    if shutil.which("pyarmor") is None:
        print("pyarmor not found — skipping obfuscation "
              "(pip install pyarmor for harder-to-crack builds).")
        return None
    try:
        work = root / "build" / "obf-src"
        if work.exists():
            shutil.rmtree(work)
        shutil.copytree(root, work,
                        ignore=shutil.ignore_patterns("build", "dist", "__pycache__",
                                                     "*.pyc", ".git"))
        print("Obfuscating Python sources with PyArmor…")
        obf_out = work / "octora_obf"
        subprocess.run(
            [sys.executable, "-m", "pyarmor", "gen",
             "-O", str(obf_out), "-r", str(work / "octora")],
            check=True, capture_output=True, text=True, timeout=600)
        shutil.rmtree(work / "octora")
        shutil.move(str(obf_out), str(work / "octora"))
        print("Obfuscation done.")
        return work
    except Exception as e:  # noqa: BLE001
        print(f"Obfuscation failed ({e}) — building without it.")
        return None


def main():
    ap = argparse.ArgumentParser(description="Build OCTORA Windows executable")
    ap.add_argument("--onedir", action="store_true", help="one-folder bundle (default)")
    ap.add_argument("--onefile", action="store_true", help="single .exe file")
    ap.add_argument("--obfuscate", action="store_true",
                    help="obfuscate sources with PyArmor first (best-effort)")
    args = ap.parse_args()
    mode = "onefile" if args.onefile else "onedir"
    check()
    build(mode, obfuscate=args.obfuscate)


if __name__ == "__main__":
    main()
