#!/bin/bash
set -e

cd "$(dirname "$0")/.."

echo "Deploying to Cloudflare Pages..."
npx wrangler pages deploy sites/public --project-name leadgen-agent --branch main --commit-dirty=true

echo "Done. https://leadgen-agent.pages.dev/"
