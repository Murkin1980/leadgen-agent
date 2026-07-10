#!/bin/bash
set -Eeuo pipefail

cd "$(dirname "$0")/.."

PROJECT="${CLOUDFLARE_PAGES_PROJECT:-leadgen-agent}"
BRANCH="${CLOUDFLARE_PAGES_BRANCH:-master}"

if ! command -v npx &>/dev/null; then
    echo "ERROR: npx not found. Install Node.js." >&2
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

echo "Deploying to Cloudflare Pages..."
echo "  Project: $PROJECT"
echo "  Branch:  $BRANCH"

npx wrangler pages deploy sites/public \
    --project-name "$PROJECT" \
    --branch "$BRANCH" \
    --commit-dirty=true

echo "Deployed to https://${PROJECT}.pages.dev/"
