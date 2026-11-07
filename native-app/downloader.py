"""Real yt-dlp/FFmpeg processing; no shell, cookies, credentials or DRM bypass."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
from urllib.parse import parse_qs, urlsplit

VERSION = "1.1.0"
PROTOCOL_VERSION = 2
CAPABILITIES = {"oneClickDownloads": True}
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
TERMINAL = {"completed", "error", "cancelled"}
ACTIVE = {"queued", "preparing", "downloading", "converting"}


class DownloadError(RuntimeError):
    pass


class Cancelled(DownloadError):
    pass


def validate_url(value: str) -> str:
    """Only public YouTube video identifiers, canonicalized before execution."""
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 32 for c in value):
        raise ValueError("Endereço de vídeo inválido.")
    try:
        url = urlsplit(value)
        if url.scheme != "https" or url.username or url.password or url.port is not None:
            raise ValueError()
        host = (url.hostname or "").lower()
        parts = url.path.strip("/").split("/")
        if host == "youtu.be" and len(parts) == 1:
            video = parts[0]
        elif host in {"youtube.com", "www.youtube.com", "music.youtube.com", "m.youtube.com"}:
            if url.path == "/watch":
                values = parse_qs(url.query).get("v", [])
                if len(values) != 1:
                    raise ValueError()
                video = values[0]
            elif len(parts) == 2 and parts[0] in {"shorts", "live", "embed"}:
                video = parts[1]
            else:
                raise ValueError()
        else:
            raise ValueError()
        if not VIDEO_ID.fullmatch(video):
            raise ValueError()
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Use um endereço HTTPS de um vídeo do YouTube ou YouTube Music.") from exc
    return "https://www.youtube.com/watch?v=" + video


def safe_filename(title: str, max_units: int = 130) -> str:
    title = unicodedata.normalize("NFC", str(title or "Sem título"))
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', " ", title)
    title = re.sub(r"\s+", " ", title).strip(" .") or "Sem título"
    # Windows limits filenames in UTF-16 code units, not Python code points.
    title = title.encode("utf-16-le")[: max_units * 2].decode("utf-16-le", errors="ignore").rstrip(" .")
    device_name = title.split(".", 1)[0].rstrip(" .")
    if re.fullmatch(r"CON|PRN|AUX|NUL|COM[0-9¹²³]|LPT[0-9¹²³]", device_name, re.I):
        title = "_" + title
    return title or "Sem título"


def media_title(info: dict) -> str:
    # Only extractor metadata, never infer artist from channel or a title split.
    artist, track = info.get("artist"), info.get("track")
    if isinstance(artist, str) and artist.strip() and isinstance(track, str) and track.strip():
        return safe_filename(f"{artist} - {track}")
    return safe_filename(info.get("title") or "Sem título")


def directory(value: str) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("Escolha uma pasta válida.")
    path = Path(value)
    if not path.is_absolute() or not path.is_dir():
        raise ValueError("A pasta deve existir e ter um caminho absoluto.")
    path = path.resolve(strict=True)
    if os.name == "nt" and (str(path).startswith("\\\\") or str(path).startswith("\\\\?")):
        raise ValueError("Escolha uma pasta local ou uma unidade de disco mapeada.")
    # Keep room for staging paths even without Windows long-path policy enabled.
    if os.name == "nt" and len(str(path).encode("utf-16-le")) // 2 > 170:
        raise ValueError("O caminho é muito longo. Escolha uma pasta mais próxima da raiz do disco.")
    return path


class Tools:
    def __init__(self, base: Path | None = None):
        self.base = Path(base) if base else Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
        self.paths = {}
        for name in ("yt-dlp", "ffmpeg", "ffprobe", "deno"):
            filename = name + (".exe" if os.name == "nt" else "")
            bundled = self.base / "tools" / filename
            self.paths[name] = str(bundled) if bundled.is_file() else (None if getattr(sys, "frozen", False) else shutil.which(filename))

    def require(self):
        missing = [name for name in ("yt-dlp", "ffmpeg", "ffprobe") if not self.paths[name]]
        if missing:
            raise DownloadError("Dependências ausentes: " + ", ".join(missing) + ". Reinstale o aplicativo auxiliar.")

    def snapshot(self):
        return {name: {"available": bool(path)} for name, path in self.paths.items()}


def process_options():
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def stop_process(process):
    if process is None or process.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
        except OSError:
            pass


def user_error(output: str) -> str:
    lower = output.lower()
    if any(s in lower for s in ("sign in", "login", "cookies", "age-restricted", "confirm your age", "private video")):
        return "O vídeo exige autenticação ou possui acesso restrito. O aplicativo não solicita credenciais nem contorna restrições."
    if "drm" in lower:
        return "Este conteúdo possui proteção técnica e não pode ser processado."
    if any(s in lower for s in ("unavailable", "not available", "removed", "geo-restricted", "geo restricted")):
        return "O vídeo está indisponível ou restrito para este acesso."
    if any(s in lower for s in ("403", "429", "challenge", "javascript", "deno", "ejs", "signature")):
        return "O YouTube recusou o acesso ou mudou seu processamento. Atualize o aplicativo auxiliar e tente novamente mais tarde."
    if any(s in lower for s in ("no space", "disk full", "not enough space")):
        return "Não há espaço suficiente no disco escolhido."
    if any(s in lower for s in ("permission denied", "access is denied")):
        return "Sem permissão para salvar nessa pasta. Escolha outra pasta."
    if "requested format" in lower:
        return "Este vídeo não oferece um formato compatível com a qualidade escolhida."
    return "Não foi possível concluir o download. Confira a conexão, atualize o aplicativo auxiliar e tente novamente."


class Runner:
    def __init__(self, tools: Tools, emit, cancelled: threading.Event, source_resolver=None):
        self.tools, self.emit, self.cancelled = tools, emit, cancelled
        # Internal dependency injection for authorized local-media integration tests.
        # Application/Native Messaging never accept or pass a resolver.
        self.resolve_source = source_resolver or validate_url
        self.process = None
        self.lock = threading.Lock()

    def cancel(self):
        self.cancelled.set()
        with self.lock:
            stop_process(self.process)

    def check_cancelled(self):
        if self.cancelled.is_set():
            raise Cancelled("Download cancelado.")

    def run(self, args: list[str], on_line=None, limit=16 * 1024 * 1024, timeout=600) -> str:
        self.check_cancelled()
        with self.lock:
            self.check_cancelled()
            process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **process_options())
            self.process = process
        timed_out = threading.Event()

        def expire():
            timed_out.set()
            stop_process(process)

        timer = threading.Timer(timeout, expire)
        timer.daemon = True
        timer.start()
        chunks, count = [], 0
        try:
            while True:
                line = process.stdout.readline(1024 * 1024)
                if not line:
                    break
                count += len(line)
                if on_line is None:
                    if count > limit:
                        stop_process(process)
                        raise DownloadError("Os dados recebidos excedem o limite de segurança.")
                    chunks.append(line)
                else:
                    chunks.append(line)
                    if len(chunks) > 80:
                        del chunks[0]
                    on_line(line.decode("utf-8", errors="replace").strip())
                self.check_cancelled()
            code = process.wait()
            self.check_cancelled()
            if timed_out.is_set():
                raise DownloadError("A operação demorou demais. Confira a conexão e tente novamente.")
            output = b"".join(chunks).decode("utf-8", errors="replace")
            if code:
                raise DownloadError(user_error(output))
            return output
        finally:
            timer.cancel()
            if process.poll() is None:
                stop_process(process)
                process.wait(timeout=10)
            if process.stdout:
                process.stdout.close()
            with self.lock:
                if self.process is process:
                    self.process = None

    def common(self):
        self.tools.require()
        args = [self.tools.paths["yt-dlp"], "--ignore-config", "--no-playlist", "--no-warnings", "--no-cache-dir", "--no-color", "--no-remote-components", "--socket-timeout", "30", "--retries", "3", "--fragment-retries", "3", "--ffmpeg-location", str(Path(self.tools.paths["ffmpeg"]).parent)]
        if self.tools.paths.get("deno"):
            args += ["--js-runtimes", "deno:" + self.tools.paths["deno"]]
        return args

    def inspect(self, url):
        output = self.run(self.common() + ["--dump-single-json", "--skip-download", "--", self.resolve_source(validate_url(url))], timeout=180)
        try:
            info = json.loads(output)
        except ValueError as exc:
            raise DownloadError("O YouTube retornou dados inesperados. Atualize o aplicativo auxiliar.") from exc
        if not isinstance(info, dict) or info.get("_type", "video") not in {"video"}:
            raise DownloadError("Escolha um vídeo individual.")
        if info.get("is_live"):
            raise DownloadError("Transmissões ao vivo em andamento não são compatíveis.")
        if info.get("has_drm"):
            raise DownloadError("Este conteúdo possui proteção técnica e não pode ser processado.")
        return info

    def download(self, job: dict, folder: Path) -> Path:
        info = self.inspect(job["url"])
        self.emit({"title": str(info.get("title") or job["title"])[:500], "channel": str(info.get("channel") or info.get("uploader") or "")[:300], "status": "downloading"})
        fmt, quality = job["format"], job["quality"]
        if fmt == "mp3":
            format_args = ["-f", "bestaudio/best", "-x", "--audio-format", "mp3", "--audio-quality", str(quality) + "K"]
        elif fmt == "m4a":
            format_args = ["-f", "bestaudio[ext=m4a]/bestaudio/best", "-x", "--audio-format", "m4a", "--audio-quality", "0"]
        elif fmt == "opus":
            format_args = ["-f", "bestaudio[acodec^=opus]/bestaudio/best", "-x", "--audio-format", "opus", "--audio-quality", "0"]
        else:
            # Convert codecs when necessary, so MP4 is playable in default Windows players.
            format_args = ["-f", f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/bestvideo+bestaudio/best", "--merge-output-format", "mkv", "--remux-video", "mkv"]
        with tempfile.TemporaryDirectory(prefix=".omd-", dir=folder) as temp:
            temp_path = Path(temp)
            args = self.common() + ["--newline", "--progress", "--progress-template", "download:OMD_PROGRESS:%(progress)j", "--print", "after_move:OMD_FILE:%(filepath)s", "--no-quiet", "--no-simulate", "--paths", str(temp_path), "--output", "media.%(ext)s", "--add-metadata"] + format_args
            # yt-dlp normally falls back to uploader as artist and upload date as
            # release date. Explicit empty overrides prevent those inferences.
            for field, source_field in (("artist", "artist,artists"), ("album", "album"), ("album_artist", "album_artist"), ("date", "release_date"), ("genre", "genre")):
                args += ["--parse-metadata", "%(" + source_field + "|)s:(?P<meta_" + field + ">.*)"]
            if fmt in {"mp3", "m4a"} and isinstance(info.get("thumbnail"), str):
                args += ["--embed-thumbnail", "--convert-thumbnails", "jpg"]
            # The second extraction is deliberate: signed media URLs can expire in queue.
            args += ["--", self.resolve_source(validate_url(job["url"]))]
            found = []

            def progress(line):
                if line.startswith("OMD_PROGRESS:"):
                    try:
                        p = json.loads(line[len("OMD_PROGRESS:"):])
                        downloaded = float(p.get("downloaded_bytes") or 0)
                        total = float(p.get("total_bytes") or p.get("total_bytes_estimate") or 0)
                        speed, eta = p.get("speed"), p.get("eta")
                        update = {"status": "downloading", "progress": min(99, downloaded * 100 / total) if total > 0 else 0, "speed": speed if isinstance(speed, (int, float)) and math.isfinite(speed) else None, "eta": eta if isinstance(eta, (int, float)) and math.isfinite(eta) else None}
                        self.emit(update)
                    except (ValueError, TypeError):
                        pass
                elif line.startswith("OMD_FILE:"):
                    found.append(line[len("OMD_FILE:"):])
                elif any(marker in line for marker in ("[ExtractAudio]", "[Merger]", "[VideoConvertor]", "[EmbedThumbnail]", "[Metadata]")):
                    self.emit({"status": "converting", "progress": 99, "speed": None, "eta": None})

            self.run(args, on_line=progress, timeout=12 * 60 * 60)
            self.check_cancelled()
            source_ext = "mkv" if fmt == "mp4" else fmt
            expected = temp_path / ("media." + source_ext)
            candidates = [Path(item) for item in reversed(found)] + [expected]
            source = next((p for p in candidates if p.is_file() and p.resolve().parent == temp_path.resolve() and p.suffix.lower() == "." + source_ext), None)
            if source is None or source.stat().st_size == 0:
                raise DownloadError("O arquivo final não foi gerado corretamente.")
            if fmt == "mp4":
                self.emit({"status": "converting", "progress": 99, "speed": None, "eta": None})
                source_streams = self.verify_media(source, fmt)
                source_height = next(s.get("height") for s in source_streams if s.get("codec_type") == "video")
                final = temp_path / "media-final.mp4"
                self.run([self.tools.paths["ffmpeg"], "-hide_banner", "-loglevel", "error", "-i", str(source), "-map", "0:v:0", "-map", "0:a:0", "-vf", f"scale=-2:'trunc(min(ih,{quality})/2)*2'", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast", "-crf", "20", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(final)], on_line=lambda _: None, timeout=12 * 60 * 60)
                source = final
            streams = self.verify_media(source, fmt)
            if fmt == "mp4":
                height = next(s.get("height") for s in streams if s.get("codec_type") == "video")
                if type(height) is int and height > 0:
                    note = f"Salvo em {height}p."
                    if height < quality:
                        note = f"Salvo em {height}p; {quality}p não estava disponível."
                    elif type(source_height) is int and source_height > quality:
                        note = f"Salvo em {height}p; resolução ajustada ao limite configurado de {quality}p."
                    self.emit({"actualHeight": height, "resultNote": note})
            return self.publish(source, folder, media_title(info), fmt)

    def verify_media(self, path: Path, fmt: str):
        data = self.run([self.tools.paths["ffprobe"], "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height", "-of", "json", str(path)], timeout=60)
        try:
            streams = json.loads(data)["streams"]
            if not any(s.get("codec_type") == "audio" for s in streams):
                raise ValueError()
            if fmt == "mp4" and not any(s.get("codec_type") == "video" for s in streams):
                raise ValueError()
            if fmt == "mp3" and not any(s.get("codec_name") == "mp3" for s in streams):
                raise ValueError()
        except (KeyError, ValueError, TypeError) as exc:
            raise DownloadError("Não foi possível validar a mídia gerada.") from exc
        return streams

    def publish(self, source: Path, folder: Path, title: str, fmt: str) -> Path:
        max_units = 130
        if os.name == "nt":
            max_units = min(max_units, 240 - len(str(folder).encode("utf-16-le")) // 2 - 20)
        title = safe_filename(title, max_units=max(20, max_units))
        for number in range(1, 10001):
            self.check_cancelled()
            name = title + (f" ({number})" if number > 1 else "") + "." + fmt
            target = folder / name
            try:
                os.link(source, target)  # Atomic and never overwrites an existing file.
                return target
            except FileExistsError:
                continue
            except OSError:
                # FAT/exFAT and some mapped drives lack hardlinks.
                owned = False
                try:
                    try:
                        with target.open("xb") as out:
                            owned = True
                            with source.open("rb") as inp:
                                while block := inp.read(1024 * 1024):
                                    self.check_cancelled()
                                    out.write(block)
                            out.flush()
                            os.fsync(out.fileno())
                    except BaseException:
                        # Windows cannot unlink an open file: leave the context first.
                        if owned:
                            target.unlink(missing_ok=True)
                        raise
                    return target
                except FileExistsError:
                    continue
        raise DownloadError("Há muitos arquivos com esse nome na pasta escolhida.")


def self_test(tools: Tools) -> dict:
    results = {}
    for name, path in tools.paths.items():
        if not path:
            results[name] = {"ok": False, "error": "não encontrado"}
            continue
        try:
            arg = "-version" if name in {"ffmpeg", "ffprobe"} else "--version"
            out = subprocess.run([path, arg], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30, **process_options())
            results[name] = {"ok": out.returncode == 0, "version": out.stdout.decode("utf-8", errors="replace").splitlines()[0][:240]}
        except (OSError, subprocess.SubprocessError, IndexError) as exc:
            results[name] = {"ok": False, "error": str(exc)[:200]}
    codecs = {name: False for name in ("libmp3lame", "libopus", "aac", "libx264")}
    if results["ffmpeg"].get("ok"):
        try:
            encoders = subprocess.run([tools.paths["ffmpeg"], "-hide_banner", "-encoders"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30, **process_options()).stdout.decode("utf-8", errors="replace")
            codecs = {name: bool(re.search(r"\b" + re.escape(name) + r"\b", encoders)) for name in codecs}
        except (OSError, subprocess.SubprocessError):
            pass
    conversion = {"ok": False, "error": "FFmpeg ou FFprobe indisponível"}
    if results["ffmpeg"].get("ok") and results["ffprobe"].get("ok"):
        try:
            with tempfile.TemporaryDirectory(prefix="omd-selftest-") as temp:
                path = Path(temp) / "teste autorizado.mp3"
                runner = Runner(tools, lambda _: None, threading.Event())
                runner.run([tools.paths["ffmpeg"], "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5", "-c:a", "libmp3lame", "-b:a", "192k", str(path)], timeout=30)
                runner.verify_media(path, "mp3")
                conversion = {"ok": True, "bytes": path.stat().st_size}
        except Exception as exc:
            conversion = {"ok": False, "error": str(exc)[:300]}
    return {"ok": all(value.get("ok") for value in results.values()) and conversion["ok"] and all(codecs.values()), "version": VERSION, "tools": results, "codecs": codecs, "conversion": conversion}
