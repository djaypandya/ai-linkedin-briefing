from __future__ import annotations

import platform
import subprocess

from .exceptions import ConfigurationError


def _require_macos() -> None:
    if platform.system() != "Darwin":
        raise ConfigurationError("Keychain credential storage is currently supported on macOS only.")


def store_linkedin_password(email: str, password: str, service: str) -> None:
    _require_macos()
    if not email.strip():
        raise ConfigurationError("LinkedIn email is required to store credentials.")
    if not password:
        raise ConfigurationError("LinkedIn password cannot be empty.")

    cmd = [
        "security",
        "add-generic-password",
        "-a",
        email,
        "-s",
        service,
        "-w",
        password,
        "-U",
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise ConfigurationError(f"Failed to store LinkedIn password in Keychain: {exc.stderr.strip()}") from exc


def load_linkedin_password(email: str, service: str) -> str | None:
    _require_macos()
    if not email.strip():
        return None

    cmd = [
        "security",
        "find-generic-password",
        "-a",
        email,
        "-s",
        service,
        "-w",
    ]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return result.stdout.strip()
