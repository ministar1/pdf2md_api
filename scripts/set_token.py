from __future__ import annotations

import argparse
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
TOKEN_KEY = "MINERU_API_TOKEN"
DEFAULT_ENV_LINES = [
    "MINERU_API_TOKEN=",
    "MINERU_LANGUAGE=en",
    "MINERU_MODEL_VERSION=vlm",
    "MINERU_ENABLE_OCR=false",
    "MINERU_ENABLE_FORMULA=true",
    "MINERU_ENABLE_TABLE=true",
]


def read_lines() -> list[str]:
    if ENV_PATH.exists():
        return ENV_PATH.read_text(encoding="utf-8").splitlines()
    return DEFAULT_ENV_LINES.copy()


def update_token(lines: list[str], token: str) -> list[str]:
    updated: list[str] = []
    replaced = False
    for line in lines:
        if line.strip().startswith(f"{TOKEN_KEY}="):
            updated.append(f"{TOKEN_KEY}={token}")
            replaced = True
        else:
            updated.append(line)

    if not replaced:
        updated.insert(0, f"{TOKEN_KEY}={token}")
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or update local MinerU token config.")
    parser.add_argument("--create-empty", action="store_true", help="Create .env with default keys and an empty token.")
    args = parser.parse_args()

    if args.create_empty:
        if not ENV_PATH.exists():
            ENV_PATH.write_text("\n".join(DEFAULT_ENV_LINES) + "\n", encoding="utf-8")
            print(f"Created: {ENV_PATH}")
        else:
            print(f"Already exists: {ENV_PATH}")
        return 0

    print("Paste the new MinerU token. It will replace MINERU_API_TOKEN in .env.")
    token = input("MINERU_API_TOKEN: ").strip()
    if not token:
        print("No token entered. .env was not changed.")
        return 1

    ENV_PATH.write_text("\n".join(update_token(read_lines(), token)) + "\n", encoding="utf-8")
    print(f"Updated: {ENV_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
