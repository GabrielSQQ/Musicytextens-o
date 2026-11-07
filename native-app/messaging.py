"""Bounded Chromium Native Messaging framing. stdout is reserved for JSON frames."""
from __future__ import annotations

import json
import struct
import threading
from typing import BinaryIO

MAX_MESSAGE = 1024 * 1024


class ProtocolError(ValueError):
    pass


def _read_exact(stream: BinaryIO, length: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < length:
        block = stream.read(length - len(chunks))
        if not block:
            raise ProtocolError("Mensagem incompleta recebida do navegador.")
        chunks.extend(block)
    return bytes(chunks)


def read_message(stream: BinaryIO):
    first = stream.read(4)
    if not first:
        return None
    if len(first) < 4:
        first += _read_exact(stream, 4 - len(first))
    length = struct.unpack("<I", first)[0]
    if not 0 < length <= MAX_MESSAGE:
        raise ProtocolError("Tamanho de mensagem inválido.")
    try:
        message = json.loads(_read_exact(stream, length).decode("utf-8"))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ProtocolError("Mensagem JSON inválida.") from exc
    if not isinstance(message, dict):
        raise ProtocolError("A mensagem deve ser um objeto JSON.")
    return message


class Writer:
    def __init__(self, stream: BinaryIO):
        self.stream = stream
        self.lock = threading.Lock()
        self.closed = False

    def send(self, message: dict):
        data = json.dumps(message, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(data) > MAX_MESSAGE:
            raise ProtocolError("A resposta excede o limite do navegador.")
        with self.lock:
            if self.closed:
                return
            try:
                remaining = memoryview(struct.pack("<I", len(data)) + data)
                # Raw pipe writes may be shorter than the requested frame.
                # Keep the lock for the entire frame, including every retry.
                while remaining:
                    written = self.stream.write(remaining)
                    if not written:
                        raise BrokenPipeError("A conexão com o navegador foi encerrada.")
                    remaining = remaining[written:]
                self.stream.flush()
            except (BrokenPipeError, OSError):
                self.closed = True

