"""Windows native host entry point. Console PyInstaller build preserves stdio."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import queue
import sys
import threading

from app import Application, state_directory
from downloader import VERSION, Tools, self_test
from messaging import ProtocolError, Writer, read_message


class InstanceLock:
    def __init__(self, folder):
        Path(folder).mkdir(parents=True, exist_ok=True)
        self.file = (Path(folder) / "host.lock").open("a+b")
        self.file.seek(0)
        if os.name == "nt":
            import msvcrt
            if self.file.read(1) == b"":
                self.file.write(b"0")
                self.file.flush()
            self.file.seek(0)
            msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def close(self):
        self.file.close()


def extension_id():
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    for file in (base / "extension-id.txt", base.parent / "extension" / "extension-id.txt"):
        try:
            value = file.read_text(encoding="ascii").strip()
            if len(value) == 32 and all("a" <= char <= "p" for char in value):
                return value
        except OSError:
            pass
    raise ValueError("Identificador da extensão ausente. Reinstale o aplicativo auxiliar.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Opera Music Downloader — aplicativo auxiliar")
    parser.add_argument("origin", nargs="?")
    parser.add_argument("--parent-window", type=int, default=0)
    parser.add_argument("--state-dir", type=Path, default=None)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args(argv)
    if args.version:
        print(VERSION)
        return 0
    if args.self_test:
        result = self_test(Tools())
        # Captured Windows console streams can use CP1252; ASCII JSON is also UTF-8.
        print(json.dumps(result, ensure_ascii=True))
        return 0 if result["ok"] else 1
    try:
        allowed = "chrome-extension://" + extension_id() + "/"
        if args.origin != allowed:
            raise ValueError("Este aplicativo deve ser aberto pela extensão autorizada no Opera GX.")
        if os.name == "nt":
            import msvcrt
            msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
            msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
        # A daemon reader must not hold BufferedReader's lock during shutdown.
        # Raw output also avoids a second failing flush by TextIOWrapper when
        # the browser closes its end of the native messaging pipe.
        native_input = os.fdopen(sys.stdin.buffer.fileno(), "rb", buffering=0, closefd=False)
        native_output = os.fdopen(sys.stdout.buffer.fileno(), "wb", buffering=0, closefd=False)
        writer = Writer(native_output)
        folder = args.state_dir or state_directory()
        lock = InstanceLock(folder)
        app = Application(folder, emit=writer.send)
        gui_requests = queue.Queue()
        reader_closed = threading.Event()
        reader_errors = []

        def respond(message):
            request_id = message["id"]
            try:
                command = message.get("type")
                if not isinstance(command, str) or len(command) > 64:
                    raise ValueError("Comando inválido.")
                result = app.dispatch(command, message.get("payload", {}))
                writer.send({"id": request_id, "ok": True, "result": result})
            except (ValueError, OSError, RuntimeError) as exc:
                writer.send({"id": request_id, "ok": False, "error": str(exc)[:500]})
            except Exception:
                writer.send({"id": request_id, "ok": False, "error": "Não foi possível executar esta ação. Confira a instalação do aplicativo auxiliar."})

        def read_requests():
            # Blocking native directory dialogs must not block cancellation or
            # state updates. Only GUI operations execute on the main thread.
            try:
                while not writer.closed:
                    message = read_message(native_input)
                    if message is None:
                        break
                    request_id = message.get("id")
                    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
                        raise ProtocolError("Identificador de solicitação inválido.")
                    command = message.get("type")
                    if command == "pick_folder":
                        gui_requests.put(message)
                    else:
                        respond(message)
            except (ValueError, OSError, ProtocolError) as exc:
                reader_errors.append(exc)
            finally:
                reader_closed.set()
                app.close()

        reader = threading.Thread(target=read_requests, name="omd-native-reader", daemon=True)
        reader.start()
        try:
            while not writer.closed and not reader_closed.is_set():
                try:
                    message = gui_requests.get(timeout=0.2)
                except queue.Empty:
                    continue
                respond(message)
        finally:
            app.close()
            lock.close()
        if reader_errors:
            raise reader_errors[0]
        return 0
    except (ValueError, OSError, ProtocolError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
