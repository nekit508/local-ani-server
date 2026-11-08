import os
import shlex
import socket
from contextlib import redirect_stdout, redirect_stderr, contextmanager
from io import TextIOBase
from selectors import DefaultSelector, EVENT_READ
from threading import RLock, Thread

from click import Group, ClickException


class Redirector(TextIOBase):
    _printer: Printer

    def __init__(self, printer: Printer):
        self._printer = printer

    def write(self, s: str) -> int:
        return self._printer.print(s, end="")


class Printer:
    _sock: socket.socket
    _redirector: Redirector

    def __init__(self, sock: socket.socket):
        self._sock = sock
        self._redirector = Redirector(self)

    def print(self, msg: str, end: str = "\n", *args, **kwargs) -> int:
        out = f"{msg.format(*args, **kwargs)}{end}"
        self._sock.sendall(out.encode("utf-8"))
        return len(out)

    @property
    @contextmanager
    def redirect_std(self):
        # it works btw
        # noinspection PyTypeChecker
        with redirect_stdout(self._redirector), redirect_stderr(self._redirector):
            yield


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

    @property
    @contextmanager
    def lifespan(self):
        self.start()
        yield
        self.stop()

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
        self._sel.register(sock, EVENT_READ, "client")

        io = Printer(sock)
        io.print("las-cli > ", end="")
        self._printers[sock] = io

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

                io = self._printers[sock]

                self._buffers[sock] += data
                splits = self._buffers[sock].split(b"\n")
                self._buffers[sock] = splits[-1]

                for split in splits[:-1]:
                    self._handle_command(split.decode("utf-8"), io)

                io.print("las-cli > ", end="")
            except BlockingIOError:
                break

    def _handle_command(self, line: str, io: Printer):
        try:
            with io.redirect_std:
                self._cli.main(args=shlex.split(line), standalone_mode=False, obj=io)
        except ClickException as e:
            io.print(f"Error: {e}")

    def stop(self):
        super().stop()

        for sock in self._server_sockets:
            self._close_server(sock)

        self._sel.close()