"""Build the Windows x64 native host and per-user Inno Setup installer.

Developer tool only. End users run the resulting Setup.exe and need no Python.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work" / "windows-build"


def run(arguments: list[str], **kwargs) -> subprocess.CompletedProcess:
    print("Executando:", " ".join(map(str, arguments)), flush=True)
    return subprocess.run([str(x) for x in arguments], check=True, cwd=ROOT, **kwargs)


def stable_extension_id(public_key: str) -> str:
    """Chromium extension IDs encode the first 128 bits of the SPKI hash."""
    digest = hashlib.sha256(base64.b64decode(public_key, validate=True)).hexdigest()[:32]
    return "".join(chr(ord("a") + int(character, 16)) for character in digest)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iscc", type=Path, help="Path to official Inno Setup 6 ISCC.exe")
    args = parser.parse_args()
    if sys.platform != "win32" or platform.machine().lower() not in {"amd64", "x86_64"}:
        parser.error("A compilação precisa ser executada em Windows x64.")
    if sys.version_info[:2] != (3, 12):
        parser.error("Utilize CPython 3.12 x64 com suporte a Tcl/Tk.")
    extension_id = (ROOT / "extension" / "extension-id.txt").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[a-p]{32}", extension_id):
        raise ValueError("ID da extensão inválido")
    manifest = json.loads((ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))
    if not manifest.get("key"):
        raise ValueError("A chave pública estável não foi incluída no manifesto da extensão")
    if stable_extension_id(manifest["key"]) != extension_id:
        raise ValueError("O ID de extensão não corresponde à chave pública do manifesto")
    iscc = args.iscc or Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe"
    if not iscc.is_file():
        found = shutil.which("ISCC.exe")
        if not found:
            raise RuntimeError("Instale Inno Setup 6 do site oficial ou informe --iscc.")
        iscc = Path(found)
    WORK.mkdir(parents=True, exist_ok=True)
    venv_path = WORK / "venv"
    if not (venv_path / "Scripts" / "python.exe").is_file():
        venv.EnvBuilder(with_pip=True).create(venv_path)
    python = venv_path / "Scripts" / "python.exe"
    run([python, "-m", "pip", "install", "--require-hashes", "--only-binary=:all:", "-r", ROOT / "installer" / "build-requirements.lock.txt"])
    tools = ROOT / "work" / "windows-tools"
    run([python, ROOT / "scripts" / "fetch_dependencies.py", "--destination", tools])
    build_dir = WORK / "pyinstaller"
    dist_dir = WORK / "dist"
    run([python, "-m", "PyInstaller", "--noconfirm", "--clean", "--console", "--onedir", "--name", "OperaMusicDownloaderHost", "--distpath", dist_dir, "--workpath", build_dir, "--specpath", WORK, "--hidden-import", "tkinter", "--hidden-import", "tkinter.filedialog", ROOT / "native-app" / "main.py"])
    stage = dist_dir / "OperaMusicDownloaderHost"
    shutil.copytree(tools, stage / "tools", dirs_exist_ok=True)
    shutil.copytree(ROOT / "extension", stage / "extension", dirs_exist_ok=True)
    shutil.copy2(ROOT / "extension" / "extension-id.txt", stage / "extension-id.txt")
    shutil.copy2(ROOT / "installer" / "LEIA-ME.html", stage / "LEIA-ME.html")
    shutil.copy2(ROOT / "installer" / "THIRD-PARTY-NOTICES.txt", stage / "THIRD-PARTY-NOTICES.txt")
    if (ROOT / "LICENSE").is_file():
        shutil.copy2(ROOT / "LICENSE", stage / "LICENSE.txt")
    licenses = stage / "tools" / "licenses"
    base_python = Path(sys.base_prefix)
    for license_file in (base_python / "LICENSE.txt", base_python / "LICENSE"):
        if license_file.is_file():
            shutil.copy2(license_file, licenses / "Python-LICENSE.txt")
            break
    # Preserve the licenses of the Python packaging components/bootloader too.
    site_packages = venv_path / "Lib" / "site-packages"
    for pattern in ("**/LICENSE*", "**/COPYING*"):
        for source in site_packages.glob(pattern):
            if source.is_file() and source.stat().st_size < 2 * 1024 * 1024:
                target = licenses / "python-packages" / source.relative_to(site_packages)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
    host = stage / "OperaMusicDownloaderHost.exe"
    result = run([host, "--self-test"], capture_output=True, text=True, encoding="utf-8")
    report = json.loads(result.stdout)
    (stage / "build-self-test.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    # The native test must return a nonzero exit code when a required tool fails.
    print("Self-test do executável concluído.", flush=True)
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    run([iscc, f"/DExtensionId={extension_id}", f"/DStageDir={stage}", f"/O{output}", ROOT / "installer" / "OperaMusicDownloader.iss"])
    setup = output / "OperaMusicDownloader-Setup.exe"
    if not setup.is_file():
        raise RuntimeError("O compilador não gerou o instalador esperado")
    digest = hashlib.sha256(setup.read_bytes()).hexdigest()
    (output / "SHA256SUMS.txt").write_text(f"{digest}  {setup.name}\n", encoding="ascii")
    print(f"Instalador criado: {setup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
