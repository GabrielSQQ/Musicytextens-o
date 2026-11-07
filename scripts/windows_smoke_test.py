"""Exercise the installed Windows host, without requiring Opera or YouTube."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import queue
import struct
import subprocess
import tempfile
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "chrome-extension://" + (ROOT / "extension" / "extension-id.txt").read_text().strip() + "/"


def music_known_folder() -> Path:
    class GUID(ctypes.Structure):
        _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]
    identifier = GUID.from_buffer_copy(uuid.UUID("4BD8D571-6D19-48D3-BE97-422220080E43").bytes_le)
    value = ctypes.c_void_p()
    shell = ctypes.WinDLL("shell32")
    shell.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
    shell.SHGetKnownFolderPath.restype = ctypes.c_long
    result = shell.SHGetKnownFolderPath(ctypes.byref(identifier), 0, None, ctypes.byref(value))
    if result != 0 or not value.value:
        raise RuntimeError("A API Known Folder não retornou a pasta Músicas")
    try:
        return Path(ctypes.wstring_at(value))
    finally:
        free = ctypes.WinDLL("ole32").CoTaskMemFree
        free.argtypes = [ctypes.c_void_p]
        free(value)


class NativeHost:
    def __init__(self, executable: Path, state: Path):
        self.process = subprocess.Popen([str(executable), ORIGIN, "--state-dir", str(state)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
        self.messages = queue.Queue()

        def read():
            try:
                while True:
                    header = self.process.stdout.read(4)
                    if not header:
                        break
                    if len(header) != 4:
                        raise RuntimeError("Cabeçalho nativo truncado")
                    length = struct.unpack("<I", header)[0]
                    if length > 1024 * 1024:
                        raise RuntimeError("Mensagem nativa excedeu o limite")
                    self.messages.put(json.loads(self.process.stdout.read(length)))
            except Exception as error:
                self.messages.put(error)
            finally:
                self.messages.put(RuntimeError("O aplicativo encerrou a comunicação"))
        threading.Thread(target=read, daemon=True).start()

    def request(self, command, payload=None):
        request_id = str(uuid.uuid4())
        content = json.dumps({"id": request_id, "type": command, "payload": payload or {}}, ensure_ascii=True).encode()
        self.process.stdin.write(struct.pack("<I", len(content)) + content)
        self.process.stdin.flush()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            response = self.messages.get(timeout=max(0.1, deadline - time.monotonic()))
            if isinstance(response, Exception):
                raise response
            if response.get("id") == request_id:
                if not response.get("ok"):
                    raise RuntimeError(response.get("error"))
                return response["result"]
        raise TimeoutError("O aplicativo não respondeu")

    def close(self):
        self.process.stdin.close()
        try:
            code = self.process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.process.kill()
            raise RuntimeError("O host não encerrou após fechar o pipe")
        if code:
            raise RuntimeError(self.process.stderr.read().decode(errors="replace"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("Este teste precisa de Windows")
    conversion = subprocess.run([str(args.host), "--self-test"], capture_output=True, text=True, encoding="utf-8", check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    report = {"platform": "Windows", "selfTest": json.loads(conversion.stdout), "checks": {}}
    assert report["selfTest"]["ok"] and report["selfTest"]["version"] == "1.1.0"
    with tempfile.TemporaryDirectory(prefix="OMD teste acentuação ") as temporary:
        # Windows TEMP can use an 8.3 username alias. The host deliberately
        # canonicalizes destination paths before persisting them.
        base = Path(temporary).resolve()
        destination = base / "Músicas com espaços e acentos"
        destination.mkdir()
        marker = destination / "não excluir.mp3"
        marker.write_bytes(b"authorized local preservation fixture")
        state = base / "state"
        music = music_known_folder()
        made_music = not music.exists()
        if made_music:
            music.mkdir(parents=True)
        try:
            native = NativeHost(args.host, state)
            try:
                ping = native.request("ping")
                assert ping["version"] == "1.1.0" and ping["protocolVersion"] == 2 and ping["capabilities"]["oneClickDownloads"]
                settings = native.request("get_state")["settings"]
                assert Path(settings["defaultFolder"]) == music
                report["checks"]["windowsKnownMusic"] = str(music)
                requested = {"defaultFolder": str(destination), "defaultFormat": "mp3", "mp3Quality": 320, "mp4Quality": 720, "authorizedDownloads": True}
                settings = native.request("settings", requested)
                for key, value in requested.items():
                    assert settings[key] == value, f"Preference {key}: {settings[key]!r} != {value!r}"
                report["checks"]["savedMp3AndUnicodePath"] = True
            finally:
                native.close()
            native = NativeHost(args.host, state)
            try:
                settings = native.request("get_state")["settings"]
                for key, value in requested.items():
                    assert settings[key] == value, f"Persisted preference {key}: {settings[key]!r} != {value!r}"
                settings = native.request("settings", {"defaultFormat": "mp4", "mp4Quality": 720})
                assert settings["defaultFormat"] == "mp4" and settings["mp4Quality"] == 720
                report["checks"]["persistedAcrossNativeRestart"] = True
                report["checks"]["savedMp4And720p"] = True
            finally:
                native.close()
            legacy = base / "legacy"
            legacy.mkdir()
            (legacy / "state.json").write_text(json.dumps({"settings": {"folderMode": "last", "defaultFolder": "", "lastFolder": str(destination), "openFolder": True}, "jobs": []}), encoding="utf-8")
            native = NativeHost(args.host, legacy)
            try:
                settings = native.request("get_state")["settings"]
                assert settings["defaultFolder"] == str(destination) and settings["openFolder"] is True
                assert settings["authorizedDownloads"] is False
                assert marker.read_bytes() == b"authorized local preservation fixture"
                report["checks"]["legacyFolderMigratedAndMediaPreserved"] = True
            finally:
                native.close()
        finally:
            if made_music:
                music.rmdir()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":
    main()
