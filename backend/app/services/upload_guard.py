"""Upload validation: size, extension, content signature, compression bombs.

Review item 7 found the upload path had no size limit, no MIME or content-signature
check, and no archive-expansion guard. Every upload in the application funnels
through :func:`store_upload` so those checks cannot be forgotten at a new call site.
"""

from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterable

from backend.app.domain.codes import ErrorCode

#: Magic-number prefixes per accepted extension. ``None`` means the format has no
#: reliable signature (CSV and JSON are plain text) and is validated by decoding
#: a prefix as UTF-8 instead.
CONTENT_SIGNATURES: dict[str, tuple[bytes, ...] | None] = {
    ".csv": None,
    ".json": None,
    ".xlsx": (b"PK\x03\x04",),  # zip container
    ".xls": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),  # OLE2 compound file
    ".parquet": (b"PAR1",),  # Apache Parquet magic bytes
    ".pdf": (b"%PDF-",),
}

TEXT_SNIFF_BYTES = 8192
COPY_CHUNK_BYTES = 1024 * 1024


class UploadRejected(ValueError):
    """An upload failed a guard. Carries a stable :class:`ErrorCode`."""

    def __init__(self, code: ErrorCode, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class StoredUpload:
    path: Path
    filename: str
    size_bytes: int
    suffix: str


def safe_filename(raw: str | None, *, fallback: str = "uploaded-file") -> str:
    """Reduce a client-supplied name to a single safe path component."""
    name = Path(str(raw or "")).name.strip()
    name = name.replace("\x00", "")
    if not name or name in {".", ".."}:
        return fallback
    return name


def _check_extension(suffix: str, allowed: Iterable[str]) -> None:
    allowed_set = {item.lower() for item in allowed}
    if suffix not in allowed_set:
        raise UploadRejected(
            ErrorCode.UNSUPPORTED_FORMAT,
            f"Unsupported file format '{suffix}'. Allowed: {sorted(allowed_set)}.",
        )


def _check_signature(path: Path, suffix: str) -> None:
    """Verify the bytes match the extension, so ``.csv`` is not a renamed binary."""
    expected = CONTENT_SIGNATURES.get(suffix, ())
    with path.open("rb") as handle:
        prefix = handle.read(TEXT_SNIFF_BYTES)

    if not prefix:
        raise UploadRejected(ErrorCode.VALIDATION_FAILED, "Uploaded file is empty.")

    if expected is None:
        # Plain-text formats: a NUL byte or undecodable prefix means this is not
        # the text file the extension claims.
        if b"\x00" in prefix:
            raise UploadRejected(
                ErrorCode.CONTENT_TYPE_REJECTED,
                f"'{suffix}' must be text but the content is binary.",
            )
        try:
            prefix.decode("utf-8")
        except UnicodeDecodeError as exc:
            # A multi-byte character may straddle the sniff boundary. Trim to
            # exactly where decoding failed and retry: UTF-8 decode stops at the
            # first bad byte, so everything before ``exc.start`` is valid. A
            # fixed -4 trim is not enough — several multi-byte characters can
            # straddle the boundary at once.
            try:
                prefix[: exc.start].decode("utf-8")
            except UnicodeDecodeError as exc2:
                raise UploadRejected(
                    ErrorCode.CONTENT_TYPE_REJECTED,
                    f"'{suffix}' content is not valid UTF-8 text.",
                ) from exc2
        return

    if not any(prefix.startswith(signature) for signature in expected):
        raise UploadRejected(
            ErrorCode.CONTENT_TYPE_REJECTED,
            f"File content does not match the '{suffix}' format signature.",
        )


def _check_compression_bomb(path: Path, suffix: str, max_ratio: float) -> None:
    """Reject archives (``.xlsx`` is a zip) that expand far beyond their size."""
    if suffix != ".xlsx" or not zipfile.is_zipfile(path):
        return
    compressed = max(path.stat().st_size, 1)
    try:
        with zipfile.ZipFile(path) as archive:
            uncompressed = sum(info.file_size for info in archive.infolist())
    except zipfile.BadZipFile as exc:
        raise UploadRejected(
            ErrorCode.CONTENT_TYPE_REJECTED, "Archive is corrupt or unreadable."
        ) from exc
    ratio = uncompressed / compressed
    if ratio > max_ratio:
        raise UploadRejected(
            ErrorCode.COMPRESSION_RATIO_REJECTED,
            f"Archive expands {ratio:.0f}x (limit {max_ratio:.0f}x).",
        )


def _stream_to_disk(source: BinaryIO, target: Path, max_bytes: int) -> int:
    """Copy at most ``max_bytes``, deleting the partial file if the cap is hit.

    The cap is enforced while streaming rather than by reading
    ``Content-Length``, which a client controls and can understate.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    try:
        with target.open("wb") as handle:
            while True:
                chunk = source.read(COPY_CHUNK_BYTES)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise UploadRejected(
                        ErrorCode.FILE_TOO_LARGE,
                        f"File exceeds the {max_bytes} byte upload limit.",
                    )
                handle.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return written


def store_upload(
    *,
    source: BinaryIO,
    filename: str | None,
    target_path: Path,
    allowed_suffixes: Iterable[str],
    max_bytes: int,
    max_compression_ratio: float,
) -> StoredUpload:
    """Validate and persist one upload, or raise :class:`UploadRejected`.

    Order matters: the extension is checked before any bytes are written, the
    size cap is enforced while streaming, and signature/bomb checks run on the
    persisted file. A rejected upload never leaves a file behind.
    """
    name = safe_filename(filename)
    suffix = Path(name).suffix.lower()
    _check_extension(suffix, allowed_suffixes)

    size = _stream_to_disk(source, target_path, max_bytes)
    try:
        _check_signature(target_path, suffix)
        _check_compression_bomb(target_path, suffix, max_compression_ratio)
    except Exception:
        target_path.unlink(missing_ok=True)
        raise

    return StoredUpload(path=target_path, filename=name, size_bytes=size, suffix=suffix)


def resolve_managed_path(relative_path: str, managed_root: Path) -> Path:
    """Resolve a server-side import path inside ``managed_root``, or raise.

    Review item 7: the import endpoint used to accept any path the server could
    read. Both the root and the candidate are fully resolved before comparison so
    ``..`` segments and symlinks cannot escape.
    """
    raw = str(relative_path or "").strip()
    if not raw:
        raise UploadRejected(ErrorCode.PATH_NOT_ALLOWED, "No import path was supplied.")

    root = managed_root.resolve()
    candidate = Path(raw)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (root / candidate).resolve()

    if resolved != root and root not in resolved.parents:
        raise UploadRejected(
            ErrorCode.PATH_NOT_ALLOWED,
            f"Import paths must live under the managed data directory ({root}).",
        )
    if not resolved.is_file():
        raise UploadRejected(ErrorCode.NOT_FOUND, "Import source file does not exist.")
    return resolved


def copy_managed_file(
    *,
    source: Path,
    target_path: Path,
    allowed_suffixes: Iterable[str],
    max_bytes: int,
    max_compression_ratio: float,
) -> StoredUpload:
    """Apply the upload guards to a file already inside the managed directory."""
    suffix = source.suffix.lower()
    _check_extension(suffix, allowed_suffixes)
    size = source.stat().st_size
    if size > max_bytes:
        raise UploadRejected(
            ErrorCode.FILE_TOO_LARGE,
            f"File exceeds the {max_bytes} byte import limit.",
        )

    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target_path)
    try:
        _check_signature(target_path, suffix)
        _check_compression_bomb(target_path, suffix, max_compression_ratio)
    except Exception:
        target_path.unlink(missing_ok=True)
        raise

    return StoredUpload(
        path=target_path, filename=source.name, size_bytes=size, suffix=suffix
    )
