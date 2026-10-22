"""Файловая библиотека загрузок — источник правды.

Раскладка:

    <DOWNLOAD_DIR>/<аниме>/<номер>.<озвучка>.<расширение>
    например:  /ext/ani-downloads/naruto/01.anidub.mp4

Имена папок и озвучек приводятся к нижнему регистру, точки и запрещённые
символы заменяются на `_` — поэтому имя файла всегда разбирается на три части.

Модуль ничего не знает про БД, задачи и FastAPI: только ФС и `config.settings`.
"""

import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from config import settings

_FILENAME = re.compile(r"^(?P<episode>\d{1,4})\.(?P<dub>.+)\.(?P<ext>[A-Za-z0-9]{2,5})$")
_SKIP_SUFFIXES = (".part", ".ytdl", ".tmp")


def sanitize(name: object, max_len: int = 120) -> str:
    """Нижний регистр, без точек и запрещённых символов."""
    value = unicodedata.normalize("NFKC", str(name)).lower()
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f.]', "_", value)
    value = re.sub(r"[\s_]+", "_", value).strip("_ ")
    if not value:
        value = "untitled"
    if len(value) > max_len:
        value = value[:max_len].rstrip("_ ")
    return value


@dataclass(frozen=True)
class Entry:
    anime: str
    dub: str
    episode: int
    ext: str
    path: Path
    size: int
    mtime: float

    @property
    def relative(self) -> str:
        return f"{self.anime}/{self.path.name}"


class Library:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(
            root if root is not None else settings.DOWNLOAD_DIR
        ).expanduser().resolve()

    # ------------------------------------------------------------------ пути

    def anime_dir(self, anime: str) -> Path:
        return self.root / sanitize(anime)

    def target(self, anime: str, dub: str, episode: int, ext: str = "mp4") -> Path:
        extension = sanitize(ext, 5) or "mp4"
        return self.anime_dir(anime) / f"{int(episode):02d}.{sanitize(dub)}.{extension}"

    def template(self, anime: str, dub: str, episode: int) -> str:
        """Шаблон для yt-dlp: расширение подставит он сам."""
        return str(self.anime_dir(anime) / f"{int(episode):02d}.{sanitize(dub)}.%(ext)s")

    def _guard(self, path: str | Path) -> Path:
        resolved = Path(path).expanduser().resolve()
        if resolved != self.root and not resolved.is_relative_to(self.root):
            raise ValueError(f"path is outside library root: {resolved}")
        return resolved

    # --------------------------------------------------------------- парсинг

    @staticmethod
    def parse_name(filename: str) -> tuple[int, str, str] | None:
        match = _FILENAME.match(Path(filename).name)
        if match is None:
            return None
        return int(match["episode"]), match["dub"], match["ext"].lower()

    def entry(self, path: str | Path) -> Entry | None:
        resolved = self._guard(path)
        try:
            relative = resolved.relative_to(self.root)
        except ValueError:
            return None
        if len(relative.parts) != 2 or not resolved.is_file():
            return None

        parsed = self.parse_name(resolved.name)
        if parsed is None:
            return None

        episode, dub, ext = parsed
        stat = resolved.stat()
        return Entry(relative.parts[0], dub, episode, ext, resolved, stat.st_size, stat.st_mtime)

    def _iter_files(self):
        if not self.root.is_dir():
            return
        for anime_dir in self.root.iterdir():
            if not anime_dir.is_dir() or anime_dir.name.startswith("."):
                continue
            for path in anime_dir.iterdir():
                if not path.is_file():
                    continue
                if path.name.startswith(".") or path.name.lower().endswith(_SKIP_SUFFIXES):
                    continue
                yield path

    # ------------------------------------------------------------- чтение ФС

    def scan(self) -> list[Entry]:
        found = [entry for path in self._iter_files() if (entry := self.entry(path))]
        found.sort(key=lambda item: (item.anime, item.dub, item.episode))
        return found

    def search(
        self,
        *,
        anime: str | None = None,
        dub: str | None = None,
        episode: int | None = None,
        query: str | None = None,
    ) -> list[Entry]:
        anime_key = sanitize(anime) if anime is not None else None
        dub_key = sanitize(dub) if dub is not None else None
        needle = query.strip().lower() if query else None

        result = []
        for entry in self.scan():
            if anime_key is not None and entry.anime != anime_key:
                continue
            if dub_key is not None and entry.dub != dub_key:
                continue
            if episode is not None and entry.episode != episode:
                continue
            if needle and needle not in entry.relative:
                continue
            result.append(entry)
        return result

    def variants(self, anime: str, dub: str, episode: int) -> list[Entry]:
        return sorted(
            self.search(anime=anime, dub=dub, episode=episode),
            key=lambda item: (item.ext != "mp4", item.path.name),
        )

    def exists(self, anime: str, dub: str, episode: int) -> Path | None:
        variants = self.variants(anime, dub, episode)
        return variants[0].path if variants else None

    def get(self, anime: str, dub: str, episode: int) -> Entry | None:
        variants = self.variants(anime, dub, episode)
        return variants[0] if variants else None

    def episodes(self, anime: str, dub: str | None = None) -> list[int]:
        numbers = {entry.episode for entry in self.search(anime=anime, dub=dub)}
        return sorted(numbers)

    def animes(self) -> list[str]:
        return sorted({entry.anime for entry in self.scan()})

    def dubs(self, anime: str) -> list[str]:
        return sorted({entry.dub for entry in self.search(anime=anime)})

    def total_size(self) -> int:
        return sum(entry.size for entry in self.scan())

    def dir_mtime(self, anime: str) -> float:
        directory = self.anime_dir(anime)
        try:
            return directory.stat().st_mtime
        except OSError:
            return 0.0

    # ----------------------------------------------------------- изменение ФС

    def delete(self, path: str | Path | Entry) -> bool:
        target = self._guard(path.path if isinstance(path, Entry) else path)
        if not target.is_file():
            return False
        target.unlink()
        self._prune_empty(target.parent)
        return True

    def delete_episode(self, anime: str, dub: str, episode: int) -> int:
        removed = 0
        for entry in self.variants(anime, dub, episode):
            if self.delete(entry):
                removed += 1
        return removed

    def _prune_empty(self, directory: Path) -> None:
        current = directory
        while current != self.root and current.is_relative_to(self.root):
            try:
                current.rmdir()
            except OSError:
                return
            current = current.parent

    def ensure(self, path: str | Path) -> Path:
        target = self._guard(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def free_space(self) -> int:
        base = self.root if self.root.exists() else self.root.parent
        return shutil.disk_usage(base).free


library = Library()


if __name__ == "__main__":
    entries = library.scan()
    print(f"root: {library.root}")
    print(f"files: {len(entries)}, size: {library.total_size() / 1024 / 1024:.1f} MB")
    for item in entries:
        print(f"  {item.anime} #{item.episode:02d} {item.dub}.{item.ext} {item.size} B")
