#!/usr/bin/env python
"""Migration chain verification script."""
import sys
import os
import sqlite3
import subprocess
import tempfile

def run_cmd(cmd, env=None):
    """Run command and return (success, output)."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=env)
    return result.returncode == 0, result.stdout + result.stderr

def main():
    print("=== Migration Chain Verification ===")
    print()

    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        db_url = f"sqlite:///{db_path}"
        os.environ['DATABASE_URL'] = db_url

        # Run alembic upgrade head
        print("1. Testing alembic upgrade head...")
        ok, out = run_cmd(f"alembic -c alembic.ini upgrade head")
        if not ok:
            print(f"FAILED: {out}")
            return 1
        print("   OK: All migrations applied")

        # Verify tables exist
        print()
        print("2. Verifying tables exist...")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        expected_tables = [
            'search_jobs', 'leads', 'landing_pages', 'landing_page_versions',
            'content_generations', 'deployments', 'outreach_campaigns',
            'outreach_messages', 'lead_stage_history', 'outreach_events',
            'audit_log', 'whatsapp_templates', 'inbound_messages'
        ]

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing = {row[0] for row in cursor.fetchall()}

        for t in expected_tables:
            if t not in existing:
                print(f"   FAILED: Missing table {t}")
                return 1
            print(f"   OK: {t}")

        # Check unique constraint on outreach_messages
        print()
        print("3. Checking unique constraint...")
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='outreach_messages'")
        schema = cursor.fetchone()[0]
        if 'uq_outreach_first_contact' not in schema:
            print("   FAILED: uq_outreach_first_contact missing")
            return 1
        print("   OK: uq_outreach_first_contact exists")

        conn.close()

        # Test downgrade to 005
        print()
        print("4. Testing downgrade to 005...")
        ok, out = run_cmd(f"alembic -c alembic.ini downgrade -1")
        if not ok:
            print(f"   FAILED: {out}")
            return 1
        print("   OK: Downgraded to 005")

        # Test upgrade back to head
        print()
        print("5. Testing upgrade back to head...")
        ok, out = run_cmd(f"alembic -c alembic.ini upgrade head")
        if not ok:
            print(f"   FAILED: {out}")
            return 1
        print("   OK: Re-upgraded to head")

        # Check single head
        print()
        print("6. Checking single migration head...")
        ok, out = run_cmd(f"alembic -c alembic.ini heads")
        if not ok:
            print(f"   FAILED: {out}")
            return 1
        heads = [line.strip() for line in out.strip().split('\n') if line.strip()]
        if len(heads) != 1:
            print(f"   FAILED: Multiple heads: {heads}")
            return 1
        print(f"   OK: Single head - {heads[0]}")

        print()
        print("=== MIGRATION CHAIN VERIFICATION PASSED ===")
        return 0

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)

if __name__ == '__main__':
    sys.exit(main())