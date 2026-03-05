from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json_log(log_dir: Path, filename: str, payload: dict[str, Any]) -> Path:
    ensure_dir(log_dir)
    target = log_dir / filename
    content = {
        "logged_at": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    target.write_text(json.dumps(content, indent=2), encoding="utf-8")
    return target
