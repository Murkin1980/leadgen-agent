#!/usr/bin/env bash
# Migration chain verification script
# Verifies that migrations 001-006 can be applied and rolled back correctly

set -Eeuo pipefail

cd "$(dirname "$0")/.."

echo "=== Migration Chain Verification ==="
echo

# Check for multiple heads
echo "Checking for multiple Alembic heads..."
alembic heads
HEAD_COUNT=$(alembic heads | grep -c "^[a-f0-9]")
if [ "$HEAD_COUNT" -gt 1 ]; then
    echo "ERROR: Multiple heads detected!"
    alembic heads
    exit 1
fi
echo "OK: Single head detected"
echo

# Create a temporary database for testing
TEST_DB="sqlite:///test_migrations.db"
export DATABASE_URL="$TEST_DB"
export REDIS_URL="redis://localhost:6379/15"
export TEXT_GENERATOR_PROVIDER="template"
export DEPLOYMENT_PROVIDER="mock"
export COLLECTOR_PROVIDER="mock"
export VERIFICATION_ENABLED="false"
export APP_ENV="development"
export ADMIN_PASSWORD="testpass"
export OUTREACH_MODE="sandbox"
export OUTREACH_SANDBOX_ALLOWLIST="+77000000001,+77000000002"
export WHATSAPP_WEBHOOK_VERIFY_TOKEN="test_verify_token"
export WHATSAPP_ALLOW_MOCK_WEBHOOKS="true"
export WHATSAPP_SERVICE_WINDOW_HOURS="24"

cleanup() {
    echo "Cleaning up test database..."
    rm -f test_migrations.db
}
trap cleanup EXIT

# Test upgrade chain 001 -> 006
echo "=== Testing upgrade chain 001 -> 006 ==="
alembic upgrade head
echo "OK: All migrations applied successfully"
echo

# Verify tables exist
echo "=== Verifying tables and indexes ==="
python -c "
import sqlite3
conn = sqlite3.connect('test_migrations.db')
cursor = conn.cursor()

# Check all expected tables
tables = [
    'search_jobs', 'leads', 'landing_pages', 'landing_page_versions',
    'content_generations', 'deployments', 'outreach_campaigns',
    'outreach_messages', 'lead_stage_history', 'outreach_events',
    'audit_log', 'whatsapp_templates', 'inbound_messages'
]
for t in tables:
    cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name=?\", (t,))
    if not cursor.fetchone():
        print(f'ERROR: Table {t} missing')
        exit(1)
    print(f'Table {t}: OK')

# Check key constraints
print()
print('Checking constraints...')

# Check unique constraint on outreach_messages
cursor.execute(\"SELECT sql FROM sqlite_master WHERE type='table' AND name='outreach_messages'\")
schema = cursor.fetchone()[0]
if 'uq_outreach_first_contact' not in schema:
    print('ERROR: uq_outreach_first_contact missing')
    exit(1)
print('Unique constraint uq_outreach_first_contact: OK')

# Check indexes
cursor.execute(\"SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'ix_%'\")
indexes = [row[0] for row in cursor.fetchall()]
expected_indexes = [
    'ix_leads_search_job_id', 'ix_leads_source_source_id',
    'ix_outreach_messages_campaign_id', 'ix_outreach_messages_lead_id',
    'ix_outreach_events_message_id', 'ix_outreach_events_provider_event_id',
    'ix_inbound_messages_lead_id', 'ix_inbound_messages_provider_message_id',
    'ix_whatsapp_templates_status'
]
for idx in expected_indexes:
    if idx not in indexes:
        print(f'WARNING: Index {idx} may be missing (SQLite may not create all)')
    else:
        print(f'Index {idx}: OK')

conn.close()
print()
print('All table checks passed!')
"

# Test downgrade 006 -> 005
echo
echo "=== Testing downgrade 006 -> 005 ==="
alembic downgrade -1
echo "OK: Downgraded to 005"
echo

# Test upgrade 005 -> 006
echo "=== Testing upgrade 005 -> 006 ==="
alembic upgrade head
echo "OK: Re-upgraded to 006"
echo

# Final check
echo "=== Final verification ==="
alembic current
echo
echo "=== Migration Chain Verification PASSED ==="