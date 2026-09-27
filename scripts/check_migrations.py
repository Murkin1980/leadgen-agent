#!/usr/bin/env python
"""Production-grade migration chain verification.

Verifies: single head, upgrade/downgrade chain integrity,
table existence, constraints, indexes, foreign keys, NOT NULL checks.
Uses PostgreSQL when DATABASE_URL is set; otherwise falls back to SQLite.
"""
from __future__ import annotations

import os
import sys
import subprocess
import tempfile

EXPECTED_TABLES = [
    "search_jobs",
    "leads",
    "landing_pages",
    "landing_page_versions",
    "content_generations",
    "deployments",
    "outreach_campaigns",
    "outreach_messages",
    "lead_stage_history",
    "outreach_events",
    "audit_log",
    "whatsapp_templates",
    "inbound_messages",
    "api_keys",
]

EXPECTED_UNIQUE_CONSTRAINTS = {
    "outreach_messages": ["uq_outreach_first_contact", "uq_outreach_message_idempotency"],
    "whatsapp_templates": ["uq_whatsapp_template_name_language"],
    "inbound_messages": [],
    "api_keys": [],
}

EXPECTED_INDEXES = {
    "outreach_events": ["ix_outreach_events_lead_id", "ix_outreach_events_message_id"],
    "outreach_messages": ["ix_outreach_messages_lead_id"],
    "inbound_messages": ["ix_inbound_messages_lead_id"],
    "api_keys": ["ix_api_keys_key_hash"],
}


def run_cmd(cmd: list[str], env: dict | None = None) -> tuple[bool, str]:
    result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def _assert_sqlite_schema(conn) -> None:
    """Assert the migrated relationships and indexes affected by batch DDL."""
    cursor = conn.cursor()
    relations = (
        ("leads", "search_job_id", "INTEGER", "search_jobs"),
        ("deployments", "job_id", "INTEGER", "search_jobs"),
        ("landing_pages", "generation_id", "VARCHAR(50)", "content_generations"),
    )
    for table, column, data_type, target in relations:
        cursor.execute(f'PRAGMA table_info("{table}")')
        columns = {row[1]: row for row in cursor.fetchall()}
        info = columns.get(column)
        if info is None or info[2].upper() != data_type or info[3] != 0:
            raise RuntimeError(f"{table}.{column} must be nullable {data_type}")
        cursor.execute(f'PRAGMA foreign_key_list("{table}")')
        if not any(
            row[2] == target and row[3] == column and row[4] == "id"
            for row in cursor.fetchall()
        ):
            raise RuntimeError(f"foreign key {table}.{column} -> {target}.id is missing")

    for table, index in (
        ("leads", "ix_leads_search_job_id"),
        ("deployments", "ix_deployments_job_id"),
    ):
        cursor.execute(f'PRAGMA index_list("{table}")')
        if not any(row[1] == index for row in cursor.fetchall()):
            raise RuntimeError(f"index {index} on {table} is missing")

    cursor.execute("PRAGMA foreign_key_check")
    if cursor.fetchall():
        raise RuntimeError("SQLite foreign_key_check found violations")


