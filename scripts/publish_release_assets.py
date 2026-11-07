"""Verify a tested Windows build and prepare a GitHub draft release.

Run inside the dedicated release-assets workflow with its own GITHUB_TOKEN.
It never publishes a draft, reads secrets, or stores the Setup in Git history.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def gh(*arguments):
    result = subprocess.run(["gh", *map(str, arguments)], check=True, capture_output=True, text=True, encoding="utf-8")
    return result.stdout


def api(path):
    return json.loads(gh("api", path))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checksums(path):
    values = {}
    for line in path.read_text(encoding="ascii").splitlines():
        digest, name = line.split()
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or Path(name).name != name:
            raise ValueError("Arquivo de hashes inválido")
        values[name] = digest
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-directory", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("GITHUB_ACTIONS") != "true":
        parser.error("Use o workflow release-assets.yml; nenhuma credencial deve ser copiada para este script")
    tag = os.environ["RELEASE_TAG"]
    run_id = os.environ["BUILD_RUN_ID"]
    repository = os.environ["GITHUB_REPOSITORY"]
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag) or not re.fullmatch(r"\d+", run_id):
        raise ValueError("Tag ou execução inválida")
    manifest = json.loads((ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))
    provenance = json.loads((ROOT / "docs" / "evidencias" / "windows-build-provenance.json").read_text(encoding="utf-8"))
    assert manifest["version"] == provenance["version"] == tag[1:]
    assert provenance["workflowRun"].endswith("/" + run_id)
    run = api(f"repos/{repository}/actions/runs/{run_id}")
    assert run["status"] == "completed" and run["conclusion"] == "success"
    assert run["head_sha"] == provenance["buildCommit"]
    assert run["path"] == ".github/workflows/windows-build.yml"

    incoming = args.artifact_directory.resolve()
    setup = incoming / "dist" / "OperaMusicDownloader-Setup.exe"
    assert setup.stat().st_size == provenance["installerBytes"]
    assert sha256(setup) == provenance["installerSha256"]
    assert setup.read_bytes()[:2] == b"MZ"
    windows_report = incoming / "test-results" / "windows-install.json"
    report = json.loads(windows_report.read_text(encoding="utf-8"))
    assert report["platform"] == "Windows"
    assert report["selfTest"]["ok"] and report["selfTest"]["version"] == tag[1:]
    for key in ("savedMp3AndUnicodePath", "persistedAcrossNativeRestart", "savedMp4And720p", "legacyFolderMigratedAndMediaPreserved"):
        assert report["checks"][key] is True
    assert report["checks"]["windowsKnownMusic"]

    expected = checksums(ROOT / "downloads" / "SHA256SUMS.txt")
    assets = ROOT / "work" / "release-assets"
    assets.mkdir(parents=True, exist_ok=True)
    files = []
    for name in ("OperaMusicDownloader-Fonte.zip", "OperaMusicDownloader-Extensao.zip"):
        source = ROOT / "downloads" / name
        assert sha256(source) == expected[name]
        with zipfile.ZipFile(source) as zipped:
            assert zipped.testzip() is None
        target = assets / name
        shutil.copy2(source, target)
        files.append(target)
    assert sha256(setup) == expected[setup.name]
    for source, name in (
        (setup, setup.name),
        (ROOT / "downloads" / "SHA256SUMS.txt", "SHA256SUMS.txt"),
        (windows_report, "windows-install.json"),
        (incoming / "work" / "windows-build" / "dist" / "OperaMusicDownloaderHost" / "build-self-test.json", "windows-build-self-test.json"),
    ):
        target = assets / name
        shutil.copy2(source, target)
        files.append(target)

    releases = api(f"repos/{repository}/releases?per_page=100")
    release = next((item for item in releases if item["tag_name"] == tag), None)
    if release is None:
        notes = ROOT / "docs" / ("RELEASE-" + tag + ".md")
        if not notes.is_file():
            raise ValueError("Notas da versão ausentes")
        gh("release", "create", tag, "--repo", repository, "--target", os.environ["GITHUB_SHA"], "--draft", "--title", f"Opera Music Downloader {tag[1:]}", "--notes-file", notes)
    elif not release["draft"]:
        raise RuntimeError("A versão já foi publicada. Prepare uma atualização explícita; este workflow só altera rascunhos.")
    gh("release", "upload", tag, *files, "--repo", repository, "--clobber")
    release = next(item for item in api(f"repos/{repository}/releases?per_page=100") if item["tag_name"] == tag)
    assert release["draft"]
    published = {item["name"]: item for item in release["assets"]}
    for path in files:
        assert published[path.name]["size"] == path.stat().st_size
    summary = {
        "releaseId": release["id"], "tag": tag, "draft": True,
        "releaseUrl": release["html_url"], "buildRun": run_id,
        "installerSha256": sha256(setup),
        "assets": [{"name": path.name, "bytes": path.stat().st_size} for path in files],
    }
    (assets / "release-upload-report.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as output:
        output.write(f"Assets verificados enviados para o rascunho [{tag}]({release['html_url']}).\n\nPublicação final pendente. Setup SHA256: `{summary['installerSha256']}`.\n")


if __name__ == "__main__":
    main()
