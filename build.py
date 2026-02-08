"""
ETTEM Build Script - Cross-platform executable builder

Usage:
    python build.py          # Build for current platform
    python build.py --clean  # Clean build (removes previous artifacts)

Output:
    Windows: dist/ETTEM.exe
    macOS:   dist/ETTEM.app
"""

import subprocess
import sys
import platform
import shutil
from pathlib import Path


def main():
    clean = "--clean" in sys.argv

    os_name = platform.system()
    print(f"Building ETTEM for {os_name}...")

    if os_name == "Darwin":
        expected_output = "dist/ETTEM.app"
    elif os_name == "Windows":
        expected_output = "dist/ETTEM.exe"
    else:
        print(f"Unsupported platform: {os_name}")
        print("ETTEM currently supports Windows and macOS.")
        sys.exit(1)

    # Clean previous build artifacts
    if clean:
        for d in ["build", "dist"]:
            p = Path(d)
            if p.exists():
                print(f"Removing {d}/...")
                shutil.rmtree(p)

    # Run PyInstaller
    cmd = [sys.executable, "-m", "PyInstaller", "ettem.spec", "--noconfirm"]
    if clean:
        cmd.append("--clean")

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)

    if result.returncode != 0:
        print("Build failed!")
        sys.exit(1)

    if Path(expected_output).exists():
        print(f"\nBuild successful: {expected_output}")
    else:
        print(f"\nWarning: Expected output not found at {expected_output}")
        print("Check the dist/ directory for build output.")


if __name__ == "__main__":
    main()
