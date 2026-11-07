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
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MAX_DOWNLOAD = 600 * 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(artifact: dict, cache: Path) -> Path:
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


def extract_tool(archive: Path, artifact: dict, tools: Path, licenses: Path) -> None:
    if artifact["kind"] in {"file", "license"}:
        destination = licenses if artifact["kind"] == "license" else tools
        shutil.copy2(archive, destination / Path(artifact["target"]).name)
        return
    with zipfile.ZipFile(archive) as zipped:
        # Copy only known binaries; never extract an arbitrary upstream path.
        for suffix, target in artifact["members"].items():
            matches = [entry for entry in zipped.infolist() if not entry.is_dir() and (entry.filename == suffix or entry.filename.endswith("/" + suffix))]
            if len(matches) != 1 or matches[0].file_size > MAX_DOWNLOAD:
                raise ValueError(f"Conteúdo inesperado no ZIP de {artifact['name']}: {suffix}")
            with zipped.open(matches[0]) as source, (tools / Path(target).name).open("wb") as destination:
                shutil.copyfileobj(source, destination)
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
    arguments.cache.mkdir(parents=True, exist_ok=True)
    arguments.destination.mkdir(parents=True, exist_ok=True)
    licenses = arguments.destination / "licenses"
    licenses.mkdir(exist_ok=True)
    for item in lock["artifacts"]:
        print(f"Verificando {item['name']} {item['version']}...")
        archive = download(item, arguments.cache)
        extract_tool(archive, item, arguments.destination, licenses)
    shutil.copy2(ROOT / "installer" / "dependencies.lock.json", licenses / "dependencies.lock.json")
    print("Dependências verificadas e preparadas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
