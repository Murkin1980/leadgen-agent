#!/bin/bash
set -Eeuo pipefail

cd "$(dirname "$0")/.."

PROJECT="${CLOUDFLARE_PAGES_PROJECT:-leadgen-agent}"
BRANCH="${CLOUDFLARE_PAGES_BRANCH:-master}"

if [ -z "${CLOUDFLARE_API_TOKEN:-}" ]; then
    echo "ERROR: CLOUDFLARE_API_TOKEN is not set." >&2
    exit 1
fi

if [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]; then
    echo "ERROR: CLOUDFLARE_ACCOUNT_ID is not set." >&2
    exit 1
fi

if [ ! -d "sites/public" ]; then
    echo "ERROR: sites/public/ directory not found." >&2
    exit 1
fi

if [ -z "$(ls -A sites/public 2>/dev/null)" ]; then
    echo "ERROR: sites/public/ is empty. Nothing to deploy." >&2
    exit 1
fi

WRANGLER=""
if [ -x "./node_modules/.bin/wrangler" ]; then
    WRANGLER="./node_modules/.bin/wrangler"
elif command -v wrangler &>/dev/null; then
    WRANGLER="wrangler"
else
    echo "ERROR: Wrangler not found. Run 'npm ci' first." >&2
    exit 1
fi

echo "Deploying to Cloudflare Pages..."
echo "  Project: $PROJECT"
echo "  Branch:  $BRANCH"
echo "  Wrangler: $WRANGLER"

$WRANGLER pages deploy sites/public \
    --project-name "$PROJECT" \
    --branch "$BRANCH" \
    --commit-dirty=true

echo "Deployed to https://${PROJECT}.pages.dev/"
