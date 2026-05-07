#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== 1. Git state ==="
git status -sb
git log -1 --oneline

if [ -n "$(git status --porcelain)" ]; then
  echo "FAIL: working tree not clean"
  exit 1
fi

echo "=== 2. Local tests ==="
python -m pytest --tb=short -q
echo "Tests passed."

echo "=== 3. Secret scan (source only) ==="
if grep -rn -E '(sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{30,}|AKIA[A-Z0-9]{16}|-----BEGIN)' \
     --include='*.py' --include='*.yaml' --include='*.yml' --include='*.toml' \
     --include='*.json' --include='*.md' src/ config/ deploy/ docs/ examples/ tests/ \
     2>/dev/null; then
  echo "FAIL: potential secret found"
  exit 1
fi
echo "No raw secrets in source."

echo "=== 4. CHANGELOG current ==="
if ! head -5 CHANGELOG.md | grep -q "0.14.0"; then
  echo "FAIL: CHANGELOG top entry is not 0.14.0"
  exit 1
fi
echo "CHANGELOG top entry: 0.14.0"

echo "=== 5. Forbidden terms in user-facing copy ==="
if grep -rni -E '(guarantee|การันตี|แน่นอน|100%)' --include='*.md' --include='*.py' \
     src/ config/ docs/ examples/ 2>/dev/null | grep -v 'forbid_terms\|forbid'; then
  echo "WARN: review above lines for quality-gate violations"
fi

echo "=== ALL PRE-DEPLOY CHECKS PASSED ==="
