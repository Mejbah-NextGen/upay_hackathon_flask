"""Portable, disposable PostgreSQL migration/concurrency/HTTP load evidence.

Run: python scripts/postgres_qa.py --download-binaries
Only a fresh loopback cluster under tmp/infrastructure-qa is started. Existing
PostgreSQL services, clusters and databases are never contacted or modified.
"""

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
from urllib.request import urlopen
from uuid import uuid4
import zipfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
QA_ROOT = PROJECT_ROOT / "tmp" / "infrastructure-qa"
OFFICIAL_PAGE = "https://www.enterprisedb.com/download-postgresql-binaries"
OFFICIAL_LINK = "https://sbp.enterprisedb.com/getfile.jsp?fileid=1260609"
ARCHIVE_URL = "https://get.enterprisedb.com/postgresql/postgresql-18.6-5-windows-x64-binaries.zip"
CREATE_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def checked_child(path, parent):
    path, parent = Path(path).resolve(), Path(parent).resolve()
    if path == parent or not path.is_relative_to(parent):
        raise ValueError("QA path must stay inside its dedicated workspace directory.")
    return path


def download_binaries():
    QA_ROOT.mkdir(parents=True, exist_ok=True)
    target = QA_ROOT / "postgres-binaries"
    installed = target / "pgsql" / "bin" / "initdb.exe"
    if installed.exists():
        return target / "pgsql" / "bin"
    with urlopen(OFFICIAL_PAGE, timeout=30) as response:
        page = response.read().decode()
    if "Version <!-- -->18.6" not in page or OFFICIAL_LINK not in page:
        raise ValueError("Official page no longer lists the reviewed archive; review source before download.")
    archive = QA_ROOT / "postgresql-18.6-5-windows-x64-binaries.zip"
    checksum = hashlib.sha256()
    if archive.exists() and not zipfile.is_zipfile(archive):
        if archive.is_symlink() or checked_child(archive, QA_ROOT) != archive:
            raise ValueError("Invalid archive cleanup target.")
        archive.unlink()
    if not archive.exists():
        with urlopen(OFFICIAL_LINK, timeout=60) as response:
            if response.url != ARCHIVE_URL or response.headers.get("Content-Type") != "application/zip":
                raise ValueError("Official archive redirect changed unexpectedly.")
            with archive.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
    with archive.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            checksum.update(chunk)
    target.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as source:
        for row in source.infolist():
            parts = PurePosixPath(row.filename).parts
            if (len(parts) < 2 or parts[0] != "pgsql" or parts[1] not in {"bin", "lib", "share"}
                    or any(part in {"..", "."} for part in parts) or "\\" in row.filename):
                continue
            if stat.S_ISLNK(row.external_attr >> 16):
                raise ValueError("Unexpected archive symlink.")
            destination = checked_child(target.joinpath(*parts), target)
            if row.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with source.open(row) as input_file, destination.open("wb") as output_file:
                    shutil.copyfileobj(input_file, output_file)
    (QA_ROOT / "postgres-binaries-source.json").write_text(json.dumps({
        "official_page": OFFICIAL_PAGE, "official_download_link": OFFICIAL_LINK, "archive_url": ARCHIVE_URL,
        "archive_sha256": checksum.hexdigest(), "bytes": archive.stat().st_size,
        "extracted_components": ["pgsql/bin", "pgsql/lib", "pgsql/share"],
        "installed_service": False, "used_existing_cluster": False,
    }, indent=2) + "\n", encoding="utf-8")
    return target / "pgsql" / "bin"


def pg_bin_path(download=False):
    candidates = [Path(os.environ["QA_PG_BIN"])] if os.environ.get("QA_PG_BIN") else []
    candidates += [QA_ROOT / "postgres-binaries" / "pgsql" / "bin", Path(r"C:\Program Files\PostgreSQL\18\bin")]
    for folder in candidates:
        if all((folder / filename).is_file() for filename in ("initdb.exe", "pg_ctl.exe")):
            return folder
    if download:
        return download_binaries()
    raise RuntimeError("PostgreSQL binaries absent. Use --download-binaries or QA_PG_BIN for reviewed portable binaries.")


def hidden_run(arguments, *, env=None, timeout=60):
    return subprocess.run([str(item) for item in arguments], cwd=PROJECT_ROOT, env=env,
                          creationflags=CREATE_FLAGS, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=timeout)


def pg_control(arguments):
    # On Windows a postmaster descendant can inherit PIPE handles even after
    # pg_ctl exits, so communicate() may hang waiting for EOF. The server has its
    # own -l log; startup/stop control output can safely go to DEVNULL.
    return subprocess.run([str(item) for item in arguments], cwd=PROJECT_ROOT,
                          creationflags=CREATE_FLAGS, stdin=subprocess.DEVNULL,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)


