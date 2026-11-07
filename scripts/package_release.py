"""Rebuild source/extension ZIPs from this checkout without build caches."""
from pathlib import Path
import argparse
import hashlib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {".git", "downloads", "work", "dist", "build", "test-results", ".cache", "__pycache__", "node_modules", ".venv", ".pytest_cache"}


def files(base):
    return sorted(path for path in base.rglob("*") if path.is_file()
                  and not any(part in EXCLUDED for part in path.relative_to(base).parts)
                  and path.suffix not in {".pyc", ".log"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installer", type=Path, help="Also hash the Windows Setup built by CI")
    args = parser.parse_args()
    destination = ROOT / "downloads"
    destination.mkdir(exist_ok=True)
    targets = [("OperaMusicDownloader-Fonte.zip", ROOT, "OperaMusicDownloader"),
               ("OperaMusicDownloader-Extensao.zip", ROOT / "extension", "extension")]
    sums = []
    for name, base, prefix in targets:
        target = destination / name
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in files(base):
                archive.write(path, Path(prefix) / path.relative_to(base))
        with zipfile.ZipFile(target) as archive:
            assert archive.testzip() is None
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        sums.append(f"{digest}  {name}\n")
        print(f"{name}: {target.stat().st_size} bytes, SHA256 {digest}")
    if args.installer:
        digest = hashlib.sha256(args.installer.read_bytes()).hexdigest()
        sums.append(f"{digest}  {args.installer.name}\n")
    (destination / "SHA256SUMS.txt").write_text("".join(sums), encoding="ascii")


if __name__ == "__main__":
    main()
