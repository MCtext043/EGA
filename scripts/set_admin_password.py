"""Set or rotate the admin password in the local .env file."""

import getpass
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.admin import hash_password


def main() -> None:
    password = getpass.getpass("Новый пароль администратора (минимум 12 символов): ")
    if len(password) < 12:
        raise SystemExit("Пароль должен содержать не менее 12 символов.")
    if password != getpass.getpass("Повторите пароль: "):
        raise SystemExit("Пароли не совпадают.")

    env_file = Path(__file__).resolve().parent.parent / ".env"
    existing = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    existing = [line for line in existing if not line.startswith(("ADMIN_PASSWORD_HASH=", "ADMIN_SESSION_SECRET="))]
    existing.extend([
        f"ADMIN_PASSWORD_HASH='{hash_password(password)}'",
        f"ADMIN_SESSION_SECRET='{secrets.token_hex(32)}'",
    ])
    env_file.write_text("\n".join(existing) + "\n", encoding="utf-8")
    print("Пароль установлен. Перезапустите сервер; прежние сессии будут завершены.")


if __name__ == "__main__":
    main()
