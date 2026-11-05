"""Provision local least-privilege logins after restoring the collector dump."""

import secrets
from pathlib import Path
from urllib.parse import quote

import psycopg
from dotenv import dotenv_values
from psycopg import sql


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"


def main() -> None:
    admin_secret = dotenv_values(RUNTIME / "local-postgres.env")
    admin_password = admin_secret.get("POSTGRES_PASSWORD")
    if not admin_password:
        raise RuntimeError("local postgres secret missing")
    admin_url = "postgresql://postgres:" + quote(admin_password, safe="") + "@127.0.0.1:5435/yongin"
    writer_secret = RUNTIME / "local-collector.env"
    reader_secret = RUNTIME / "local-analysis.env"
    if writer_secret.exists() or reader_secret.exists():
        if not writer_secret.exists() or not reader_secret.exists():
            raise RuntimeError("partial local role secrets")
        print("local role secrets already exist; not rotating")
        return
    writer_password = secrets.token_urlsafe(32)
    reader_password = secrets.token_urlsafe(32)
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute("revoke all on schema collector, analytics from public")
        for role in ("yongin_collector_writer", "yongin_analysis_reader"):
            conn.execute(sql.SQL("create role {} nologin").format(sql.Identifier(role)))
        conn.execute("grant usage on schema collector to yongin_collector_writer")
        conn.execute("grant select, insert, update, delete on all tables in schema collector to yongin_collector_writer")
        conn.execute("grant usage, select on all sequences in schema collector to yongin_collector_writer")
        conn.execute("grant usage on schema analytics to yongin_analysis_reader")
        conn.execute("grant select on all tables in schema analytics to yongin_analysis_reader")
        for login, password, group in (
            ("yongin_collector_login", writer_password, "yongin_collector_writer"),
            ("yongin_analysis_login", reader_password, "yongin_analysis_reader"),
        ):
            conn.execute(sql.SQL("create role {} login password {}").format(
                sql.Identifier(login), sql.Literal(password)))
            conn.execute(sql.SQL("grant {} to {}").format(sql.Identifier(group), sql.Identifier(login)))
    local_host = "127.0.0.1:5435"
    local_docker = "yongin-local-postgres:5432"
    writer_host_url = f"postgresql://yongin_collector_login:{quote(writer_password, safe='')}@{local_host}/yongin"
    reader_host_url = f"postgresql://yongin_analysis_login:{quote(reader_password, safe='')}@{local_host}/yongin"
    writer_docker_url = f"postgresql://yongin_collector_login:{quote(writer_password, safe='')}@{local_docker}/yongin"
    reader_docker_url = f"postgresql://yongin_analysis_login:{quote(reader_password, safe='')}@{local_docker}/yongin"
    with psycopg.connect(writer_host_url) as conn:
        conn.execute("select count(*) from collector.dataset_records").fetchone()
    with psycopg.connect(reader_host_url) as conn:
        conn.execute("select count(*) from analytics.current_dataset_records").fetchone()
        try:
            conn.execute("select count(*) from collector.dataset_records").fetchone()
        except psycopg.errors.InsufficientPrivilege:
            conn.rollback()
        else:
            raise RuntimeError("local reader can access collector schema")
    old = dotenv_values(RUNTIME / "collector.env")
    writer_secret.write_text("SUPABASE_DB_URL=" + writer_docker_url + "\nDATA_GO_KR_SERVICE_KEY=" +
                             (old.get("DATA_GO_KR_SERVICE_KEY") or "") + "\n", encoding="utf-8")
    reader_secret.write_text("DATABASE_URL=" + reader_docker_url + "\n", encoding="utf-8")
    (RUNTIME / "local-host.env").write_text("WRITER_URL=" + writer_host_url +
                                             "\nREADER_URL=" + reader_host_url + "\n", encoding="utf-8")
    print("local writer and reader roles verified; ignored secrets created")


if __name__ == "__main__":
    main()