@contextmanager
def isolated_postgres(folder):
    import psycopg
    from psycopg import sql
    from sqlalchemy.engine import URL
    QA_ROOT.mkdir(parents=True, exist_ok=True)
    run_root = checked_child(QA_ROOT / ("pg-run-" + uuid4().hex), QA_ROOT)
    run_root.mkdir()
    data = checked_child(run_root / "data", run_root)
    password_file = run_root / "bootstrap-password.txt"
    password = secrets.token_urlsafe(40)
    password_file.write_text(password + "\n", encoding="utf-8")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    started = False
    try:
        initialized = hidden_run([folder / "initdb.exe", "-D", data, "-U", "upay_qa",
                                  "--pwfile", password_file, "-A", "scram-sha-256", "--no-locale", "-E", "UTF8"], timeout=120)
        if initialized.returncode:
            raise RuntimeError("Isolated initdb failed: " + initialized.stderr.replace(password, "[redacted]")[-1500:])
        password_file.unlink(missing_ok=True)
        with (data / "postgresql.conf").open("a", encoding="utf-8") as config:
            config.write(f"\nlisten_addresses='127.0.0.1'\nport={port}\nunix_socket_directories=''\nfsync=on\nsynchronous_commit=on\n")
        startup = pg_control([folder / "pg_ctl.exe", "-D", data, "-l", run_root / "postgres.log", "-w", "start"])
        if startup.returncode:
            raise RuntimeError("Isolated PostgreSQL start failed; review its isolated server log.")
        started = True
        database = "upay_qa_" + uuid4().hex
        with psycopg.connect(host="127.0.0.1", port=port, dbname="postgres", user="upay_qa", password=password, autocommit=True, connect_timeout=5) as connection:
            connection.execute(sql.SQL("CREATE DATABASE {} ENCODING 'UTF8'").format(sql.Identifier(database)))
            version = connection.execute("SHOW server_version").fetchone()[0]
        with psycopg.connect(host="127.0.0.1", port=port, dbname=database, user="upay_qa", password=password, connect_timeout=5) as connection:
            connection.execute("CREATE TABLE _qa_cluster_guard (purpose text NOT NULL)")
            connection.execute("INSERT INTO _qa_cluster_guard VALUES ('upayx-isolated-qa-v1')")
        url = URL.create("postgresql+psycopg", username="upay_qa", password=password,
                         host="127.0.0.1", port=port, database=database).render_as_string(hide_password=False)
        yield url, version
    finally:
        password_file.unlink(missing_ok=True)
        if started or (data / "postmaster.pid").exists():
            stopped = pg_control([folder / "pg_ctl.exe", "-D", data, "-m", "fast", "-w", "stop"])
            if stopped.returncode:
                raise RuntimeError("Temporary PostgreSQL could not be stopped; keeping only its isolated QA directory for review.")
        if run_root.is_symlink() or checked_child(run_root, QA_ROOT) != run_root:
            raise ValueError("Unsafe temporary cluster cleanup path.")
        # Native Python cleanup, with one verified absolute subtree, never shell
        # deletion or a path assembled from a database/service setting.
        shutil.rmtree(run_root)


def run_qa(folder):
    import psycopg
    from sqlalchemy.engine import make_url
    with isolated_postgres(folder) as (url, version):
        env = {**os.environ, "DATABASE_URL": url, "QA_POSTGRES_URL": url, "QA_DATABASE_URL": url,
               "AUTO_CREATE_SCHEMA": "0", "SEED_DEMO_DATA": "0"}
        migration = hidden_run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, timeout=120)
        password = make_url(url).password
        (QA_ROOT / "postgres-migration.log").write_text((migration.stdout + migration.stderr).replace(password, "[redacted]"), encoding="utf-8")
        if migration.returncode:
            raise RuntimeError("PostgreSQL migration failed; see the sanitized QA migration log.")
        parsed = make_url(url)
        with psycopg.connect(host=parsed.host, port=parsed.port, dbname=parsed.database, user=parsed.username, password=parsed.password, connect_timeout=5) as connection:
            revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            table_count = connection.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'").fetchone()[0]
        tests = hidden_run([sys.executable, "-m", "unittest", "tests.test_postgres", "-v"], env=env, timeout=120)
        (QA_ROOT / "postgres-tests.log").write_text((tests.stdout + tests.stderr).replace(password, "[redacted]"), encoding="utf-8")
        if tests.returncode:
            raise RuntimeError("PostgreSQL concurrency QA failed; see the sanitized QA tests log.")
        load = hidden_run([sys.executable, "scripts/load_test.py", "--output", "tmp/infrastructure-qa/load-postgres.json"], env=env, timeout=120)
        if load.returncode:
            (QA_ROOT / "postgres-load.log").write_text((load.stdout+load.stderr).replace(password, "[redacted]"), encoding="utf-8")
            raise RuntimeError("PostgreSQL HTTP load invariants failed; see the QA load report/log.")
        load_result = json.loads((QA_ROOT / "load-postgres.json").read_text(encoding="utf-8"))
        provenance_path = QA_ROOT / "postgres-binaries-source.json"
        result = {"schema_version": 1, "postgresql_version": version, "migration_revision": revision,
                  "migrated_table_count_including_alembic_and_guard": table_count,
                  "concurrency_tests_passed": 6, "test_types": ["duplicate schedule claim", "competing guarded debits",
                  "ledger/audit failure rollback", "API duplicate-key race across eight connections",
                  "provider outbox competing leases", "expired lease/lost-response reconciliation"],
                  "loopback_only": True, "temporary_cluster": True, "used_existing_cluster": False,
                  "durability_settings": {"fsync": True, "synchronous_commit": True},
                  "load_report": "tmp/infrastructure-qa/load-postgres.json", "load_invariants_passed": load_result["all_invariants_passed"],
                  "binary_provenance": json.loads(provenance_path.read_text(encoding="utf-8")) if provenance_path.exists() else {"source": "operator supplied QA_PG_BIN"},
                  "scope": "local fixture evidence, not managed PostgreSQL failover or production capacity certification"}
    result["temporary_cluster_stopped_and_removed"] = True
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-binaries", action="store_true")
    parser.add_argument("--output", type=Path, default=QA_ROOT / "postgres-qa.json")
    args = parser.parse_args()
    try:
        folder = pg_bin_path(args.download_binaries)
        result = run_qa(folder)
    except Exception as exc:
        # Do not echo DSNs, environment credentials or arbitrary subprocess args.
        print(f"QA failed ({type(exc).__name__}): {str(exc) if isinstance(exc, (RuntimeError, ValueError)) else 'see sanitized logs'}")
        sys.exit(1)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
