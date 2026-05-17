"""Async git-clone + local-path source materialisation."""
from __future__ import annotations

import asyncio
import shutil
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from codesensei.indexing.errors import IndexError, IndexErrorCategory


def normalise_source(source: str) -> tuple[str, Literal["https", "local"]]:
    """Decide how to materialise the source.

    Strip trailing ``.git`` and trailing slash for canonical storage.
    """
    source = source.strip()
    if not source:
        raise IndexError(IndexErrorCategory.INVALID_INPUT, "Source must be a non-empty string.")
    if source.startswith("https://") or source.startswith("http://"):
        canonical = source.rstrip("/")
        if canonical.endswith(".git"):
            canonical = canonical[:-4]
        return canonical, "https"
    if source.startswith("git@") or source.startswith("ssh://"):
        raise IndexError(
            IndexErrorCategory.INVALID_INPUT,
            "SSH/authenticated clones are not supported (deferred). Use a public HTTPS URL "
            "or a local mounted path.",
        )
    if source.startswith("/"):
        return source.rstrip("/") or "/", "local"
    raise IndexError(
        IndexErrorCategory.INVALID_INPUT,
        f"Unsupported source format: {source!r}. Expected an https:// URL or an absolute path.",
    )


@asynccontextmanager
async def materialise(
    source: str, source_kind: Literal["https", "local"], default_branch: str | None
) -> AsyncIterator[Path]:
    """Yield a `Path` to the working tree; clean it up on exit if it was cloned."""
    if source_kind == "local":
        path = Path(source)
        # Path existence/type are cheap syscalls — running them inside an async function is fine.
        if not path.exists() or not path.is_dir():  # noqa: ASYNC240
            raise IndexError(
                IndexErrorCategory.CLONE_FAILED, f"Local path does not exist: {source}"
            )
        yield path
        return

    tmpdir = Path(tempfile.mkdtemp(prefix="codesensei-clone-"))
    try:
        args = ["git", "clone", "--depth", "1", "--filter=blob:none"]
        if default_branch:
            args.extend(["-b", default_branch])
        # Re-append .git so we hit the canonical clone URL.
        clone_url = source if source.endswith(".git") else source + ".git"
        args.extend([clone_url, str(tmpdir)])
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            stderr_text = stderr.decode("utf-8", errors="replace").strip()
            first_line = stderr_text.splitlines()[0] if stderr_text else "unknown error"
            raise IndexError(
                IndexErrorCategory.CLONE_FAILED,
                f"git clone failed for {source!r}: {first_line}",
                retryable=True,
            )
        yield tmpdir
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
