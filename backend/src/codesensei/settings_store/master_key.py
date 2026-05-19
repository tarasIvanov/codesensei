"""Resolve the MASTER_KEY from env or a persisted keyfile, auto-generating once if needed.

Precedence:
    1. `MASTER_KEY` env var (if non-empty, used as-is — no file I/O).
    2. `MASTER_KEY_FILE` env var: read file if present. If missing, generate a fresh
       Fernet key, write the file with 0600 perms, and return it.
    3. Neither set → empty string (settings_store stays locked, same as v1).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet

_logger = logging.getLogger(__name__)


def resolve_from_file(path_str: str) -> str:
    """Read or create a Fernet keyfile at `path_str`. Returns the key string."""
    path = Path(path_str)
    if path.exists():
        try:
            key = path.read_text(encoding="utf-8").strip()
            if key:
                return key
        except OSError as exc:
            _logger.warning("master_key_read_failed path=%s err=%s", path_str, exc)
            return ""

    path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key().decode()
    try:
        with os.fdopen(
            os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
            "w",
            encoding="utf-8",
        ) as fh:
            fh.write(key)
        _logger.info("master_key_generated path=%s", path_str)
    except FileExistsError:
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            _logger.warning("master_key_read_after_race_failed err=%s", exc)
            return ""
    except OSError as exc:
        _logger.warning("master_key_write_failed path=%s err=%s", path_str, exc)
        return ""
    return key
