"""A folder browser for choosing which project on this machine to scan.

The dashboard's API runs on the machine whose folders are scanned, and a web page can never learn
the absolute path of a folder from the operating system's own file dialog, so the choosing is done
here: the page asks for the directories inside a folder and the person walks to the project.

Only directory names are listed (never files or their contents), and only administrators may call
it, the same people who may scan a server folder at all.
"""

from pathlib import Path
from typing import Any

MAX_ENTRIES = 500
# Folders nobody picks as a project, and that can hold hundreds of thousands of entries.
NOISE = {"node_modules", "__pycache__", ".git", ".next", "dist", "build", "venv", ".venv"}


class BrowseError(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


def _is_project(folder: Path) -> bool:
    return (folder / "prisma" / "schema.prisma").is_file() or (folder / "schema.prisma").is_file()


def browse(path: str | None, show_hidden: bool = False) -> dict[str, Any]:
    home = Path.home()
    if path is not None and "\x00" in path:
        raise BrowseError("that is not a valid path")
    folder = Path(path).expanduser() if path else home
    try:
        folder = folder.resolve()
    except OSError as error:
        raise BrowseError(f"cannot open that path: {error.strerror or error}") from error
    if not folder.is_dir():
        raise BrowseError(f"{folder} is not a folder")

    entries: list[dict[str, Any]] = []
    truncated = False
    try:
        children = sorted(folder.iterdir(), key=lambda p: p.name.lower())
    except PermissionError as error:
        raise BrowseError(f"you do not have permission to read {folder}", 403) from error
    for child in children:
        name = child.name
        if name in NOISE or (name.startswith(".") and not show_hidden):
            continue
        try:
            if not child.is_dir():
                continue
            entries.append(
                {
                    "name": name,
                    "path": str(child),
                    "is_project": _is_project(child),
                    "is_git": (child / ".git").exists(),
                }
            )
        except OSError:
            continue  # unreadable or vanished while listing: skip it
        if len(entries) >= MAX_ENTRIES:
            truncated = True
            break

    parent = folder.parent
    return {
        "path": str(folder),
        "parent": str(parent) if parent != folder else None,
        "home": str(home),
        "is_project": _is_project(folder),
        "is_git": (folder / ".git").exists(),
        "entries": entries,
        "truncated": truncated,
    }
