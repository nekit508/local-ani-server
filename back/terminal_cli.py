import os
import shlex
import socket
from selectors import DefaultSelector, EVENT_READ
from threading import RLock, Thread

from click import Group


class Printer:
    _sock: socket.socket

    def __init__(self, sock: socket.socket):
        self._sock = sock

    def print(self, msg: str, *args, **kwargs):
        self._sock.sendall(f"{msg.format(*args, **kwargs)}\n".encode("utf-8"))


class AWorker:
    _lock: RLock
    _working: bool
    _thread: Thread | None

    def __init__(self):
        self._lock = RLock()
        self._working = False
        self._thread = None

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("Already running")

        with self._lock:
            self._working = True
            self._thread = Thread(target=self._start, daemon=True)
            self._thread.start()

    @property
    def should_stop(self):
        with self._lock:
            return not self._working

    def _start(self):
        try:
            self._loop()
        finally:
            with self._lock:
                self._working = False

    def _loop(self): ...

    def stop(self):
        with self._lock:
            self._working = False
        self._thread.join()


class TerminalCLI(AWorker):
    _sel: DefaultSelector
    _server_sockets: list[socket.socket]
    _buffers: dict[socket.socket, bytes]
    _printers: dict[socket.socket, Printer]
    _cli: Group

    def __init__(self, paths: list[str], cli: Group):
        super().__init__()
        self._buffers = {}
        self._printers = {}

        self._cli = cli

        self._sel = DefaultSelector()
        self._server_sockets = list(self._open_server(path) for path in paths)

    def _open_server(self, path: str) -> socket.socket:
        if os.path.exists(path):
            os.unlink(path)

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(path)

        sock.listen()
        sock.setblocking(False)
        self._sel.register(sock, EVENT_READ, "server")

        return sock

    def _close_server(self, sock: socket.socket):
        self._sel.unregister(sock)
        sock.close()
        sock.detach()

    def _loop(self):
        while not self.should_stop:
            for key, mask in self._sel.select(1):
                if mask & EVENT_READ:
                    if key.data == "server":
                        self._accept(key.fileobj)
                    elif key.data == "client":
                        self._handle(key.fileobj)

    def _accept(self, sock: socket.socket):
        while True:
            try:
                self._attach(sock.accept()[0])
            except BlockingIOError:
                break

    def _attach(self, sock: socket.socket):
        sock.setblocking(False)
        self._buffers[sock] = b""
        self._printers[sock] = Printer(sock)
        self._sel.register(sock, EVENT_READ, "client")

    def _detach(self, sock: socket.socket):
        self._sel.unregister(sock)
        sock.close()
        del self._buffers[sock]
        del self._printers[sock]

    def _handle(self, sock: socket.socket):
        while True:
            try:
                data = sock.recv(8192)

                if data == b"":
                    self._detach(sock)
                    break

                self._buffers[sock] += data

                splits = self._buffers[sock].split(b"\n")
                self._buffers[sock] = splits[-1]

                for split in splits[:-1]:
                    self._handle_command(split.decode("utf-8"), self._printers[sock])
            except BlockingIOError:
                break


    def _handle_command(self, line: str, io: Printer):
        try:
            self._cli.main(args=shlex.split(line), standalone_mode=False, obj=io)
        except Exception as e:
            io.print(f"Error: {e}")

    def stop(self):
        super().stop()

        for sock in self._server_sockets:
            self._close_server(sock)

        self._sel.close()