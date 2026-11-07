"""Maintenance utility called invisibly by Inno Setup, never by the extension.

The public Setup contains no yt-dlp, Deno or FFmpeg binaries. Inno Setup obtains
those directly from pinned upstream HTTPS URLs with native download progress;
this utility verifies the cached bytes again and extracts only known files.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import traceback

from fetch_dependencies import ROOT, install_from_cache

MEDIA_SUFFIXES = {".mp3", ".mp4", ".m4a", ".opus", ".wav", ".flac", ".ogg", ".webm", ".mkv", ".avi", ".aac"}
TOOL_FILES = {"yt-dlp.exe", "ffmpeg.exe", "ffprobe.exe", "deno.exe"}


def remove_installed_tools(destination: Path) -> None:
    """Remove only files written by this utility; never scan/delete user media."""
    record = destination / ".installed-dependencies.json"
    if not record.is_file():
        paths = list(TOOL_FILES)
    else:
        paths = json.loads(record.read_text(encoding="utf-8"))
    if not isinstance(paths, list) or len(paths) > 10000:
        raise ValueError("Registro de arquivos de dependências inválido.")
    for relative in paths:
        if not isinstance(relative, str) or "\\" in relative or ":" in relative:
            continue
        name = PurePosixPath(relative)
        if name.is_absolute() or ".." in name.parts or name.suffix.lower() in MEDIA_SUFFIXES:
            continue
        if not (relative in TOOL_FILES or name.parts and name.parts[0] == "licenses"):
            continue
        target = destination.joinpath(*name.parts)
        if not target.resolve().is_relative_to(destination.resolve()):
            continue
        target.unlink(missing_ok=True)
        parent = target.parent
        while parent != destination:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
    record.unlink(missing_ok=True)
    (destination / ".installed-dependencies.json.tmp").unlink(missing_ok=True)
    try:
        destination.rmdir()
    except OSError:
        pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--remove", action="store_true")
    parser.add_argument("--self-test-host", type=Path)
    args = parser.parse_args(argv)
    args.log.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open("a" if args.self_test_host else "w", encoding="utf-8") as output, redirect_stdout(output), redirect_stderr(output):
        try:
            if args.self_test_host:
                result = subprocess.run([str(args.self_test_host), "--self-test"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                print(result.stdout.decode("utf-8", errors="replace"))
                print(result.stderr.decode("utf-8", errors="replace"))
                return result.returncode
            elif args.remove:
                remove_installed_tools(args.destination)
            else:
                if args.cache is None:
                    raise ValueError("Pasta temporária dos downloads não informada.")
                lock = json.loads((ROOT / "installer" / "dependencies.lock.json").read_text(encoding="utf-8"))
                install_from_cache(lock, args.destination, args.cache, offline=True)
            print("Concluído.")
            return 0
        except Exception:
            traceback.print_exc()
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
