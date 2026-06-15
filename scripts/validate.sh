#!/usr/bin/env bash
# Validates the marketplace structure: JSON manifests + every skill's frontmatter.
# Uses python3 (universal) for JSON so there's nothing to install.
set -uo pipefail
fail=0
err(){ echo "❌ $*"; fail=1; }
ok(){ echo "✅ $*"; }

# $1 = json file, $2... = required top-level keys
check_json() {
  local f="$1"; shift
  if [ ! -f "$f" ]; then err "missing $f"; return; fi
  if ! python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$f" 2>/dev/null; then
    err "$f is not valid JSON"; return
  fi
  ok "$f valid JSON"
  for k in "$@"; do
    if ! python3 -c "import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if sys.argv[2] in d else 1)" "$f" "$k" 2>/dev/null; then
      err "$f missing key '$k'"
    fi
  done
}

# marketplace
check_json ".claude-plugin/marketplace.json" name plugins
python3 -c "import json; d=json.load(open('.claude-plugin/marketplace.json')); assert isinstance(d.get('plugins'),list) and d['plugins']" 2>/dev/null \
  && ok "marketplace lists at least one plugin" || err "marketplace.plugins missing/empty"

# plugins
shopt -s nullglob
for PJ in plugins/*/.claude-plugin/plugin.json; do
  check_json "$PJ" name version
done

# skills: each needs a SKILL.md with name+description frontmatter on line 1
for d in plugins/*/skills/*/; do
  S="${d}SKILL.md"
  if [ ! -f "$S" ]; then err "missing $S"; continue; fi
  head -1 "$S" | grep -q '^---' || { err "$S: frontmatter must start on line 1"; continue; }
  fm=$(awk 'NR==1{next} /^---/{exit} {print}' "$S")
  if echo "$fm" | grep -qE '^name:' && echo "$fm" | grep -qE '^description:'; then
    ok "$(basename "$d")/SKILL.md frontmatter ok"
  else
    err "$(basename "$d")/SKILL.md missing name/description in frontmatter"
  fi
done

echo "----"
if [ "$fail" -eq 0 ]; then echo "All checks passed."; else echo "Validation FAILED."; exit 1; fi
