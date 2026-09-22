#!/usr/bin/env bash
# Publish this source with dev attribution, using the operator's own GitHub login.
set -euo pipefail
cd "$(dirname "$0")/.."
repo="devendrayadv/gramrail"
command -v gh >/dev/null || { echo "Install GitHub CLI (gh) and run gh auth login first." >&2; exit 1; }
command -v git >/dev/null || { echo "Git is required." >&2; exit 1; }
login="$(gh api user --jq .login)"
if [[ "$login" != "devendrayadv" ]]; then
  echo "Authenticated as $login, not devendrayadv. Switch the GitHub CLI account first." >&2
  exit 1
fi
if [[ -d .github/workflows ]]; then
  echo "Review GitHub Actions triggers before publishing. This script refuses unreviewed workflows." >&2
  exit 1
fi
if [[ ! -d .git ]]; then
  git init -b main
  git config user.name "dev"
  git config user.email "120010820+devendrayadv@users.noreply.github.com"
  git add .
  git commit -m "feat: introduce GramRail alpha foundation"
else
  if [[ -n "$(git status --porcelain)" ]]; then
    echo "Working tree is not clean. Review and commit local changes before publishing." >&2
    exit 1
  fi
fi
if gh repo view "$repo" --json name >/dev/null 2>&1; then
  visibility="$(gh repo view "$repo" --json visibility --jq .visibility)"
  [[ "$visibility" == "PUBLIC" ]] || { echo "Existing repository is not public. Visibility was not changed." >&2; exit 1; }
  # Never force-push over an existing history.
  git push "https://github.com/$repo.git" HEAD:refs/heads/main
else
  gh repo create "$repo" --public \
    --description "Reusable features and a durable runtime for Telegram applications. By dev." \
    --source . --push
fi
echo "Published source to https://github.com/$repo"
