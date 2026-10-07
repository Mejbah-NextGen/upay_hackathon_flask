"""Developer-only frozen baseline generation; never connects to wallet data."""

import ast
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from alembic.autogenerate import produce_migrations, render_python_code
from alembic.migration import MigrationContext
from alembic.operations.ops import UpgradeOps, ModifyTableOps
from sqlalchemy import create_engine

from app import create_app
from app.extensions import db
from config import DevelopmentConfig


def main():
    original = set()
    paths = subprocess.check_output(["git", "ls-files", "app/domain"], cwd=ROOT, text=True).splitlines()
    for path in paths:
        for node in ast.walk(ast.parse((ROOT / path).read_text(encoding="utf-8"))):
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__tablename__" for t in node.targets):
                original.add(ast.literal_eval(node.value))
    configuration = type("SchemaConfig", (DevelopmentConfig,), {
        "AUTO_CREATE_SCHEMA": False, "SEED_DEMO_DATA": False, "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    app = create_app(configuration)
    engine = create_engine("sqlite:///:memory:")
    with app.app_context(), engine.connect() as connection:
        operations = produce_migrations(MigrationContext.configure(connection), db.metadata).upgrade_ops.ops
    new_indexes = {"ix_transactions_user_status_created", "ix_schedules_due_auto_status"}
    baseline, additions = [], []
    for operation in operations:
        name = getattr(operation, "table_name", None)
        if isinstance(operation, ModifyTableOps) and name in original:
            first = [item for item in operation.ops if getattr(item, "index_name", None) not in new_indexes]
            second = [item for item in operation.ops if getattr(item, "index_name", None) in new_indexes]
            if first:
                baseline.append(ModifyTableOps(name, first))
            if second:
                additions.append(ModifyTableOps(name, second))
        else:
            (baseline if name in original else additions).append(operation)
    output = ROOT / "migrations" / "versions"
    output.mkdir(parents=True, exist_ok=True)
    helpers = '''
def _create_table(name, *columns, **kwargs):
    inspector = sa.inspect(op.get_bind())
    if name in inspector.get_table_names():
        if os.environ.get("ALEMBIC_ADOPT_EXISTING") != "1":
            raise RuntimeError("Existing schema requires an explicit validated adoption: ALEMBIC_ADOPT_EXISTING=1")
        expected = {column.name: column for column in columns if isinstance(column, sa.Column)}
        actual = {column["name"]: column for column in inspector.get_columns(name)}
        if set(expected) != set(actual) or any(not column.primary_key and column.nullable != actual[key]["nullable"] for key, column in expected.items()):
            raise RuntimeError("Existing table is incompatible with the frozen baseline: " + name)
        frozen = sa.Table(name, sa.MetaData(), *columns)
        for key, column in expected.items():
            reflected = actual[key]["type"]
            if column.type._type_affinity is not reflected._type_affinity:
                raise RuntimeError("Incompatible existing column type: " + name + "." + key)
            for attribute in ("length", "precision", "scale"):
                if getattr(column.type, attribute, None) != getattr(reflected, attribute, None):
                    raise RuntimeError("Incompatible existing column bounds: " + name + "." + key)
        if list(frozen.primary_key.columns.keys()) != inspector.get_pk_constraint(name)["constrained_columns"]:
            raise RuntimeError("Incompatible existing primary key: " + name)
        actual_foreign = {(tuple(c["constrained_columns"]), c["referred_table"], tuple(c["referred_columns"]),
                           c.get("options", {}).get("ondelete"), c.get("options", {}).get("onupdate"))
                          for c in inspector.get_foreign_keys(name)}
        # Resolve targets from strings; referenced tables may not be loaded yet.
        expected_foreign = {(tuple(c.columns.keys()), next(iter(c.elements)).target_fullname.split(".")[-2],
                             tuple(e.target_fullname.split(".")[-1] for e in c.elements), c.ondelete, c.onupdate)
                            for c in frozen.foreign_key_constraints}
        if expected_foreign != actual_foreign:
            raise RuntimeError("Incompatible existing foreign keys: " + name)
        expected_unique = {tuple(c.columns.keys()) for c in frozen.constraints if isinstance(c, sa.UniqueConstraint)}
        actual_unique = {tuple(c["column_names"]) for c in inspector.get_unique_constraints(name)}
        if not expected_unique.issubset(actual_unique):
            raise RuntimeError("Missing existing uniqueness constraint: " + name)
        return
    op.create_table(name, *columns, **kwargs)

def _create_index(name, table_name, columns, **kwargs):
    actual = {index["name"]: index for index in sa.inspect(op.get_bind()).get_indexes(table_name)}
    if name in actual:
        if actual[name]["column_names"] != columns or actual[name]["unique"] != bool(kwargs.get("unique", False)):
            raise RuntimeError("Incompatible existing index: " + name)
        return
    op.create_index(name, table_name, columns, **kwargs)
'''
    for revision, previous, operations, label in (
        ("20261007_01", None, baseline, "Frozen original wallet baseline"),
        ("20261007_02", "20261007_01", additions, "API, security, AI governance, durable workers and query indexes"),
    ):
        path = output / (revision + ".py")
        if path.exists():
            raise RuntimeError("Frozen migrations already exist; create a new revision instead.")
        body = render_python_code(UpgradeOps(operations)).replace("op.create_table(", "_create_table(").replace("op.create_index(", "_create_index(")
        text = f'"""{label}. Generated from the reviewed schema on 7 October 2026."""\nimport os\nimport sqlalchemy as sa\nfrom alembic import op\n\nrevision = {revision!r}\ndown_revision = {previous!r}\nbranch_labels = None\ndepends_on = None\n' + helpers + '\ndef upgrade():\n' + body + '\n\ndef downgrade():\n    raise RuntimeError("Destructive downgrade disabled; restore a tested database backup instead.")\n'
        path.write_text(text, encoding="utf-8", newline="\n")
    print(f"Frozen {len(original)} baseline tables and {len(db.metadata.tables) - len(original)} added tables.")


if __name__ == "__main__":
    main()
