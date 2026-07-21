#!/usr/bin/env bash
# One-time GitHub repository metadata setup (audit 11-1). Requires the repo owner
# to be authenticated with the GitHub CLI (`gh auth login`). Fills in the About
# description, homepage, topics, and enables Discussions — currently all empty,
# which is the cheapest discoverability win available.
#
#   ./scripts/setup_github_metadata.sh
set -euo pipefail

REPO="${REPO:-mohitmishra786/readprism}"
HOMEPAGE="${HOMEPAGE:-https://readprism.app}"

# ~128-char, keyword-first description (github skill guidance).
DESCRIPTION="Self-hostable RSS/newsletter reader that ranks your daily digest by how you actually read — a behavioral, explainable ranking engine. Open source."

# 6–20 lowercase-hyphen topics mixing technology + purpose + category.
TOPICS=(
  rss-reader self-hosted content-aggregation personalization machine-learning
  fastapi nextjs pgvector recommendation-engine newsletter
  news-aggregator open-source explainable-ai
)

echo "Setting description + homepage on $REPO ..."
gh repo edit "$REPO" --description "$DESCRIPTION" --homepage "$HOMEPAGE" --enable-discussions

echo "Setting topics ..."
gh repo edit "$REPO" $(printf -- '--add-topic %s ' "${TOPICS[@]}")

echo "Done. Verify at https://github.com/$REPO"
