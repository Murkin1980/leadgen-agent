#!/bin/bash
set -e

cd "$(dirname "$0")/.."

if [ -z "$(git status sites/public --porcelain)" ]; then
    echo "No changes to publish."
    exit 0
fi

git add sites/public
git commit -m "Publish landing pages $(date +%Y-%m-%d)"
git push
echo "Git published to origin."
