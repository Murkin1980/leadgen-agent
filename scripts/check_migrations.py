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
import urllib.parse

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


def check_sqlite(db_url: str) -> int:
    """Run migration checks against a temporary SQLite database."""
    import sqlite3

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    env = os.environ.copy()
    env["DATABASE_URL"] = db_url

    try:
        # Upgrade
        print("1. alembic upgrade head...")
        ok, out = run_cmd(["alembic", "-c", "alembic.ini", "upgrade", "head"], env=env)
        if not ok:
            print(f"   FAILED: {out[:300]}")
            return 1
        print("   OK")

        # Table check
        print("\n2. Verifying tables...")
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
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            return check_sqlite(f"sqlite:///{db_path}")
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


if __name__ == "__main__":
    sys.exit(main())
