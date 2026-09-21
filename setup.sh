#!/usr/bin/env bash
# HKUST e-Tendering Automation - Setup Check (check & report only)

cd "$(dirname "$0")" || exit 1

PASS=0
FAIL=0
WARN=0

# ANSI colors when attached to a terminal; plain markers otherwise
if [ -t 1 ]; then
  C_OK=$'\033[32m'; C_FAIL=$'\033[31m'; C_WARN=$'\033[33m'; C_OFF=$'\033[0m'
else
  C_OK=''; C_FAIL=''; C_WARN=''; C_OFF=''
fi

ok()   { printf '%s[OK]%s   %s\n'   "$C_OK"   "$C_OFF" "$1"; PASS=$((PASS+1)); }
fail() { printf '%s[FAIL]%s %s\n'  "$C_FAIL" "$C_OFF" "$1"; FAIL=$((FAIL+1)); }
warn() { printf '%s[WARN]%s %s\n'  "$C_WARN" "$C_OFF" "$1"; WARN=$((WARN+1)); }

echo
echo "=================================================="
echo " HKUST e-Tendering Automation - Setup Check"
echo "=================================================="
echo

# ---- 1) Python 3.11+ ----
PY=python3
command -v python3 >/dev/null 2>&1 || PY=python
if command -v "$PY" >/dev/null 2>&1; then
  if "$PY" -c 'import sys; sys.exit(sys.version_info < (3, 11))' >/dev/null 2>&1; then
    ok "Python 3.11+ found ($PY)"
  else
    fail "Python 3.11+ required (found an older version)"
  fi
else
  fail "Python not found on PATH - install Python 3.11+"
fi

# ---- 2) uv ----
if command -v uv >/dev/null 2>&1; then
  ok "uv found"
else
  fail "'uv' not found - install from https://docs.astral.sh/uv/getting-started/installation/"
fi

# ---- 3) Playwright Chromium ----
PW_DIR="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}"
if ls "$PW_DIR"/chromium-* >/dev/null 2>&1; then
  ok "Playwright Chromium found"
else
  fail "Playwright Chromium not found - run: uv run playwright install chromium"
fi

# ---- 4) .env file ----
if [ -f .env ]; then
  ok ".env file found"
else
  fail ".env missing - copy .env.example to .env and fill in the values"
  echo
  echo "--------------------------------------------------"
  echo "Summary: $PASS passed, $FAIL failed, $WARN warnings"
  [ "$FAIL" -eq 0 ] && exit 0 || exit 1
fi

# helper: read a key from .env (stripping comments/CR) and report empty/missing
check_env() {
  local key="$1" level="$2" val
  val=$(sed -n "s/^${key}=//p" .env | tail -n1 | tr -d '\r')
  if [ -n "$val" ]; then
    ok "${key} is set"
  elif [ "$level" = "WARN" ]; then
    warn "${key} is not set"
  else
    fail "${key} is not set in .env"
  fi
}

# ---- 5-7) .env variables ----
check_env HKUST_VENDOR_ID HARD
check_env HKUST_PASSWORD HARD
check_env GMAIL_APP_PASSWORD WARN

# ---- 8) BR certificate ----
BR_PATH=$(sed -n 's/^BR_CERTIFICATE_PATH=//p' .env | tail -n1 | tr -d '\r')
[ -n "$BR_PATH" ] || BR_PATH="assets/br_certificate.pdf"
if [ -f "$BR_PATH" ]; then
  ok "BR certificate found: $BR_PATH"
else
  warn "BR certificate not found at \"$BR_PATH\" - attachment will be skipped"
fi

echo
echo "--------------------------------------------------"
echo "Summary: $PASS passed, $FAIL failed, $WARN warnings"
echo "--------------------------------------------------"
if [ "$FAIL" -gt 0 ]; then
  echo "Fix the FAIL items above, then re-run this script."
  exit 1
fi
echo "All required checks passed."
exit 0
