"""
Convert loans.borrower_id from text/char(36) to native UUID

This migration is safe when existing borrower_id values are valid UUID strings.
It performs these steps:
 1. Add borrower_id_new UUID NULL
 2. Backfill borrower_id_new = borrower_id::uuid for rows where borrower_id looks like a UUID
 3. Abort if any non-null borrower_id couldn't be cast to uuid
 4. Drop foreign key constraint on loans.borrower_id (if exists)
 5. Drop old borrower_id column
 6. Rename borrower_id_new -> borrower_id
 7. Recreate FK constraint and index

Downgrade will attempt to reverse by casting uuid back to text. Use with caution.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection

# revision identifiers, used by Alembic.
revision = "b3aa2f5d9c07"
down_revision = "408743feea24"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind: Connection = op.get_bind()
    inspector = sa.inspect(bind)

    # 1) Add new nullable UUID column
    with op.batch_alter_table("loans") as batch_op:
        batch_op.add_column(sa.Column("borrower_id_new", postgresql.UUID(as_uuid=True), nullable=True))

    # 2) Backfill borrower_id_new depending on current borrower_id column type
    cols = inspector.get_columns("loans")
    old_col = next((c for c in cols if c.get("name") == "borrower_id"), None)

    if old_col is None:
        # No existing borrower_id column — nothing to backfill
        pass
    else:
        col_type = old_col.get("type")
        # If borrower_id is already UUID-typed, copy directly
        try:
            is_uuid_type = isinstance(col_type, postgresql.UUID)
        except Exception:
            # Fallback: inspect type name
            is_uuid_type = "UUID" in str(col_type).upper()

        if is_uuid_type:
            op.execute(
                """
                UPDATE loans
                SET borrower_id_new = borrower_id
                WHERE borrower_id IS NOT NULL
                """
            )
        else:
            # borrower_id stored as text — use safe regex cast for values that look like UUIDs
            op.execute(
                """
                UPDATE loans
                SET borrower_id_new = borrower_id::uuid
                WHERE borrower_id ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
                """
            )

        # 3) Verify there are no non-null borrower_id rows that failed to backfill
        invalid_count = bind.execute(
            sa.text(
                "SELECT COUNT(1) FROM loans WHERE borrower_id IS NOT NULL AND borrower_id_new IS NULL"
            )
        ).scalar()

        if invalid_count and int(invalid_count) > 0:
            raise RuntimeError(
                f"Migration aborted: {invalid_count} rows have non-UUID borrower_id values."
            )

    # 4) Drop foreign key constraint(s) referencing users.id on loans.borrower_id
    fks = inspector.get_foreign_keys("loans")
    for fk in fks:
        # If the foreign key references the users table on borrower_id, drop it
        if fk.get("referred_table") == "users" and "borrower_id" in fk.get("constrained_columns", []):
            op.drop_constraint(fk.get("name"), "loans", type_="foreignkey")

    # 5) Drop old borrower_id column (if present)
    if old_col is not None:
        with op.batch_alter_table("loans") as batch_op:
            batch_op.drop_column("borrower_id")

    # 6) Rename borrower_id_new -> borrower_id
    with op.batch_alter_table("loans") as batch_op:
        batch_op.alter_column("borrower_id_new", new_column_name="borrower_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)

    # 7) Recreate foreign key constraint and index
    op.create_foreign_key("fk_loans_borrower_id_users", "loans", "users", ["borrower_id"], ["id"]) 
    op.create_index("ix_loans_borrower_id", "loans", ["borrower_id"]) 


def downgrade() -> None:
    bind: Connection = op.get_bind()
    inspector = sa.inspect(bind)

    # 1) Add old text column back as borrower_id_old
    with op.batch_alter_table("loans") as batch_op:
        batch_op.add_column(sa.Column("borrower_id_old", sa.String(36), nullable=True))

    # 2) Backfill borrower_id_old from uuid borrower_id
    op.execute(
        """
        UPDATE loans
        SET borrower_id_old = borrower_id::text
        WHERE borrower_id IS NOT NULL
        """
    )

    # 3) Drop FK on loans.borrower_id if exists
    fks = inspector.get_foreign_keys("loans")
    for fk in fks:
        if fk.get("referred_table") == "users" and "borrower_id" in fk.get("constrained_columns", []):
            op.drop_constraint(fk.get("name"), "loans", type_="foreignkey")

    # 4) Drop uuid borrower_id column
    with op.batch_alter_table("loans") as batch_op:
        batch_op.drop_column("borrower_id")

    # 5) Rename borrower_id_old -> borrower_id (text)
    with op.batch_alter_table("loans") as batch_op:
        batch_op.alter_column("borrower_id_old", new_column_name="borrower_id", existing_type=sa.String(36), nullable=True)

    # 6) Recreate FK (note: this will likely fail if users.id is uuid and types mismatch)
    # Re-create as plain text foreign key only if users.id is text — handle with care in production
    try:
        op.create_foreign_key("fk_loans_borrower_id_users", "loans", "users", ["borrower_id"], ["id"]) 
    except Exception:
        # Skip if incompatible
        pass

    # Index
    try:
        op.create_index("ix_loans_borrower_id", "loans", ["borrower_id"]) 
    except Exception:
        pass
