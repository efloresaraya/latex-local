import asyncio
import threading
from pathlib import Path
from typing import Awaitable, Callable, Dict

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# Extensions that should trigger a file-changed notification
WATCH_EXTENSIONS = {".tex", ".bib", ".sty", ".cls", ".tikz", ".txt", ".png", ".jpg", ".jpeg", ".pdf"}

# Extensions produced by LaTeX compilation — never notify for these
COMPILE_OUTPUT = {".aux", ".log", ".out", ".toc", ".fls", ".fdb_latexmk",
                  ".synctex", ".gz", ".bbl", ".blg", ".idx", ".ilg", ".ind",
                  ".lof", ".lot", ".nav", ".snm", ".vrb"}


class _DebounceHandler(FileSystemEventHandler):
    def __init__(self, callback: Callable[[], None], delay: float = 0.6):
        self._callback = callback
        self._delay = delay
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def _trigger(self):
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(self._delay, self._callback)
            self._timer.start()

    def _should_watch(self, path: str) -> bool:
        p = Path(path)
        return p.suffix in WATCH_EXTENSIONS and p.suffix not in COMPILE_OUTPUT

    def on_modified(self, event):
        if not event.is_directory and self._should_watch(event.src_path):
            self._trigger()

    def on_created(self, event):
        if not event.is_directory and self._should_watch(event.src_path):
            self._trigger()

    def on_deleted(self, event):
        if not event.is_directory and self._should_watch(event.src_path):
            self._trigger()


class ProjectWatcher:
    def __init__(self):
        self._observer = Observer()
        self._watches: Dict[str, object] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._observer.start()

    def stop(self):
        self._observer.stop()
        self._observer.join()

    def watch(
        self,
        project_dir: Path,
        project_name: str,
        async_callback: Callable[[str], Awaitable[None]],
    ):
        key = str(project_dir)
        if key in self._watches or not project_dir.exists():
            return

        def sync_callback():
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    async_callback(project_name), self._loop
                )

        handler = _DebounceHandler(sync_callback)
        watch = self._observer.schedule(handler, key, recursive=True)
        self._watches[key] = watch

    def unwatch(self, project_dir: Path):
        key = str(project_dir)
        if key in self._watches:
            self._observer.unschedule(self._watches.pop(key))
