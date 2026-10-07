"""Durable content-free conversation invalidation to close erasure races."""

import os
import sqlalchemy as sa
from alembic import op

revision = "20261007_03"
down_revision = "20261007_02"
branch_labels = None
depends_on = None


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

def upgrade():
    _create_table("ai_conversation_controls",
                    sa.Column("user_id", sa.Integer(), nullable=False),
                    sa.Column("generation", sa.Integer(), nullable=False),
                    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
                    sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
                    sa.PrimaryKeyConstraint("user_id"))
    _create_index("ix_ai_conversation_controls_updated_at", "ai_conversation_controls", ["updated_at"], unique=False)


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore a tested database backup instead.")
