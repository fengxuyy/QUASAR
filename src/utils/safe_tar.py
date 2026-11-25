"""Safe tar extraction helpers (path containment / zip-slip prevention)."""

from __future__ import annotations

import os
import tarfile
from pathlib import Path
from typing import BinaryIO, Union


def _normalize_member_name(name: str) -> str | None:
    """Return a clean relative path for a tar member, or None to skip it.

    Materials Cloud SSSP archives use member names like ``./Si.UPF`` and a
    directory entry named ``.``. Those must not be rejected or nested oddly.
    """
    if not name:
        return None
    # Normalize separators and strip leading ./ clutter.
    cleaned = name.replace("\\", "/").lstrip("/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    cleaned = cleaned.strip()
    if not cleaned or cleaned in {".", "./"}:
        return None
    parts = [part for part in cleaned.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        return None
    return "/".join(parts)


def _resolve(path: Path) -> Path:
    """Resolve a path without requiring it to exist yet."""
    try:
        return path.resolve(strict=False)  # type: ignore[call-arg]
    except TypeError:
        return Path(os.path.abspath(str(path)))


def _is_within_directory(directory: Path, target: Path) -> bool:
    try:
        directory_r = _resolve(directory)
        target_r = _resolve(target)
        target_r.relative_to(directory_r)
        return True
    except (ValueError, OSError):
        return False


def safe_extractall(
    tar: tarfile.TarFile,
    path: Union[str, Path],
) -> None:
    """Extract tar members only if every member stays under ``path``.

    Rejects absolute paths, ``..`` traversal, and link targets outside the root.
    Normalizes Materials Cloud-style ``./file.UPF`` member names.
    Prefer Python 3.12+ ``filter='data'`` when available; fall back to a
    member-by-member extract if filter mode fails.
    """
    dest = Path(path)
    dest.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest.resolve()

    # Rewrite members in-place so extractall writes to clean relative paths.
    safe_members: list[tarfile.TarInfo] = []
    for member in tar.getmembers():
        normalized = _normalize_member_name(member.name)
        if normalized is None:
            continue
        member.name = normalized
        member_path = dest / normalized
        if not _is_within_directory(dest_resolved, member_path):
            raise RuntimeError(f"Blocked tar member path escape: {member.name!r}")
        if member.issym() or member.islnk():
            link_target = Path(member.linkname)
            if link_target.is_absolute():
                raise RuntimeError(f"Blocked absolute tar link: {member.name!r}")
            linked = (member_path.parent / link_target)
            if not _is_within_directory(dest_resolved, linked):
                raise RuntimeError(f"Blocked tar link escape: {member.name!r} -> {member.linkname!r}")
        safe_members.append(member)

    if not safe_members:
        raise RuntimeError("Tar archive contained no extractable members.")

    # Python 3.12+ supports filter= to block dangerous members by default.
    try:
        tar.extractall(path=dest, members=safe_members, filter="data")  # type: ignore[call-arg]
    except TypeError:
        tar.extractall(path=dest, members=safe_members)
    except Exception:
        # Some interpreters choke on filter='data' with rewritten members; do a
        # controlled member loop without the filter.
        for member in safe_members:
            tar.extract(member, path=dest)


def safe_extract_tar_path(archive_path: Union[str, Path], dest_path: Union[str, Path]) -> None:
    with tarfile.open(archive_path, "r:*") as tar:
        safe_extractall(tar, dest_path)


def safe_extract_tar_bytes(data: bytes, dest_path: Union[str, Path]) -> None:
    import io

    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tar:
        safe_extractall(tar, dest_path)
