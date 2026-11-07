"""Run local checks without requiring pytest. Run from the project directory."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(args: list[str]) -> None:
    print("\n> " + " ".join(args), flush=True)
    subprocess.run(args, cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", action="store_true", help="Also run Playwright fixtures; see docs/TESTES.md")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "extension/manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 3
    assert "nativeMessaging" in manifest["permissions"]
    assert not manifest.get("externally_connectable")
    assert not any(p in manifest.get("permissions", []) for p in ("cookies", "webRequest", "debugger"))
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"])
    node = shutil.which("node")
    if node:
        for script in sorted((ROOT / "extension").glob("*.js")):
            run([node, "--check", str(script)])
        for test in sorted((ROOT / "tests").glob("test_*.mjs")):
            run([node, "--test", str(test)])
    else:
        print("Node.js ausente: verificação JavaScript não executada.")
    if args.browser:
        run([sys.executable, "tests/browser_test.py"])
    print("\nVerificações solicitadas concluídas.")


if __name__ == "__main__":
    main()
