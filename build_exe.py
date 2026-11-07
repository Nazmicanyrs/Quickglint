"""Automated build script for packaging Quickglint into a standalone Windows executable."""

import os
import subprocess
import sys
from pathlib import Path


def build():
    print("=" * 60)
    print(" Building Quickglint Standalone Windows Executable (.exe)")
    print("=" * 60)

    project_dir = Path(__file__).resolve().parent
    spec_file = project_dir / "quickglint.spec"
    if not spec_file.exists():
        spec_file = project_dir / "Quickglint.spec"

    if not spec_file.exists():
        print(f"Error: Spec file {spec_file} not found!", file=sys.stderr)
        sys.exit(1)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        str(spec_file),
    ]

    print(f"Running command: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(project_dir))

    if result.returncode == 0:
        dist_dir = project_dir / "dist" / "Quickglint"
        dist_exe = dist_dir / "Quickglint.exe" if dist_dir.exists() else project_dir / "dist" / "Quickglint.exe"
        print("\n" + "=" * 60)
        print(" [SUCCESS] Quickglint Build Succeeded with High-Performance Startup!")
        print(f" Output Folder: {dist_dir}")
        print(f" Output Executable: {dist_exe}")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print(f" [FAILED] Build Failed with code: {result.returncode}")
        print("=" * 60)
        sys.exit(result.returncode)


if __name__ == "__main__":
    build()

