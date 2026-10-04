"""Create local demo keys without overwriting existing configuration."""

from __future__ import annotations

import os
import secrets

from dotenv import dotenv_values, set_key

from config import ROOT_DIR


def main() -> None:
    path = ROOT_DIR / ".env"
    values = dotenv_values(path) if path.exists() else {}
    for key in ("DISPATCH_SHARED_SECRET", "VOICE_SHARED_SECRET", "PHONE_HASH_SALT"):
        if not values.get(key) and not os.environ.get(key):
            set_key(path, key, secrets.token_urlsafe(32))
    if path.exists():
        path.chmod(0o600)
    print("Local demo access configured. Keys stay in the ignored .env file.")


if __name__ == "__main__":
    main()
