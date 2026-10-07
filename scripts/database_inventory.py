"""Read-only SQLite snapshots and isolated ORM schema catalog; never seed/migrate.

No account identifiers, credentials, conversation text or record samples are
exported. An active WAL is refused: take a reviewed SQLite backup first.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import inspect
import json
from pathlib import Path
import re
import sqlite3
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


PURPOSES = {
    "users": ("Wallet and ledger", "Account identity, password hash, verification and current synthetic wallet balance."),
    "transactions": ("Wallet and ledger", "Wallet receipts; only SUCCESS records affect the balance. OUT includes amount plus fee."),
    "wallet_opening_balances": ("Demo provenance", "Explicit opening balance anchors for exact per-account ledger reconciliation."),
    "demo_datasets": ("Demo provenance", "Synthetic generator version, covered dates and dataset provenance; no real-user validation implied."),
    "recipient_registrations": ("Payments and scheduling", "Recipient/service registration and payment eligibility checks."),
    "scheduled_payments": ("Payments and scheduling", "Individual installments, due dates, recurrence, completion and unique linked receipt."),
    "wallet_submissions": ("Payments and scheduling", "Per-user wallet form idempotency and completed transaction link."),
    "savings_plans": ("Payments and scheduling", "Stored fixed-contribution savings goals and estimated returns; saving a plan does not move money."),
    "pay_later_accounts": ("Payments and scheduling", "Outstanding deferred purchase balance for each synthetic wallet; the service enforces its limit."),
    "pay_later_purchases": ("Payments and scheduling", "Merchant invoice purchases, amount due and repayment state."),
    "payment_invoices": ("Payments and scheduling", "User-owned paid bill/service receipt metadata and unique provider references."),
    "payment_submissions": ("Payments and scheduling", "User-owned bill payment submission idempotency and receipt linkage."),
    "user_profiles": ("Profile and preferences", "User-owned nickname, address and uploaded photo metadata/content."),
    "user_preferences": ("Profile and preferences", "Persistent notification-enabled preference; this setting does not control authentication."),
    "display_preferences": ("Profile and preferences", "Persistent language and theme choices."),
    "notification_read_states": ("Notifications", "Per-user notification read-through timestamp."),
    "notification_read_receipts": ("Notifications", "Per-user individual notification acknowledgement keys."),
    "assistant_conversations": ("AI privacy and guidance", "Bounded conversation content; encrypted when deployment keys are configured."),
    "ai_consents": ("AI privacy and guidance", "Separate, revocable hosted-assistant and model-research purpose consent."),
    "ai_conversation_retention": ("AI privacy and guidance", "Conversation expiry; chat retention is seven days by default."),
    "ai_conversation_controls": ("AI privacy and guidance", "Content-free erasure generation prevents in-flight requests recreating deleted chat."),
    "ai_governance_events": ("AI privacy and guidance", "Content-free consent, safety and privacy observations with bounded retention."),
    "pilot_participants": ("Pilot measurement", "Experiment cohort, variant, source classification and research consent."),
    "pilot_events": ("Pilot measurement", "Deduplicated task, completion and retention observations; synthetic and real cohorts remain distinct."),
    "pilot_feedback": ("Pilot measurement", "Participant-reported research observations; values are not evidence of controlled uplift."),
    "api_tokens": ("Provider and API integration", "Expiring/revocable scoped bearer credential hashes; raw bearer tokens are not stored."),
    "api_idempotency": ("Provider and API integration", "Unique token/key request digest and encrypted response replay cache."),
    "provider_intents": ("Provider and API integration", "Explicit provider authorization and status; independent of synthetic wallet money movement."),
    "provider_outbox": ("Provider and API integration", "Durable provider retries, unique intent, availability and competing-worker lease."),
    "provider_webhooks": ("Provider and API integration", "Deduplicated signed provider event IDs and payload hashes."),
    "security_rate_buckets": ("Security and monitoring", "Shared hashed rate limit keys, windows and expiry across app workers."),
    "security_otp_challenges": ("Security and monitoring", "Hashed, expiring one-use OTP challenges and bounded verification attempts."),
    "security_trusted_sessions": ("Security and monitoring", "Hashed session/device/agent trust, expiry and revocation."),
    "security_audit_events": ("Security and monitoring", "Signed append-only content-minimized audit events; ORM update/delete blocked."),
    "transaction_review_flags": ("Security and monitoring", "Unique transaction/rule monitoring flags for human review."),
    "schedule_retries": ("Durable workers", "Persistent retry/backoff and exhausted state per scheduled payment."),
    "worker_heartbeats": ("Durable workers", "Worker role, last observation and completion/failure counts."),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def workspace_path(path: str | Path, *, exists: bool = True) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(ROOT)
    except ValueError:
        raise ValueError("Inventory paths must resolve inside the project workspace.") from None
    if exists and not candidate.is_file():
        raise ValueError("Inventory input must be an existing workspace file.")
    return candidate


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


@contextmanager
def readonly_snapshot(path: Path):
    """Read a quiescent file without journal creation or implicit database creation."""
    path = workspace_path(path)
    if path.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
        raise ValueError("Inventory inputs must be SQLite snapshot files (.db, .sqlite, .sqlite3).")
    for suffix, label in (("-wal", "WAL"), ("-journal", "rollback journal")):
        sidecar = Path(str(path) + suffix)
        if sidecar.exists() and sidecar.stat().st_size:
            raise ValueError("Active " + label + " detected; inventory a consistent backup rather than the live database.")
    # immutable prevents SQLite from creating journal/SHM sidecars. A second hash
    # below detects a concurrent file change; WAL-backed files are rejected.
    connection = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        yield connection
    finally:
        connection.close()


def _default_value(default):
    if default is None:
        return None
    value = default.arg
    if callable(value):
        return "callable: " + value.__module__ + "." + value.__qualname__
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (bool, int, float, str)) or value is None:
        return value
    return str(value)


def expected_schema():
    """Register models with an isolated app, never import run.py/wsgi.py."""
    from app import create_app
    from app.extensions import db
    from config import DevelopmentConfig
    from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint
    from sqlalchemy.dialects import postgresql, sqlite
    from sqlalchemy.schema import CreateIndex, CreateTable

    class InventoryConfig(DevelopmentConfig):
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        SQLALCHEMY_ENGINE_OPTIONS = {}
        SQLALCHEMY_BINDS = {}
        AUTO_CREATE_SCHEMA = False
        SEED_DEMO_DATA = False
        SCHEDULE_AUTO_RUN_ON_REQUEST = False
        SECURITY_PRODUCTION = False
        ASSISTANT_API_ENABLED = False
        OPENAI_API_KEY = ""
        DATA_ENCRYPTION_KEY = ""
        DATA_ENCRYPTION_KEYS = ""
        REQUIRE_DATA_ENCRYPTION = False
        MONITOR_LARGE_AMOUNT_BDT = "50000"
        SECRET_KEY = "inventory-isolated-metadata-only"
        TESTING = True
        DEBUG = False

    app = create_app(InventoryConfig)
    with app.app_context():
        sources = {mapper.local_table.name: relative(Path(inspect.getfile(mapper.class_)).resolve())
                   for mapper in db.Model.registry.mappers}
        result = {}
        for table in sorted(db.metadata.tables.values(), key=lambda table: table.name):
            group, purpose = PURPOSES.get(table.name, ("Unclassified", "New schema requires a reviewed purpose entry."))
            columns = []
            for column in table.columns:
                columns.append({
                    "name": column.name, "type": str(column.type),
                    "sqlite_type": column.type.compile(dialect=sqlite.dialect()),
                    "postgresql_type": column.type.compile(dialect=postgresql.dialect()),
                    "nullable": column.nullable, "primary_key": column.primary_key,
                    "python_default": _default_value(column.default),
                    "python_onupdate": _default_value(column.onupdate),
                    "server_default": str(column.server_default.arg) if column.server_default is not None else None,
                    "foreign_keys": sorted(fk.target_fullname for fk in column.foreign_keys),
                })
            result[table.name] = {
                "group": group, "purpose": purpose, "source": sources.get(table.name), "columns": columns,
                "primary_key": [column.name for column in table.primary_key.columns],
                "foreign_keys": sorted([
                    {"name": constraint.name, "columns": [element.parent.name for element in constraint.elements],
                     "references": [element.target_fullname for element in constraint.elements],
                     "ondelete": constraint.ondelete, "onupdate": constraint.onupdate}
                    for constraint in table.constraints if isinstance(constraint, ForeignKeyConstraint)
                ], key=lambda item: (item["columns"], item["references"])),
                "unique_constraints": sorted([
                    {"name": constraint.name, "columns": [column.name for column in constraint.columns]}
                    for constraint in table.constraints if isinstance(constraint, UniqueConstraint)
                ], key=lambda item: item["columns"]),
                "checks": sorted(str(constraint.sqltext) for constraint in table.constraints if isinstance(constraint, CheckConstraint)),
                "indexes": [{"name": index.name, "columns": [column.name for column in index.columns], "unique": index.unique}
                            for index in sorted(table.indexes, key=lambda index: index.name)],
                "sqlite_ddl": str(CreateTable(table).compile(dialect=sqlite.dialect())).strip(),
                "postgresql_ddl": str(CreateTable(table).compile(dialect=postgresql.dialect())).strip(),
                "sqlite_index_ddl": [str(CreateIndex(index).compile(dialect=sqlite.dialect())) for index in sorted(table.indexes, key=lambda index: index.name)],
            }
        # No schema or seed was created even in the isolated in-memory database.
        db.session.remove()
        db.engine.dispose()
    return result


def _checks_from_ddl(ddl: str):
    """Read balanced CHECK expressions; full original DDL remains in the JSON."""
    results = []
    for match in re.finditer(r"\bCHECK\s*\(", ddl, re.IGNORECASE):
        start, depth, quote = match.end(), 1, None
        position = start
        while position < len(ddl) and depth:
            character = ddl[position]
            if quote:
                if character == quote:
                    if position + 1 < len(ddl) and ddl[position + 1] == quote:
                        position += 1
                    else:
                        quote = None
            elif character in "'\"`":
                quote = character
            elif character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
            position += 1
        if depth == 0:
            results.append(ddl[start:position - 1].strip())
    return results


def observed_schema(connection):
    tables = {}
    for row in connection.execute("SELECT name, sql FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        name, ddl = row["name"], row["sql"] or ""
        quoted = quote_identifier(name)
        columns = [{"name": column["name"], "type": column["type"],
                    "nullable": not bool(column["notnull"]), "primary_key_position": column["pk"],
                    "server_default": column["dflt_value"], "hidden": column["hidden"]}
                   for column in connection.execute("PRAGMA table_xinfo(" + quoted + ")")]
        foreign_keys = [dict(record) for record in connection.execute("PRAGMA foreign_key_list(" + quoted + ")")]
        indexes = []
        for index in connection.execute("PRAGMA index_list(" + quoted + ")"):
            index_name = index["name"]
            indexes.append({"name": index_name, "unique": bool(index["unique"]), "origin": index["origin"],
                            "partial": bool(index["partial"]),
                            "columns": [field["name"] for field in connection.execute("PRAGMA index_info(" + quote_identifier(index_name) + ")")],
                            "ddl": connection.execute("SELECT sql FROM sqlite_schema WHERE type='index' AND name=?", (index_name,)).fetchone()[0]})
        tables[name] = {"columns": columns,
                        "primary_key": [column["name"] for column in sorted(columns, key=lambda item: item["primary_key_position"]) if column["primary_key_position"]],
                        "foreign_keys": foreign_keys, "indexes": sorted(indexes, key=lambda item: item["name"]),
                        "unique_constraints": [index["columns"] for index in indexes if index["unique"] and index["origin"] == "u"],
                        "checks": _checks_from_ddl(ddl), "ddl": ddl,
                        "row_count": connection.execute("SELECT COUNT(*) FROM " + quoted).fetchone()[0]}
    return tables


def compare_schema(expected, observed):
    differences = {}
    for name in sorted(set(expected) & set(observed)):
        target, actual = expected[name], observed[name]
        desired_columns = {column["name"]: column for column in target["columns"]}
        actual_columns = {column["name"]: column for column in actual["columns"]}
        changes = []
        for column_name in sorted(set(desired_columns) & set(actual_columns)):
            desired, existing = desired_columns[column_name], actual_columns[column_name]
            if re.sub(r"\s", "", desired["sqlite_type"].upper()) != re.sub(r"\s", "", existing["type"].upper()):
                changes.append({"column": column_name, "attribute": "type", "expected": desired["sqlite_type"], "actual": existing["type"]})
            if desired["nullable"] != existing["nullable"]:
                changes.append({"column": column_name, "attribute": "nullable", "expected": desired["nullable"], "actual": existing["nullable"]})
            if desired["server_default"] != existing["server_default"]:
                changes.append({"column": column_name, "attribute": "server_default", "expected": desired["server_default"], "actual": existing["server_default"]})
        actual_indexes = {index["name"]: index for index in actual["indexes"]}
        missing_indexes = [index["name"] for index in target["indexes"] if index["name"] not in actual_indexes]
        mismatched_indexes = [index["name"] for index in target["indexes"] if index["name"] in actual_indexes and
                              (index["columns"], index["unique"], False) != (actual_indexes[index["name"]]["columns"], actual_indexes[index["name"]]["unique"], actual_indexes[index["name"]]["partial"])]
        missing_unique = [item["columns"] for item in target["unique_constraints"] if item["columns"] not in actual["unique_constraints"]]
        grouped_fks = {}
        for foreign_key in actual["foreign_keys"]:
            grouped_fks.setdefault(foreign_key["id"], []).append(foreign_key)
        actual_fks = set()
        for members in grouped_fks.values():
            members.sort(key=lambda item: item["seq"])
            actual_fks.add((tuple(item["from"] for item in members), tuple(item["table"] + "." + item["to"] for item in members), members[0]["on_delete"], members[0]["on_update"]))
        missing_fks = [item for item in target["foreign_keys"] if (tuple(item["columns"]), tuple(item["references"]), item["ondelete"] or "NO ACTION", item["onupdate"] or "NO ACTION") not in actual_fks]
        info = {"missing_columns": sorted(set(desired_columns) - set(actual_columns)),
                "unexpected_columns": sorted(set(actual_columns) - set(desired_columns)), "column_differences": changes,
                "missing_indexes": missing_indexes, "mismatched_indexes": mismatched_indexes,
                "missing_unique_constraints": missing_unique, "missing_foreign_keys": missing_fks,
                "primary_key_mismatch": target["primary_key"] != actual["primary_key"],
                "missing_checks": sorted(set(target["checks"]) - set(actual["checks"]))}
        if any(info.values()):
            differences[name] = info
    return {"missing_tables": sorted(set(expected) - set(observed)),
            "unexpected_tables": sorted(set(observed) - set(expected) - {"alembic_version", "_qa_cluster_guard"}),
            "table_differences": differences}


def _money(value):
    number = Decimal(str(value or 0))
    if not number.is_finite():
        raise ValueError("Non-finite ledger amount cannot be inventoried.")
    return number.quantize(Decimal("0.01"))


def _iso(value, *, day=False):
    if value is None:
        return None
    try:
        return (date.fromisoformat(str(value)).isoformat() if day else datetime.fromisoformat(str(value)).isoformat())
    except ValueError:
        return "invalid date value (withheld)"


def aggregate_provenance(connection, tables):
    result = {"date_ranges": {}, "synthetic_datasets": [], "opening_anchor_sources": {}}
    for table, column in (("transactions", "created_at"), ("users", "created_at"),
                          ("scheduled_payments", "due_at"), ("wallet_opening_balances", "recorded_at")):
        if table in tables and column in {item["name"] for item in tables[table]["columns"]}:
            row = connection.execute("SELECT MIN(" + quote_identifier(column) + "), MAX(" + quote_identifier(column) + ") FROM " + quote_identifier(table)).fetchone()
            result["date_ranges"][table + "." + column] = {"min": _iso(row[0]), "max": _iso(row[1])}
    if "demo_datasets" in tables:
        for row in connection.execute("SELECT starts_on,ends_on,generated_at,generator_version,synthetic FROM demo_datasets"):
            # Version is source metadata, bounded to the generator's safe syntax.
            version = row["generator_version"]
            version = version if isinstance(version, str) and re.fullmatch(r"household-ledger-v\d{1,3}", version) else "other generator (version withheld)"
            result["synthetic_datasets"].append({"starts_on": _iso(row["starts_on"], day=True), "ends_on": _iso(row["ends_on"], day=True),
                                                  "generated_at": _iso(row["generated_at"]), "generator_version": version, "synthetic": bool(row["synthetic"])})
    if "wallet_opening_balances" in tables:
        for row in connection.execute("SELECT source,COUNT(*) AS count FROM wallet_opening_balances GROUP BY source"):
            # Never export arbitrary customer-written source labels.
            label = "synthetic opening fixture" if str(row["source"]).startswith("Synthetic opening fixture / ") else "other source (label withheld)"
            result["opening_anchor_sources"][label] = result["opening_anchor_sources"].get(label, 0) + row["count"]
    return result


def reconcile_balances(connection, tables):
    required = {"users", "transactions"}
    if not required.issubset(tables):
        return {"available": False, "reason": "Wallet or receipt table absent."}
    balances = {row["id"]: _money(row["balance"]) for row in connection.execute("SELECT id,balance FROM users")}
    movements = {user_id: Decimal("0.00") for user_id in balances}
    incoming = outgoing = fees = Decimal("0.00")
    invalid_directions = 0
    for row in connection.execute("SELECT user_id,amount,fee,direction FROM transactions WHERE status='SUCCESS'"):
        amount, fee = _money(row["amount"]), _money(row["fee"])
        if row["direction"] == "IN":
            delta = amount
            incoming += amount
        elif row["direction"] == "OUT":
            delta = -(amount + fee)
            outgoing += amount + fee
            fees += fee
        else:
            invalid_directions += 1
            continue
        if row["user_id"] in movements:
            movements[row["user_id"]] += delta
    anchors = {row["user_id"]: _money(row["opening_balance"]) for row in connection.execute("SELECT user_id,opening_balance FROM wallet_opening_balances")} if "wallet_opening_balances" in tables else {}
    differences = [abs(balances[user_id] - (anchors[user_id] + movements[user_id])) for user_id in set(balances) & set(anchors)]
    return {"available": True, "formula": "opening balance + SUCCESS IN amount - SUCCESS OUT (amount + fee)",
            "accounts": len(balances), "anchored_accounts": len(differences), "unanchored_accounts": len(set(balances) - set(anchors)),
            "mismatched_anchored_accounts": sum(value != 0 for value in differences),
            "invalid_success_directions": invalid_directions,
            "current_balance_total_bdt": str(sum(balances.values(), Decimal("0.00"))),
            "opening_balance_total_bdt": str(sum(anchors.values(), Decimal("0.00"))),
            "success_incoming_total_bdt": str(incoming), "success_outgoing_total_including_fees_bdt": str(outgoing),
            "success_outgoing_fees_total_bdt": str(fees), "net_success_change_bdt": str(incoming - outgoing),
            "absolute_discrepancy_total_bdt": str(sum(differences, Decimal("0.00"))),
            "largest_absolute_discrepancy_bdt": str(max(differences, default=Decimal("0.00"))),
            "fully_reconciled": bool(balances) and len(differences) == len(balances) and not any(differences) and not invalid_directions}


def inspect_database(path, expected):
    path = workspace_path(path)
    before_hash, before_stat = sha256_file(path), path.stat()
    with readonly_snapshot(path) as connection:
        tables = observed_schema(connection)
        integrity_rows = connection.execute("PRAGMA integrity_check").fetchall()
        integrity_ok = len(integrity_rows) == 1 and integrity_rows[0][0] == "ok"
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        violations_by_table = {}
        for row in violations:
            violations_by_table[row[0]] = violations_by_table.get(row[0], 0) + 1
        version = connection.execute("PRAGMA schema_version").fetchone()[0]
        page_count = connection.execute("PRAGMA page_count").fetchone()[0]
        page_size = connection.execute("PRAGMA page_size").fetchone()[0]
        # Migration version is schema metadata, never a secret connection URL.
        heads = [row[0] for row in connection.execute("SELECT version_num FROM alembic_version")] if "alembic_version" in tables else []
        reconciliation = reconcile_balances(connection, tables)
        provenance = aggregate_provenance(connection, tables)
        storage_prefix_counts = {}
        for table, column in (("assistant_conversations", "messages"), ("api_idempotency", "response_json"), ("provider_intents", "biller_reference")):
            if table in tables and column in {item["name"] for item in tables[table]["columns"]}:
                row = connection.execute("SELECT COUNT(*), COALESCE(SUM(" + quote_identifier(column) + " LIKE 'enc:v1:%'),0) FROM " + quote_identifier(table)).fetchone()
                storage_prefix_counts[table + "." + column] = {"rows": row[0], "enc_v1_prefix_rows": row[1], "other_rows": row[0] - row[1]}
    after_hash, after_stat = sha256_file(path), path.stat()
    unchanged = before_hash == after_hash and before_stat.st_mtime_ns == after_stat.st_mtime_ns and before_stat.st_size == after_stat.st_size
    if not unchanged:
        raise ValueError("Database changed during inventory; no consistent snapshot claim can be made.")
    return {"path": relative(path), "bytes": before_stat.st_size,
            "last_modified_utc": datetime.fromtimestamp(before_stat.st_mtime, timezone.utc).isoformat(),
            "sha256_before": before_hash, "sha256_after": after_hash, "unchanged": unchanged,
            "read_only_uri": "mode=ro&immutable=1", "schema_version": version,
            "migration_heads": heads, "table_count": len(tables), "page_count": page_count, "page_size": page_size,
            "total_rows": sum(table["row_count"] for table in tables.values()),
            "application_rows": sum(table["row_count"] for name, table in tables.items() if name in expected),
            "integrity_check": "ok" if integrity_ok else "failed (details withheld)",
            "foreign_key_violation_count": len(violations), "foreign_key_violations_by_table": violations_by_table,
            "tables": tables, "schema_comparison": compare_schema(expected, tables),
            "field_storage_prefix_counts": storage_prefix_counts,
            "provenance": provenance, "balance_reconciliation": reconciliation}


def build_inventory(paths):
    expected = expected_schema()
    source_paths = sorted({ROOT / item["source"] for item in expected.values()} | set((ROOT / "migrations" / "versions").glob("*.py")) | {Path(__file__).resolve(), ROOT / "compose.yaml", ROOT / "config.py"})
    return {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "sqlite_library_version": sqlite3.sqlite_version,
            "scope": "Read-only workspace SQLite snapshots; isolated ORM metadata. No record samples or personal identifiers exported.",
            "expected_table_count": len(expected), "expected_column_count": sum(len(table["columns"]) for table in expected.values()),
            "expected_migration_head": "20261007_03", "source_sha256": {relative(path): sha256_file(path) for path in source_paths},
            "expected_tables": expected, "databases": [inspect_database(path, expected) for path in paths]}


def _cell(value):
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value).replace("|", "\\|").replace("\n", " ").replace("<", "&lt;").replace(">", "&gt;")


def _constraints(table):
    lines = ["Primary key: `" + ", ".join(table["primary_key"]) + "`." if table["primary_key"] else "Primary key: none."]
    for foreign_key in table["foreign_keys"]:
        lines.append("Foreign key: `" + ", ".join(foreign_key["columns"]) + "` → `" + ", ".join(foreign_key["references"]) + "`; delete " + (foreign_key["ondelete"] or "NO ACTION") + ", update " + (foreign_key["onupdate"] or "NO ACTION") + ".")
    if not table["foreign_keys"]:
        lines.append("Foreign keys: none.")
    lines.append("Unique constraints: " + ("; ".join("`" + ", ".join(item["columns"]) + "`" + (" (" + item["name"] + ")" if item["name"] else "") for item in table["unique_constraints"]) or "none") + ".")
    lines.append("Indexes: " + ("; ".join("`" + index["name"] + "(" + ", ".join(index["columns"]) + ")`" + (" UNIQUE" if index["unique"] else "") for index in table["indexes"]) or "none beyond primary/unique constraint indexes") + ".")
    lines.append("Checks: " + ("; ".join("`" + item + "`" for item in table["checks"]) or "none declared in the ORM") + ".")
    return "\n\n".join(lines)


def render_catalog(report):
    databases, expected = report["databases"], report["expected_tables"]
    main = next((database for database in databases if database["path"] == "instance/upay_hackathon.db"), None)
    labels, backup_count = [], 0
    for database in databases:
        if database["path"] == "instance/upay_hackathon.db":
            label = "Main"
        elif database["path"] == "instance/judge-demo.db":
            label = "Judge demo"
        elif database["path"].startswith("instance/backups/"):
            backup_count += 1
            label = "Backup " + str(backup_count)
        else:
            label = "Snapshot " + str(len(labels) + 1)
        labels.append(label)
    main_description = (f"The inspected main file contains **{main['table_count']} tables** and " + ("no Alembic version table" if not main["migration_heads"] else "Alembic revision " + ", ".join(main["migration_heads"])) + ". Its missing tables/indexes are reported below." if main else "The historical main file was **not inspected** because it was absent or not selected. No database was created to fill that gap.")
    lines = ["# Database catalog", "",
             "Generated by `scripts/database_inventory.py` at " + report["generated_at_utc"] + ". This is a read-only snapshot of the files listed below; it does not migrate, seed, reset, decrypt or print account records.", "",
             f"The code declares **{report['expected_table_count']} application tables and {report['expected_column_count']} columns**, with Alembic head `{report['expected_migration_head']}`. " + main_description + " ORM schema and inspected data are distinct evidence.", "",
             "## Database environments", "",
             "| Environment | Storage and lifecycle | Evidence / boundary |", "| --- | --- | --- |",
             "| Existing local demo | `instance/upay_hackathon.db`; persisted SQLite file | When present/selected, inspected using `mode=ro&immutable=1`, with identical before/after hashes. No upgrade performed. |",
             "| Judge demo | `instance/judge-demo.db`; separately prepared seeded SQLite demonstration | Included if present, using the same read-only/hash checks. The historical main file is preserved. |",
             "| Historical demo backups | `instance/backups/*.db`; snapshots before demo reset | Inspected individually; they are historical schemas/data, not automatically restored. |",
             "| Compose infrastructure lab | PostgreSQL 18 image; named `postgres18_data` volume mounted at `/var/lib/postgresql` | `compose.yaml` runs migrations before web/workers. This inventory does not connect to that volume or claim current row counts. |",
             "| Disposable infrastructure QA | Separate temporary PostgreSQL 18.6 cluster and unique SQLite fixtures under `tmp/infrastructure-qa` | Six PostgreSQL concurrency checks and SQLite/PostgreSQL mixed HTTP load reports in [LOAD_TEST.md](LOAD_TEST.md). QA PostgreSQL cluster was stopped and removed. |",
             "| Independent reference provider | Separate reference sandbox SQLite ledger selected explicitly by its runner | Signed HTTP integration fixture; provider results never debit the local wallet. Provider database is not the main application database or an official Upay connection. |", "",
             "Only schema and aggregate metrics are published. Account identifiers, mobile/email/name values, password/PIN/OTP values and hashes, bearer tokens, challenges, chat rows and private payment references are excluded. Python defaults below are application-side defaults; **they are not SQL server defaults**. Callable defaults are named without execution. PostgreSQL timestamp types preserve timezone support; SQLite stores application UTC timestamps as `DATETIME`.", "",
             "## Inspected files", "", "| File | Bytes | Modified (UTC) | Tables | Total rows / application rows | Integrity / FK errors | Unchanged |", "| --- | ---: | --- | ---: | --- | ---: | --- |"]
    for database in databases:
        lines.append(f"| `{database['path']}` | {database['bytes']} | {database['last_modified_utc']} | {database['table_count']} | {database['total_rows']} / {database['application_rows']} | {database['integrity_check']} / {database['foreign_key_violation_count']} | {_cell(database['unchanged'])} |")
    if not databases:
        lines.extend(["", "No existing SQLite snapshot was found or selected. This report contains schema metadata only; database row counts, integrity and balances are not inspected."])
    for database in databases:
        lines.extend(["", "SHA256 `" + database["path"] + "`: `" + database["sha256_before"] + "`. Before and after inspection matched."])
    row_labels = labels or ["Snapshot"]
    lines.extend(["", "Filesystem modification dates are observations, not dataset creation dates. Backup filename timestamps are historical naming provenance. SQLite `schema_version` is an internal change counter, not an Alembic migration revision.", "", "## Actual table row counts", "",
                  "| Table | " + " | ".join(row_labels) + " |", "| --- | " + " | ".join("---:" for _ in row_labels) + " |"])
    all_tables = sorted(set(expected) | {name for database in databases for name in database["tables"]})
    for name in all_tables:
        values = [str(database["tables"][name]["row_count"]) if name in database["tables"] else "absent" for database in databases] or ["not inspected"]
        lines.append("| `" + name + "` | " + " | ".join(values) + " |")
    lines.append("")
    for index, database in enumerate(databases):
        lines.append(labels[index] + ": `" + database["path"] + "`.")
    lines.extend(["", "## Schema differences and startup requirements", "",
                  "The inventory command does not modify these files. Development startup normally uses `AUTO_CREATE_SCHEMA=True` and `SEED_DEMO_DATA=True`; do not start it merely to inspect a snapshot. `create_all` can add missing tables but does not add missing indexes on existing tables, alter columns or establish migration provenance. Use the reviewed backup/adoption procedure in [DEPLOYMENT.md](DEPLOYMENT.md) with seeding disabled. Existing schemas require explicit `ALEMBIC_ADOPT_EXISTING=1`; frozen migrations validate their structure. Production requires PostgreSQL and ordinary migrations, with auto-create and demo seeding disabled."])
    for database in databases:
        comparison = database["schema_comparison"]
        lines.extend(["", "### `" + database["path"] + "`", "",
                      "Migration revision: " + (", ".join("`" + value + "`" for value in database["migration_heads"]) or "unrecorded (no `alembic_version` table)") + ". Internal SQLite schema counter: " + str(database["schema_version"]) + ".", "",
                      "Missing tables: " + (", ".join("`" + name + "`" for name in comparison["missing_tables"]) or "none") + ".", "",
                      "Unexpected application tables: " + (", ".join("`" + name + "`" for name in comparison["unexpected_tables"]) or "none") + "."])
        for name, differences in comparison["table_differences"].items():
            items = [key + ": " + json.dumps(value, ensure_ascii=False) for key, value in differences.items() if value]
            lines.extend(["", "`" + name + "`: " + "; ".join(items) + "."])
        if not comparison["table_differences"]:
            lines.extend(["", "Existing table column/constraint/index shapes match the expected SQLite metadata."])
    lines.extend(["", "## Dataset provenance and balance reconciliation", "",
                  "Reconciliation checks each anchored wallet independently before publishing aggregates: `opening + SUCCESS IN amount − SUCCESS OUT (amount + fee)`. Pending, failed and deferred receipts have no wallet effect. Matching aggregate totals alone do not prove each account reconciles. A historical file without explicit opening anchors is marked unverified."])
    for database in databases:
        reconciliation = database["balance_reconciliation"]
        lines.extend(["", "### `" + database["path"] + "`", "",
                      "| Aggregate | Observed value |", "| --- | --- |"])
        for key, value in reconciliation.items():
            if key not in {"formula", "available"}:
                lines.append("| " + key.replace("_", " ") + " | " + _cell(value) + " |")
        lines.extend(["", "Date ranges (stored application UTC timestamps):", ""])
        for key, value in database["provenance"]["date_ranges"].items():
            lines.append("- `" + key + "`: " + _cell(value["min"]) + " to " + _cell(value["max"]) + ".")
        for dataset in database["provenance"]["synthetic_datasets"]:
            lines.extend(["", "Dataset: synthetic=" + _cell(dataset["synthetic"]) + "; generator `" + dataset["generator_version"] + "`; period " + _cell(dataset["starts_on"]) + " to " + _cell(dataset["ends_on"]) + "; generated " + _cell(dataset["generated_at"]) + "."])
        if not database["provenance"]["synthetic_datasets"]:
            lines.extend(["", "No explicit `demo_datasets` provenance row/table in this snapshot; synthetic source cannot be established from the schema alone."])
        if database["provenance"]["opening_anchor_sources"]:
            lines.extend(["", "Opening sources: " + json.dumps(database["provenance"]["opening_anchor_sources"], ensure_ascii=False) + "."])
    lines.extend(["", "## Sensitive-field storage observations", "",
                  "The application encrypts new conversation text, API replay payloads and provider biller references when configured keys are available. The following counts inspect only the `enc:v1:` prefix, without printing or decrypting values; a prefix is not cryptographic authentication. Historical demo rows and seeded synthetic legacy fields may remain plaintext. This is field encryption, not full SQLite/database/backup encryption; runtime secrets and key sidecars are excluded from this inventory.", "",
                  "| File | Field | Rows | `enc:v1:` prefix | Other / legacy |", "| --- | --- | ---: | ---: | ---: |"])
    for database in databases:
        for field, counts in database["field_storage_prefix_counts"].items():
            lines.append("| `" + database["path"] + "` | `" + field + "` | " + str(counts["rows"]) + " | " + str(counts["enc_v1_prefix_rows"]) + " | " + str(counts["other_rows"]) + " |")
    lines.extend(["", "## Complete expected application schema", "",
                  "The following is the current ORM contract, not a claim that all tables exist in the main file. The [JSON inventory](../output/qa/database-inventory.json) contains every observed SQLite column, FK, index, unique constraint, check and original table DDL for all inspected files, plus expected SQLite/PostgreSQL DDL and source checksums. SQL constraint enforcement and service validation are separate: SQLite does not enforce `VARCHAR` length or `NUMERIC` precision like PostgreSQL; no ORM CHECK constraints are currently declared."])
    groups = list(dict.fromkeys(group for group, _ in PURPOSES.values()))
    for group in groups:
        lines.extend(["", "### " + group])
        for name, table in expected.items():
            if table["group"] != group:
                continue
            lines.extend(["", "#### `" + name + "`", "", table["purpose"], "",
                          "Source: [`" + table["source"] + "`](../" + table["source"] + "). Main rows: " + ((str(main["tables"][name]["row_count"]) if name in main["tables"] else "table absent") if main else "not inspected") + ".", "",
                          "| Column | SQLite type | PostgreSQL type | Nullable | PK | Python default | SQL default | FK target |",
                          "| --- | --- | --- | --- | --- | --- | --- | --- |"])
            for column in table["columns"]:
                lines.append("| `" + column["name"] + "` | " + " | ".join(_cell(value) for value in (column["sqlite_type"], column["postgresql_type"], column["nullable"], column["primary_key"], column["python_default"], column["server_default"], ", ".join(column["foreign_keys"]) or None)) + " |")
            lines.extend(["", _constraints(table)])
    lines.extend(["", "## Reproduce the inventory", "", "```powershell", ".\\.venv\\Scripts\\python.exe scripts\\database_inventory.py", "```", "",
                  "Defaults inspect the main file if it exists, `instance/judge-demo.db` if present, and all `.db` files directly in `instance/backups`. With no database files present, it produces a complete schema-only catalog and marks counts as not inspected. Use repeatable `--database <workspace-file>` arguments to inspect selected snapshots, for example `--database instance/judge-demo.db`. `--json` and `--markdown` select workspace report destinations. No connection string is accepted or printed. Selected inputs must exist inside the project after path resolution; live WAL/journal files are refused. Connections close in `finally`, and changed hashes/size/mtime abort the report. Run against a quiescent snapshot; this utility is not an online backup tool.", ""])
    lines.extend(["Regenerate an existing submission document's marked catalog without changing its surrounding feedback or scores:", "", "```powershell", ".\\.venv\\Scripts\\python.exe scripts\\database_inventory.py --phase2 phase_2.md", "```", "", "The optional `--phase2` target must already contain exactly one `<!-- BEGIN GENERATED DATABASE CATALOG -->` and one `<!-- END GENERATED DATABASE CATALOG -->` in order. Only content between them is replaced; links are adjusted for the root document. Missing/duplicate/reversed markers fail before report writes.", ""])
    return "\n".join(lines)


def default_databases(root=ROOT):
    return [path for path in [root / "instance" / "upay_hackathon.db", root / "instance" / "judge-demo.db", *sorted((root / "instance" / "backups").glob("*.db"))] if path.is_file()]


BEGIN_MARKER = "<!-- BEGIN GENERATED DATABASE CATALOG -->"
END_MARKER = "<!-- END GENERATED DATABASE CATALOG -->"


def embed_catalog(document: str, catalog: str):
    """Replace only the unique generated block, preserving all outside text."""
    if document.count(BEGIN_MARKER) != 1 or document.count(END_MARKER) != 1:
        raise ValueError("Phase 2 document requires exactly one begin and one end catalog marker.")
    start = document.index(BEGIN_MARKER) + len(BEGIN_MARKER)
    end = document.index(END_MARKER)
    if end < start:
        raise ValueError("Phase 2 catalog markers are in the wrong order.")
    root_links = re.sub(r"(\]\()\.\./", r"\1", catalog)
    root_links = root_links.replace("(LOAD_TEST.md)", "(docs/LOAD_TEST.md)").replace("(DEPLOYMENT.md)", "(docs/DEPLOYMENT.md)")
    return document[:start] + "\n\n" + root_links.rstrip() + "\n\n" + document[end:]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", action="append", help="Existing SQLite file inside the workspace (repeatable).")
    parser.add_argument("--json", default="output/qa/database-inventory.json")
    parser.add_argument("--markdown", default="docs/DATABASE_CATALOG.md")
    parser.add_argument("--phase2", help="Existing phase_2.md with unique generated catalog markers; preserve all other text.")
    args = parser.parse_args(argv)
    paths = args.database if args.database is not None else default_databases()
    json_path = workspace_path(args.json, exists=False)
    markdown_path = workspace_path(args.markdown, exists=False)
    phase2_path = workspace_path(args.phase2) if args.phase2 else None
    phase2_text = phase2_path.read_bytes().decode("utf-8") if phase2_path else None
    if json_path.suffix.lower() != ".json" or markdown_path.suffix.lower() != ".md":
        parser.error("Report destinations must use .json and .md extensions, respectively.")
    if phase2_path:
        if phase2_path.suffix.lower() != ".md" or phase2_path in {json_path, markdown_path}:
            parser.error("Phase 2 target must be a distinct existing Markdown file.")
        try:
            embed_catalog(phase2_text, "")
        except ValueError as exc:
            parser.error(str(exc))
    inputs = [workspace_path(path) for path in paths]
    output_paths = [json_path, markdown_path, *([phase2_path] if phase2_path else [])]
    if any(path.exists() and path.stat().st_nlink > 1 for path in output_paths):
        parser.error("Report destinations cannot be hard-link aliases.")
    if json_path in inputs or markdown_path in inputs or json_path == markdown_path or any(output.exists() and output.samefile(database) for output in (json_path, markdown_path) for database in inputs):
        parser.error("Report destinations must differ from every database input and from each other.")
    report = build_inventory(inputs)
    catalog = render_catalog(report)
    for path in (json_path, markdown_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(catalog, encoding="utf-8")
    if phase2_path:
        phase2_path.write_bytes(embed_catalog(phase2_text, catalog).encode("utf-8"))
    print(json.dumps({"expected_tables": report["expected_table_count"], "expected_columns": report["expected_column_count"],
                      "databases": [{"path": database["path"], "tables": database["table_count"], "integrity": database["integrity_check"],
                                     "fk_violations": database["foreign_key_violation_count"], "unchanged": database["unchanged"]}
                                    for database in report["databases"]],
                      "json_report": relative(json_path), "catalog": relative(markdown_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
