"""Persistent single-worker queue and directory preferences."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time
import uuid

from downloader import ACTIVE, TERMINAL, VERSION, PROTOCOL_VERSION, CAPABILITIES, Cancelled, Runner, Tools, directory, process_options, validate_url

DEFAULT_SETTINGS = {"folderMode": "default", "defaultFolder": "", "lastFolder": "", "openFolder": False, "defaultFormat": "mp3", "mp3Quality": 320, "mp4Quality": 720, "authorizedDownloads": False}
FOLDER_ERROR = "Configure uma pasta de destino na extensão."
CONSENT_ERROR = "Confirme na extensão que você tem autorização para baixar o conteúdo."


def known_music_directory():
    """Resolve the actual Windows Known Folder, including redirected Music folders."""
    if os.name != "nt":
        return ""
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    folder_id = GUID.from_buffer_copy(uuid.UUID("4BD8D571-6D19-48D3-BE97-422220080E43").bytes_le)
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    ole = ctypes.WinDLL("ole32", use_last_error=True)
    shell.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
    shell.SHGetKnownFolderPath.restype = ctypes.c_long
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole.CoTaskMemFree.restype = None
    pointer = ctypes.c_void_p()
    try:
        if shell.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(pointer)) != 0 or not pointer.value:
            return ""
        return str(directory(ctypes.wstring_at(pointer)))
    except (OSError, ValueError):
        return ""
    finally:
        if pointer.value:
            ole.CoTaskMemFree(pointer)


def state_directory() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "OperaMusicDownloader"
    return Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))) / "OperaMusicDownloader"


def pick_directory(initial: str = "", parent_window: int = 0):
    # tkinter delegates to Windows' native directory picker. Runs on main thread.
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        chosen = filedialog.askdirectory(parent=root, title="Escolha onde salvar sua música ou vídeo", initialdir=initial if initial and Path(initial).is_dir() else None, mustexist=True)
        return str(directory(chosen)) if chosen else None
    finally:
        root.destroy()


def open_directory(folder: Path):
    folder = directory(str(folder))
    if os.name == "nt":
        os.startfile(str(folder))
    else:
        subprocess.Popen(["xdg-open", str(folder)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **process_options())


class Application:
    def __init__(self, data_dir: Path, emit=lambda _: None, tools=None, picker=pick_directory, runner_factory=Runner, folder_opener=open_directory, music_folder=None):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.data_dir / "state.json"
        self.emit = emit
        self.tools = tools or Tools()
        self.picker, self.runner_factory, self.folder_opener = picker, runner_factory, folder_opener
        self.music_folder = music_folder or known_music_directory
        self.lock = threading.RLock()
        self.settings = dict(DEFAULT_SETTINGS)
        self.jobs = []
        self.work = queue.Queue()
        self.closing = threading.Event()
        self.current_runner = None
        self.current_id = None
        self.last_emit = self.last_save = 0
        self._load()
        self.worker = threading.Thread(target=self._work_loop, name="omd-download-queue", daemon=True)
        self.worker.start()

    def _load(self):
        try:
            if self.state_path.stat().st_size > 2 * 1024 * 1024:
                raise ValueError("Arquivo de estado muito grande")
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError()
            settings = raw.get("settings", {})
            if isinstance(settings, dict):
                # Validate each field independently so a damaged preference never
                # discards a previously selected destination or valid history.
                for key in ("defaultFolder", "lastFolder"):
                    value = settings.get(key)
                    if isinstance(value, str) and len(value) <= 1024 and "\x00" not in value:
                        self.settings[key] = value
                for key in ("openFolder", "authorizedDownloads"):
                    if type(settings.get(key)) is bool:
                        self.settings[key] = settings[key]
                if settings.get("defaultFormat") in ("mp3", "mp4"):
                    self.settings["defaultFormat"] = settings["defaultFormat"]
                for key, allowed in (("mp3Quality", (128, 192, 320)), ("mp4Quality", (360, 720, 1080))):
                    value = settings.get(key)
                    if type(value) is int and value in allowed:
                        self.settings[key] = value
            jobs = raw.get("jobs", [])
            if isinstance(jobs, list):
                for job in jobs[-100:]:
                    if not isinstance(job, dict) or not isinstance(job.get("id"), str) or not isinstance(job.get("status"), str) or job["status"] not in ACTIVE | TERMINAL:
                        continue
                    # Do not resume media operations automatically after interruption.
                    if job["status"] in ACTIVE:
                        job.update(status="error", error="O aplicativo foi encerrado antes de concluir. Você pode tentar novamente.", speed=None, eta=None)
                    self.jobs.append(job)
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError):
            # Keep a recoverable copy; media files are never touched.
            if self.state_path.exists():
                try:
                    self.state_path.replace(self.data_dir / "state-corrompido.json")
                except OSError:
                    pass
        # A configured but missing destination remains selected and produces a
        # clear error on download. Never silently reroute that user's files.
        if not self.settings["defaultFolder"]:
            if self.settings["lastFolder"]:
                self.settings["defaultFolder"] = self.settings["lastFolder"]
            else:
                try:
                    initial = self.music_folder()
                    self.settings["defaultFolder"] = str(directory(initial)) if initial else ""
                except (OSError, ValueError):
                    pass
        self._save()

    def _save(self):
        with self.lock:
            fd, temp = tempfile.mkstemp(prefix="state-", suffix=".tmp", dir=self.data_dir)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as file:
                    json.dump({"settings": self.settings, "jobs": self.jobs[-100:]}, file, ensure_ascii=False, allow_nan=False)
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(temp, self.state_path)
            finally:
                Path(temp).unlink(missing_ok=True)
            self.last_save = time.monotonic()

    def snapshot(self):
        with self.lock:
            jobs = [{key: value for key, value in job.items() if not key.startswith("_")} for job in self.jobs]
            return copy.deepcopy({"version": VERSION, "protocolVersion": PROTOCOL_VERSION, "capabilities": CAPABILITIES, "settings": self.settings, "jobs": jobs, "tools": self.tools.snapshot()})

    def broadcast(self, force=False):
        now = time.monotonic()
        if force or now - self.last_emit >= 0.25:
            self.last_emit = now
            self.emit({"event": "state", "data": self.snapshot()})

    def update_job(self, job, updates):
        with self.lock:
            job.update(updates)
            terminal = job["status"] in TERMINAL
            if terminal or time.monotonic() - self.last_save > 2:
                self._save()
        self.broadcast(force=terminal)

    def choose_folder(self):
        """Resolve the saved destination only; downloads never invoke a picker."""
        with self.lock:
            try:
                return directory(self.settings["defaultFolder"])
            except (ValueError, OSError):
                raise ValueError(FOLDER_ERROR) from None

    def enqueue(self, payload):
        if self.closing.is_set():
            raise ValueError("A conexão com o navegador foi encerrada.")
        url = validate_url(payload.get("url"))
        for field in ("title", "channel", "thumbnail"):
            if field in payload and not isinstance(payload[field], str):
                raise ValueError("Dados do vídeo inválidos.")
        with self.lock:
            if self.closing.is_set():
                raise ValueError("A conexão com o navegador foi encerrada.")
            if self.settings["authorizedDownloads"] is not True:
                raise ValueError(CONSENT_ERROR)
            folder = self.choose_folder()
            fmt = self.settings["defaultFormat"]
            quality = self.settings["mp3Quality"] if fmt == "mp3" else self.settings["mp4Quality"]
            if any(j.get("url") == url and j.get("format") == fmt and j.get("quality") == quality and j["status"] in ACTIVE for j in self.jobs):
                raise ValueError("Este download já está na fila.")
            if sum(j["status"] in ACTIVE for j in self.jobs) >= 50:
                raise ValueError("A fila está cheia. Aguarde os downloads atuais.")
            self.tools.require()
            job = {"id": str(uuid.uuid4()), "url": url, "title": payload.get("title", "Preparando sua música...")[:500], "channel": payload.get("channel", "")[:300], "thumbnail": payload.get("thumbnail", "")[:2048], "format": fmt, "quality": quality, "status": "queued", "progress": 0, "speed": None, "eta": None, "error": "", "path": "", "actualHeight": None, "resultNote": "", "createdAt": datetime.now(timezone.utc).isoformat(), "_folder": str(folder), "_openFolder": self.settings["openFolder"]}
            previous_jobs = list(self.jobs)
            self.jobs.append(job)
            # Never trim active jobs; retain the latest terminal records up to 100 total.
            while len(self.jobs) > 100:
                index = next((i for i, j in enumerate(self.jobs) if j["status"] in TERMINAL), None)
                if index is None:
                    break
                self.jobs.pop(index)
            try:
                self._save()
            except (OSError, ValueError):
                self.jobs = previous_jobs
                raise
            self.work.put(job)
        self.broadcast(force=True)
        return {"jobId": job["id"]}

    def cancel(self, job_id):
        with self.lock:
            job = next((job for job in self.jobs if job["id"] == job_id), None)
            if job is None:
                raise ValueError("Download não encontrado.")
            if job["status"] in TERMINAL:
                return {"cancelled": False}
            if job_id == self.current_id and self.current_runner:
                self.current_runner.cancel()
            else:
                self.update_job(job, {"status": "cancelled", "speed": None, "eta": None})
        return {"cancelled": True}

    def _work_loop(self):
        while not self.closing.is_set():
            try:
                job = self.work.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                with self.lock:
                    if job["status"] != "queued" or self.closing.is_set():
                        continue
                    cancel_event = threading.Event()
                    runner = self.runner_factory(self.tools, lambda data: self.update_job(job, data), cancel_event)
                    self.current_runner, self.current_id = runner, job["id"]
                    self.update_job(job, {"status": "preparing"})
                result = runner.download(job, directory(job["_folder"]))
                # Once a complete verified file was published, report success even if
                # cancellation races immediately after the atomic publication.
                self.update_job(job, {"status": "completed", "progress": 100, "speed": None, "eta": None, "path": str(result)})
                should_open = job.get("_openFolder", False)
                if should_open:
                    try:
                        self.folder_opener(result.parent)
                    except (OSError, ValueError):
                        pass  # Download succeeded even if Explorer could not open.
            except Cancelled:
                self.update_job(job, {"status": "cancelled", "speed": None, "eta": None})
            except Exception as exc:
                message = str(exc)[:500] if isinstance(exc, (ValueError, RuntimeError)) else "Não foi possível concluir o download. Confira a pasta, o espaço livre e a conexão."
                self.update_job(job, {"status": "error", "error": message, "speed": None, "eta": None})
            finally:
                with self.lock:
                    self.current_runner = self.current_id = None
                self.work.task_done()

    def dispatch(self, command: str, payload: dict):
        if not isinstance(payload, dict):
            raise ValueError("Dados da solicitação inválidos.")
        if command == "ping":
            return {"version": VERSION, "protocolVersion": PROTOCOL_VERSION, "capabilities": dict(CAPABILITIES)}
        if command == "get_state":
            return self.snapshot()
        if command == "download":
            return self.enqueue(payload)
        if command == "cancel":
            return self.cancel(payload.get("jobId"))
        if command == "pick_folder":
            chosen = self.picker(self.settings["defaultFolder"] or self.settings["lastFolder"])
            if not chosen:
                return {"cancelled": True}
            folder = directory(chosen)
            with self.lock:
                if self.closing.is_set():
                    raise ValueError("A conexão com o navegador foi encerrada.")
                previous_settings = dict(self.settings)
                self.settings["lastFolder"] = str(folder)
                # The browser popup may close as the native picker takes focus.
                # Commit here rather than relying on a later popup message.
                self.settings["defaultFolder"] = str(folder)
                self.settings["folderMode"] = "default"
                try:
                    self._save()
                except (OSError, ValueError):
                    self.settings = previous_settings
                    raise
            self.broadcast(force=True)
            return {"path": str(folder)}
        if command == "settings":
            if not set(payload).issubset({"folderMode", "defaultFolder", "openFolder", "defaultFormat", "mp3Quality", "mp4Quality", "authorizedDownloads"}):
                raise ValueError("Configuração desconhecida.")
            changes = {}
            if "folderMode" in payload:
                if payload["folderMode"] != "default":
                    raise ValueError("A pasta é configurada somente no popup da extensão.")
            for key in ("openFolder", "authorizedDownloads"):
                if key in payload:
                    if type(payload[key]) is not bool:
                        raise ValueError("Preferência inválida: " + key + ".")
                    changes[key] = payload[key]
            if "defaultFormat" in payload:
                if payload["defaultFormat"] not in ("mp3", "mp4"):
                    raise ValueError("Escolha MP3 ou MP4.")
                changes["defaultFormat"] = payload["defaultFormat"]
            for key, allowed in (("mp3Quality", (128, 192, 320)), ("mp4Quality", (360, 720, 1080))):
                if key in payload:
                    if type(payload[key]) is not int or payload[key] not in allowed:
                        raise ValueError("Qualidade inválida: " + key + ".")
                    changes[key] = payload[key]
            if "defaultFolder" in payload:
                try:
                    changes["defaultFolder"] = str(directory(payload["defaultFolder"]))
                except (ValueError, OSError):
                    raise ValueError(FOLDER_ERROR) from None
            with self.lock:
                final = dict(self.settings, **changes)
                previous_settings = self.settings
                self.settings = final
                try:
                    self._save()
                except (OSError, ValueError):
                    self.settings = previous_settings
                    raise
            self.broadcast(force=True)
            return dict(self.settings)
        if command == "open_folder":
            with self.lock:
                if payload.get("jobId"):
                    job = next((j for j in self.jobs if j["id"] == payload["jobId"] and j["status"] == "completed"), None)
                    if not job or not job.get("path"):
                        raise ValueError("Arquivo concluído não encontrado.")
                    folder = Path(job["path"]).parent
                else:
                    folder = self.settings["defaultFolder"] or self.settings["lastFolder"]
            if not folder:
                raise ValueError("Nenhuma pasta foi escolhida ainda.")
            self.folder_opener(directory(str(folder)))
            return {"opened": True}
        if command == "clear_history":
            with self.lock:
                previous_jobs = self.jobs
                self.jobs = [j for j in self.jobs if j["status"] not in TERMINAL]
                try:
                    self._save()
                except (OSError, ValueError):
                    self.jobs = previous_jobs
                    raise
            self.broadcast(force=True)
            return {"cleared": True}
        raise ValueError("Comando desconhecido.")

    def close(self):
        with self.lock:
            self.closing.set()
            if self.current_runner:
                self.current_runner.cancel()
            for job in self.jobs:
                if job["status"] == "queued":
                    job.update(status="error", error="O aplicativo foi encerrado antes de iniciar. Você pode tentar novamente.")
            self._save()
        self.worker.join(timeout=12)

