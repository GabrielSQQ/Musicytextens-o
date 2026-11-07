"""Download only pinned upstream Windows tools and verify bytes before extraction.

No release discovery or automatic lock modification is performed at build time.
Run on any platform; the downloaded executable tools are Windows x64 only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import ssl
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
MAX_DOWNLOAD = 600 * 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(artifact: dict, cache: Path, *, offline: bool = False) -> Path:
    url = urllib.parse.urlsplit(artifact["url"])
    approved_binary = url.hostname == "github.com" and url.path.startswith(("/yt-dlp/yt-dlp/releases/download/", "/denoland/deno/releases/download/", "/BtbN/FFmpeg-Builds/releases/download/"))
    approved_license = url.hostname == "raw.githubusercontent.com" and artifact["kind"] == "license" and url.path.startswith(("/yt-dlp/yt-dlp/", "/denoland/deno/"))
    if url.scheme != "https" or not (approved_binary or approved_license):
        raise ValueError("URL de dependência fora das fontes aprovadas")
    expected = artifact["sha256"]
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError("SHA256 inválido no lock")
    target = cache / Path(artifact["filename"]).name
    if target.exists() and sha256(target) == expected:
        return target
    if offline:
        raise ValueError(f"Arquivo verificado ausente ou corrompido: {artifact['filename']}. Volte e tente baixar novamente.")
    target.unlink(missing_ok=True)
    temporary = target.with_suffix(target.suffix + ".partial")
    try:
        request = urllib.request.Request(artifact["url"], headers={"User-Agent": "OperaMusicDownloader-build/1.0"})
        with urllib.request.urlopen(request, timeout=120, context=ssl.create_default_context()) as response, temporary.open("wb") as output:
            if urllib.parse.urlsplit(response.url).scheme != "https":
                raise ValueError("Redirecionamento sem TLS recusado")
            total = 0
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                total += len(chunk)
                if total > MAX_DOWNLOAD:
                    raise ValueError("Dependência excede tamanho permitido")
                output.write(chunk)
        if sha256(temporary) != expected:
            raise ValueError(f"SHA256 divergente: {artifact['name']}. Arquivo rejeitado.")
        temporary.replace(target)
        return target
    finally:
        temporary.unlink(missing_ok=True)


def extract_tool(archive: Path, artifact: dict, tools: Path, licenses: Path) -> list[Path]:
    if artifact["kind"] in {"file", "license"}:
        destination = licenses if artifact["kind"] == "license" else tools
        target = destination / Path(artifact["target"]).name
        shutil.copy2(archive, target)
        return [target]
    written = []
    with zipfile.ZipFile(archive) as zipped:
        # Copy only known binaries; never extract an arbitrary upstream path.
        for suffix, target in artifact["members"].items():
            matches = [entry for entry in zipped.infolist() if not entry.is_dir() and (entry.filename == suffix or entry.filename.endswith("/" + suffix))]
            if len(matches) != 1 or matches[0].file_size > MAX_DOWNLOAD:
                raise ValueError(f"Conteúdo inesperado no ZIP de {artifact['name']}: {suffix}")
            with zipped.open(matches[0]) as source, (tools / Path(target).name).open("wb") as destination:
                shutil.copyfileobj(source, destination)
            written.append(tools / Path(target).name)
        for entry in zipped.infolist():
            name = PurePosixPath(entry.filename)
            if entry.is_dir() or entry.file_size > 8 * 1024 * 1024:
                continue
            if "\\" in entry.filename or ":" in entry.filename or any(part in {"..", ""} for part in name.parts) or name.is_absolute():
                raise ValueError("Caminho inseguro no ZIP")
            if "license" in entry.filename.lower() or name.name.lower().startswith(("copying", "readme")):
                # Preserve license hierarchy without permitting path traversal.
                dest = licenses / artifact["name"] / Path(*name.parts)
                if not dest.resolve().is_relative_to(licenses.resolve()):
                    raise ValueError("Caminho de licença fora da pasta permitida")
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zipped.open(entry) as source, dest.open("wb") as output:
                    shutil.copyfileobj(source, output)
                written.append(dest)
    return written


def install_from_cache(lock: dict, destination: Path, cache: Path, *, offline=False) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    # Verify/extract every artifact before replacing any installed executable.
    # Record owned paths before the final copy so interrupted installation can
    # still be removed safely without scanning user files.
    with tempfile.TemporaryDirectory(prefix=".omd-tools-", dir=destination.parent) as temporary:
        staging = Path(temporary)
        licenses = staging / "licenses"
        licenses.mkdir()
        written = []
        for item in lock["artifacts"]:
            print(f"Verificando {item['name']} {item['version']}...", flush=True)
            archive = download(item, cache, offline=offline)
            written.extend(extract_tool(archive, item, staging, licenses))
        lock_path = licenses / "dependencies.lock.json"
        lock_path.write_text(json.dumps(lock, ensure_ascii=True, indent=2), encoding="utf-8")
        written.append(lock_path)
        names = [path.relative_to(staging).as_posix() for path in written]
        record = destination / ".installed-dependencies.json"
        try:
            previous = json.loads(record.read_text(encoding="utf-8"))
            if isinstance(previous, list):
                names = list(dict.fromkeys([item for item in previous if isinstance(item, str)] + names))
        except (OSError, ValueError):
            pass
        pending_record = destination / ".installed-dependencies.json.tmp"
        pending_record.write_text(json.dumps(names, ensure_ascii=True, indent=2), encoding="utf-8")
        pending_record.replace(record)
        final_paths = []
        for source in written:
            target = destination / source.relative_to(staging)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            final_paths.append(target)
    return final_paths + [record]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=ROOT / "work" / "windows-tools")
    parser.add_argument("--cache", type=Path, default=ROOT / "work" / "downloads")
    parser.add_argument("--verify-lock", action="store_true", help="Check lock structure only; no network")
    arguments = parser.parse_args()
    lock = json.loads((ROOT / "installer" / "dependencies.lock.json").read_text(encoding="utf-8"))
    if lock["schema"] != 1 or lock["platform"] != "windows-x86_64":
        raise ValueError("Lock incompatível")
    if arguments.verify_lock:
        for item in lock["artifacts"]:
            if len(item["sha256"]) != 64 or "/latest/" in item["url"]:
                raise ValueError("Dependência não fixada")
        print("Lock: versões explícitas e SHA256 presentes.")
        return 0
    install_from_cache(lock, arguments.destination, arguments.cache)
    print("Dependências verificadas e preparadas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
