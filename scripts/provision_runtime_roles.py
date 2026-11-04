"""Provision separate least-privilege DB logins into ignored local env files.

Run only on the trusted operator host. Never prints generated passwords or DSNs.
Existing secret files are verified and never overwritten; rotate them deliberately.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import psycopg
from dotenv import dotenv_values
from psycopg import sql


ROOT = Path(__file__).resolve().parents[1]
SECRET_DIR = ROOT / ".runtime"
WRITER = "yongin_collector_login"
READER = "yongin_analysis_login"


def login_url(admin_url: str, role: str, password: str) -> str:
    parsed = urlsplit(admin_url)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise ValueError("SUPABASE_DB_URL must be a PostgreSQL URL")
    admin_user = unquote(parsed.username or "")
    suffix = admin_user.split(".", 1)[1] if admin_user.startswith("postgres.") else ""
    login = role + ("." + suffix if suffix else "")
    host_port = parsed.netloc.rsplit("@", 1)[-1]
    netloc = f"{quote(login, safe='.')}:" + quote(password, safe="") + "@" + host_port
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def _write_new(path: Path, content: str) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    if os.name != "nt":
        path.chmod(0o600)


def verify_urls(writer_url: str, reader_url: str) -> None:
    if not writer_url or not reader_url:
        raise RuntimeError("runtime DSN is missing")
    with psycopg.connect(writer_url, connect_timeout=15) as conn:
        row = conn.execute(
            "select current_user, has_schema_privilege(current_user,%s,%s)",
            ("collector", "USAGE"),
        ).fetchone()
        if row != (WRITER, True):
            raise RuntimeError("writer login privilege verification failed")
    with psycopg.connect(reader_url, connect_timeout=15) as conn:
        row = conn.execute(
            "select current_user, has_schema_privilege(current_user,%s,%s), "
            "has_schema_privilege(current_user,%s,%s)",
            ("analytics", "USAGE", "collector", "USAGE"),
        ).fetchone()
        if row != (READER, True, False):
            raise RuntimeError("reader login privilege verification failed")
        conn.execute("select count(*) from analytics.giheung_events").fetchone()


def main() -> int:
    values = dotenv_values(ROOT / ".env")
    admin_url = values.get("SUPABASE_DB_URL") or ""
    if not admin_url:
        print("SUPABASE_DB_URL missing from ignored .env")
        return 2
    writer_file = SECRET_DIR / "collector.env"
    reader_file = SECRET_DIR / "analysis.env"
    if writer_file.exists() and reader_file.exists():
        writer_url = dotenv_values(writer_file).get("SUPABASE_DB_URL") or ""
        reader_url = dotenv_values(reader_file).get("SUPABASE_ANALYSIS_DB_URL") or ""
        verify_urls(writer_url, reader_url)
        print("verified existing separate writer/reader logins; credentials unchanged")
        return 0
    if writer_file.exists() or reader_file.exists():
        print("only one runtime secret file exists; refusing partial setup")
        return 3

    writer_password = secrets.token_urlsafe(32)
    reader_password = secrets.token_urlsafe(32)
    writer_url = login_url(admin_url, WRITER, writer_password)
    reader_url = login_url(admin_url, READER, reader_password)

    with psycopg.connect(admin_url, connect_timeout=15, autocommit=True) as conn:
        for login, password, group in (
            (WRITER, writer_password, "yongin_collector_writer"),
            (READER, reader_password, "yongin_analysis_reader"),
        ):
            exists = conn.execute(
                "select exists(select 1 from pg_roles where rolname=%s)", (login,)
            ).fetchone()[0]
            action = "alter" if exists else "create"
            conn.execute(
                sql.SQL(f"{action} role {{}} login password {{}}").format(
                    sql.Identifier(login), sql.Literal(password)
                )
            )
            conn.execute(
                sql.SQL("grant {} to {}").format(
                    sql.Identifier(group), sql.Identifier(login)
                )
            )

    # Verify both credentials and the role boundary before writing them locally.
    verify_urls(writer_url, reader_url)

    SECRET_DIR.mkdir(parents=True, exist_ok=True)
    _write_new(
        writer_file,
        "SUPABASE_DB_URL=" + writer_url + "\n"
        "DATA_GO_KR_SERVICE_KEY=" + (values.get("DATA_GO_KR_SERVICE_KEY") or "") + "\n",
    )
    _write_new(reader_file, "SUPABASE_ANALYSIS_DB_URL=" + reader_url + "\n")
    print("verified separate writer/reader logins and created ignored runtime env files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