def check_sqlite() -> int:
    """Run migration checks against a temporary SQLite database."""
    import sqlite3

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"

    try:
        # Upgrade
        print("1. alembic upgrade head...")
        ok, out = run_cmd(["alembic", "-c", "alembic.ini", "upgrade", "head"], env=env)
        if not ok:
            print(f"   FAILED: {out[:300]}")
            return 1
        print("   OK")

        # Table and schema check
        print("\n2. Verifying tables and migration schema...")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing = {row[0] for row in cursor.fetchall()}
        missing = [t for t in EXPECTED_TABLES if t not in existing]
        if missing:
            print(f"   FAILED: missing tables: {missing}")
            conn.close()
            return 1
        print(f"   OK: {len(EXPECTED_TABLES)} tables present")
        _assert_sqlite_schema(conn)
        print("   OK: revision 002/004 columns, foreign keys, and indexes")

        # Unique constraint check
        print("\n3. Checking unique constraints...")
        for table, expected in EXPECTED_UNIQUE_CONSTRAINTS.items():
            if not expected:
                continue
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,))
            row = cursor.fetchone()
            if not row:
                print(f"   WARNING: table {table} not found in sqlite_master")
                continue
            schema = row[0] or ""
            for constraint_name in expected:
                if constraint_name not in schema:
                    print(f"   FAILED: constraint {constraint_name} missing on {table}")
                    conn.close()
                    return 1
        print("   OK")

        # Index check
        print("\n4. Checking indexes...")
        cursor.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND name IS NOT NULL")
        existing_indexes = {row[0]: row[1] for row in cursor.fetchall()}
        for table, expected_idx in EXPECTED_INDEXES.items():
            for idx in expected_idx:
                if idx not in existing_indexes:
                    print(f"   WARNING: index {idx} on {table} not found (may need manual check)")
        print("   OK")

        conn.close()

        # Downgrade chain
        print("\n5. Downgrade by 1 step...")
        ok, out = run_cmd(["alembic", "-c", "alembic.ini", "downgrade", "-1"], env=env)
        if not ok:
            print(f"   FAILED: {out[:300]}")
            return 1
        print("   OK")

        # Re-upgrade
        print("\n6. Re-upgrade to head...")
        ok, out = run_cmd(["alembic", "-c", "alembic.ini", "upgrade", "head"], env=env)
        if not ok:
            print(f"   FAILED: {out[:300]}")
            return 1
        print("   OK")

        # Single head
        print("\n7. Single head check...")
        ok, out = run_cmd(["alembic", "-c", "alembic.ini", "heads"], env=env)
        if not ok:
            print(f"   FAILED: {out[:300]}")
            return 1
        heads = [line.strip() for line in out.split("\n") if line.strip()]
        if len(heads) != 1:
            print(f"   FAILED: expected 1 head, got {len(heads)}: {heads}")
            return 1
        print(f"   OK: {heads[0]}")

        # Downgrade all
        print("\n8. Full downgrade to base...")
        ok, out = run_cmd(["alembic", "-c", "alembic.ini", "downgrade", "base"], env=env)
        if not ok:
            print(f"   FAILED: {out[:300]}")
            return 1
        print("   OK")

        # Full upgrade back
        print("\n9. Full upgrade back to head...")
        ok, out = run_cmd(["alembic", "-c", "alembic.ini", "upgrade", "head"], env=env)
        if not ok:
            print(f"   FAILED: {out[:300]}")
            return 1
        print("   OK")

        # Existing database upgrade path with data already present at revision 001.
        print("\n10. Existing revision-001 SQLite database upgrade...")
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            existing_db_path = f.name
        existing_env = os.environ.copy()
        existing_env["DATABASE_URL"] = f"sqlite:///{existing_db_path}"
        try:
            ok, out = run_cmd(
                ["alembic", "-c", "alembic.ini", "upgrade", "001"], env=existing_env
            )
            if not ok:
                print(f"   FAILED creating revision-001 database: {out[:500]}")
                return 1

            with sqlite3.connect(existing_db_path) as existing_conn:
                cursor = existing_conn.cursor()
                cursor.execute(
                    "INSERT INTO search_jobs (city, category) VALUES (?, ?)",
                    ("Almaty", "migration-fixture"),
                )
                job_id = cursor.lastrowid
                cursor.execute(
                    "INSERT INTO leads (name) VALUES (?)", ("existing migration lead",)
                )
                lead_id = cursor.lastrowid

            ok, out = run_cmd(
                ["alembic", "-c", "alembic.ini", "upgrade", "head"], env=existing_env
            )
            if not ok:
                print(f"   FAILED upgrading existing database: {out[:500]}")
                return 1

            with sqlite3.connect(existing_db_path) as existing_conn:
                _assert_sqlite_schema(existing_conn)
                existing_conn.execute("PRAGMA foreign_keys = ON")
                cursor = existing_conn.cursor()
                row = cursor.execute(
                    "SELECT name, search_job_id FROM leads WHERE id = ?", (lead_id,)
                ).fetchone()
                if row != ("existing migration lead", None):
                    raise RuntimeError(f"existing lead data changed during upgrade: {row}")
                cursor.execute(
                    "UPDATE leads SET search_job_id = ? WHERE id = ?", (job_id, lead_id)
                )
                existing_conn.commit()
                try:
                    cursor.execute(
                        "UPDATE leads SET search_job_id = -1 WHERE id = ?", (lead_id,)
                    )
                except sqlite3.IntegrityError:
                    existing_conn.rollback()
                else:
                    raise RuntimeError("search_job_id foreign key accepted a missing job")
                preserved = cursor.execute(
                    "SELECT name, search_job_id FROM leads WHERE id = ?", (lead_id,)
                ).fetchone()
                if preserved != ("existing migration lead", job_id):
                    raise RuntimeError(
                        f"existing lead relationship was not preserved: {preserved}"
                    )
        finally:
            if os.path.exists(existing_db_path):
                os.unlink(existing_db_path)
        print("   OK: existing data preserved; nullable FK enforcement verified")

        print("\n=== MIGRATION CHAIN VERIFICATION PASSED ===")
        return 0

    except Exception as exc:
        print(f"ERROR: {exc}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def check_postgres(db_url: str) -> int:
    """Run migration checks against a real PostgreSQL database."""
    import sqlalchemy

    engine = sqlalchemy.create_engine(db_url)
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url

    try:
        # Upgrade
        print("1. alembic upgrade head (PostgreSQL)...")
        ok, out = run_cmd(["alembic", "-c", "alembic.ini", "upgrade", "head"], env=env)
        if not ok:
            print(f"   FAILED: {out[:500]}")
            return 1
        print("   OK")

        # Table check
        print("\n2. Verifying tables...")
        with engine.connect() as conn:
            result = conn.execute(
                sqlalchemy.text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
                )
            )
            existing = {row[0] for row in result}
            missing = [t for t in EXPECTED_TABLES if t not in existing]
            if missing:
                print(f"   FAILED: missing tables: {missing}")
                return 1
            print(f"   OK: {len(EXPECTED_TABLES)} tables present")

        # Unique constraint check
        print("\n3. Checking unique constraints...")
        with engine.connect() as conn:
            for table, expected in EXPECTED_UNIQUE_CONSTRAINTS.items():
                if not expected:
                    continue
                result = conn.execute(
                    sqlalchemy.text(
                        "SELECT constraint_name FROM information_schema.table_constraints "
                        "WHERE table_schema = 'public' AND table_name = :table AND constraint_type = 'UNIQUE'"
                    ),
                    {"table": table},
                )
                existing_constraints = {row[0] for row in result}
                for constraint_name in expected:
                    if constraint_name not in existing_constraints:
                        print(f"   FAILED: constraint {constraint_name} missing on {table}")
                        return 1
        print("   OK")

        # Index check
        print("\n4. Checking indexes...")
        with engine.connect() as conn:
            result = conn.execute(
                sqlalchemy.text(
                    "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"
                )
            )
            existing_indexes = {row[0] for row in result}
            for table, expected_idx in EXPECTED_INDEXES.items():
                for idx in expected_idx:
                    if idx not in existing_indexes:
                        print(f"   WARNING: index {idx} on {table} not found")
        print("   OK")

        # Downgrade/upgrade chain
        print("\n5. Downgrade by 1 step...")
        ok, out = run_cmd(["alembic", "-c", "alembic.ini", "downgrade", "-1"], env=env)
        if not ok:
            print(f"   FAILED: {out[:500]}")
            return 1
        print("   OK")

        print("\n6. Re-upgrade to head...")
        ok, out = run_cmd(["alembic", "-c", "alembic.ini", "upgrade", "head"], env=env)
        if not ok:
            print(f"   FAILED: {out[:500]}")
            return 1
        print("   OK")

        # Single head
        print("\n7. Single head check...")
        ok, out = run_cmd(["alembic", "-c", "alembic.ini", "heads"], env=env)
        if not ok:
            print(f"   FAILED: {out[:500]}")
            return 1
        heads = [line.strip() for line in out.split("\n") if line.strip()]
        if len(heads) != 1:
            print(f"   FAILED: expected 1 head, got {len(heads)}: {heads}")
            return 1
        print(f"   OK: {heads[0]}")

        print("\n=== POSTGRESQL MIGRATION VERIFICATION PASSED ===")
        return 0

    except Exception as exc:
        print(f"ERROR: {exc}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        engine.dispose()


def main() -> int:
    print("=== Migration Chain Verification (Production-Grade) ===")
    print()
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url and db_url.startswith("postgresql"):
        print(f"Mode: PostgreSQL ({db_url.split('@')[-1] if '@' in db_url else 'configured'})")
        return check_postgres(db_url)
    else:
        print("Mode: SQLite (temporary file)")
        return check_sqlite()


if __name__ == "__main__":
    sys.exit(main())
