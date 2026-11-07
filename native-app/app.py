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

from downloader import ACTIVE, TERMINAL, VERSION, Cancelled, Runner, Tools, directory, process_options, validate_url

DEFAULT_SETTINGS = {"folderMode": "ask", "defaultFolder": "", "lastFolder": "", "openFolder": False}


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
    def __init__(self, data_dir: Path, emit=lambda _: None, tools=None, picker=pick_directory, runner_factory=Runner, folder_opener=open_directory):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.data_dir / "state.json"
        self.emit = emit
        self.tools = tools or Tools()
        self.picker, self.runner_factory, self.folder_opener = picker, runner_factory, folder_opener
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
                for key, default in DEFAULT_SETTINGS.items():
                    value = settings.get(key, default)
                    if type(value) is type(default):
                        self.settings[key] = value[:1024] if isinstance(value, str) else value
                if self.settings["folderMode"] not in {"ask", "last", "default"}:
                    self.settings["folderMode"] = "ask"
            jobs = raw.get("jobs", [])
            if isinstance(jobs, list):
                for job in jobs[-100:]:
                    if not isinstance(job, dict) or not isinstance(job.get("id"), str) or job.get("status") not in ACTIVE | TERMINAL:
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
            return copy.deepcopy({"settings": self.settings, "jobs": jobs, "tools": self.tools.snapshot()})

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
        with self.lock:
            mode = self.settings["folderMode"]
            previous = self.settings["lastFolder"]
            fixed = self.settings["defaultFolder"]
        selected = previous if mode == "last" else fixed if mode == "default" else ""
        if selected:
            try:
                return directory(selected)
            except (ValueError, OSError):
                pass  # Removed/removable folder: ask again instead of choosing silently.
        chosen = self.picker(previous or fixed)
        if not chosen:
            return None
        selected = directory(chosen)
        with self.lock:
            if self.closing.is_set():
                raise ValueError("A conexão com o navegador foi encerrada.")
            self.settings["lastFolder"] = str(selected)
            self._save()
        self.broadcast(force=True)
        return selected

    def enqueue(self, payload):
        if self.closing.is_set():
            raise ValueError("A conexão com o navegador foi encerrada.")
        if payload.get("authorized") is not True:
            raise ValueError("Confirme que você tem autorização para baixar este conteúdo.")
        url = validate_url(payload.get("url"))
        fmt, quality = payload.get("format", "mp3"), payload.get("quality", 192)
        if not isinstance(fmt, str) or fmt not in {"mp3", "m4a", "opus", "mp4"} or type(quality) is not int:
            raise ValueError("Formato ou qualidade inválidos.")
        if quality not in ({360, 720, 1080} if fmt == "mp4" else {128, 192, 320}):
            raise ValueError("Qualidade inválida para o formato escolhido.")
        for field in ("title", "channel", "thumbnail"):
            if field in payload and not isinstance(payload[field], str):
                raise ValueError("Dados do vídeo inválidos.")
        with self.lock:
            if any(j["url"] == url and j["format"] == fmt and j["quality"] == quality and j["status"] in ACTIVE for j in self.jobs):
                raise ValueError("Este download já está na fila.")
            if sum(j["status"] in ACTIVE for j in self.jobs) >= 50:
                raise ValueError("A fila está cheia. Aguarde os downloads atuais.")
        self.tools.require()
        folder = self.choose_folder()
        if folder is None:
            return {"cancelled": True}
        if self.closing.is_set():
            raise ValueError("A conexão com o navegador foi encerrada.")
        job = {"id": str(uuid.uuid4()), "url": url, "title": payload.get("title", "Preparando sua música...")[:500], "channel": payload.get("channel", "")[:300], "thumbnail": payload.get("thumbnail", "")[:2048], "format": fmt, "quality": quality, "status": "queued", "progress": 0, "speed": None, "eta": None, "error": "", "path": "", "createdAt": datetime.now(timezone.utc).isoformat(), "_folder": str(folder)}
        with self.lock:
            if self.closing.is_set():
                raise ValueError("A conexão com o navegador foi encerrada.")
            self.jobs.append(job)
            # Never trim active jobs; retain the latest terminal records up to 100 total.
            while len(self.jobs) > 100:
                index = next((i for i, j in enumerate(self.jobs) if j["status"] in TERMINAL), None)
                if index is None:
                    break
                self.jobs.pop(index)
            self._save()
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
                with self.lock:
                    should_open = self.settings["openFolder"]
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
            return {"version": VERSION}
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
                self.settings["lastFolder"] = str(folder)
                self._save()
            self.broadcast(force=True)
            return {"path": str(folder)}
        if command == "settings":
            if not set(payload).issubset({"folderMode", "defaultFolder", "openFolder"}):
                raise ValueError("Configuração desconhecida.")
            changes = {}
            if "folderMode" in payload:
                if not isinstance(payload["folderMode"], str) or payload["folderMode"] not in {"ask", "last", "default"}:
                    raise ValueError("Modo de pasta inválido.")
                changes["folderMode"] = payload["folderMode"]
            if "openFolder" in payload:
                if type(payload["openFolder"]) is not bool:
                    raise ValueError("Preferência de abertura inválida.")
                changes["openFolder"] = payload["openFolder"]
            if "defaultFolder" in payload:
                changes["defaultFolder"] = str(directory(payload["defaultFolder"])) if payload["defaultFolder"] else ""
            with self.lock:
                final = dict(self.settings, **changes)
                if final["folderMode"] == "default" and not final["defaultFolder"]:
                    raise ValueError("Escolha uma pasta padrão antes de ativar esta opção.")
                self.settings = final
                self._save()
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
                self.jobs = [j for j in self.jobs if j["status"] not in TERMINAL]
                self._save()
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

