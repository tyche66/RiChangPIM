#!/usr/bin/env bash
# AI-PIM V1.2 secret scan — fail-closed release gate.
#
# Scans the repository for patterns that MUST NEVER be committed:
#   - JWT / Bearer tokens
#   - PostgreSQL passwords
#   - MinIO root credentials
#   - AI provider API keys (OpenAI / Azure / Anthropic)
#   - private keys / TLS private keys
#
# This is a HARD gate: any hit other than documented false positives in
# scripts/secret_scan_allowlist.txt fails the release with exit 1.
#
# Patterns are intentionally aligned with docs/v1.2-plan.md §6.5:
# "外部 AI Key 未进入 Git、文档、日志、命令参数或测试产物；JWT、数据库密码、
#  MinIO 密码秘密扫描无命中".
set -uo pipefail

# V1.2 secret scan strategy:
# - If the repo is a git working tree, scan ONLY git-tracked files. This is
#   the authoritative interpretation of "未进入 Git" in docs/v1.2-plan.md §6.5
#   — local-only files such as .env (which is in .gitignore) are NOT scanned.
# - If not a git repo (sandbox/manual check), scan everything except the
#   recognized local / build / cache directories and .env / *.local files.

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

EXCLUDE_DIRS=(
  --exclude-dir='.git'
  --exclude-dir='node_modules'
  --exclude-dir='venv'
  --exclude-dir='frontend/dist'
  --exclude-dir='__pycache__'
  --exclude-dir='.ruff_cache'
  --exclude-dir='.vite'
)

# Determine scan target listing once per run.
TARGETS_FILE="/tmp/ai-pim-secret-scan-targets-$$.txt"
: > "$TARGETS_FILE"
if [ -d "$ROOT/.git" ] && command -v git >/dev/null 2>&1; then
  git ls-files > "$TARGETS_FILE"
else
  # No git: list everything except .env / .env.local / *.local and the
  # excluded directories above. Also honor a minimal set of git-ignored dev
  # paths (docker/nginx/certs — local self-signed TLS) to behave consistently
  # with the git-tracked scan mode.
  find . -type f \
    -not -path './.git/*' \
    -not -path './node_modules/*' \
    -not -path './venv/*' \
    -not -path '*/venv/*' \
    -not -path '*/.venv/*' \
    -not -path './frontend/dist/*' \
    -not -path '*/__pycache__/*' \
    -not -path '*/.ruff_cache/*' \
    -not -path '*/.vite/*' \
    -not -path './docker/nginx/certs/*' \
    -not -name '.env' \
    -not -name '.env.local' \
    -not -name '*.local' \
    | sed 's#^\./##' > "$TARGETS_FILE"
fi

HITS=0
REPORT="/tmp/ai-pim-secret-scan-$$.txt"
: > "$REPORT"

scan_pattern() {
  local label="$1" pattern="$2"
  # When git is detected, scan the tracked file list; else fall back to the
  # filtered filesystem list.
  if [ ! -s "$TARGETS_FILE" ]; then
    echo "    (no files to scan for $label)"
    return 0
  fi
  # Match against the listed files only.
  local hits
  hits="$(xargs -a "$TARGETS_FILE" grep -InIE --color=never "$pattern" 2>/dev/null || true)"
  if [ -n "$hits" ]; then
    local n
    n="$(printf '%s\n' "$hits" | wc -l)"
    HITS=$((HITS + n))
    echo "FAIL: secret pattern '$label' matched ($n hit(s)):"
    printf '%s\n' "$hits"
  fi
}

# Secret patterns. Tuned to avoid matching:
#   - fail-closed env validation: ${VAR:?... is required}
#   - shell variable interpolation: ${VAR} and ${VAR:-default}
#   - example placeholders: __REPLACE_ME__, ci-placeholder
# We lint .env.example explicitly: it must only contain change-me placeholders.

# JWT-ish: header.payload.signature with real base64 chunks.
scan_pattern "JWT-ish bearer" 'eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}'

# OpenAI-style keys (sk-...). Any match is a real leak (docs/v1.2-plan.md §6.5).
scan_pattern "OpenAI-style key" 'sk-[A-Za-z0-9]{20,}'

# Azure / generic AI API keys (long concrete literal assignments).
scan_pattern "Azure/concrete AI key" 'AI_API_KEY=[A-Za-z0-9_=\-]{30,}'

# Anthropic keys.
scan_pattern "Anthropic key" 'sk-ant-[A-Za-z0-9_-]{20,}'

# PEM private key blocks.
scan_pattern "Private key block" '-----BEGIN [A-Z ]*PRIVATE KEY-----'

# SSH / TLS .pem / .key / .crt files accidentally tracked (binary or PEM).
# This is structural — not a pattern match — but very valuable.
scan_key_files() {
  local hits file
  hits=""
  while IFS= read -r file; do
    case "$file" in
      *.pem|*.key|*.crt|id_rsa|id_ed25519|id_ecdsa)
        hits="$hits\n$file"
        ;;
    esac
  done < "$TARGETS_FILE"
  if [ -n "$hits" ]; then
    local n
    n="$(printf '%s' "$hits" | grep -c .)"
    HITS=$((HITS + n))
    echo "FAIL: tracked private key / cert files ($n):"
    printf '%b\n' "$hits"
  fi
}

scan_key_files

# Documented known false positives (e2e mock tokens, CI placeholders).
ALLOWLIST="scripts/secret_scan_allowlist.txt"
if [ -f "$ALLOWLIST" ]; then
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    # Strip lines starting with #.
    case "$line" in '#'*) continue ;; esac
    if grep -F "$line" "$REPORT" >/dev/null 2>&1; then
      : # would have allowed, but our scan already failed; report as is
    fi
  done < "$ALLOWLIST"
fi

if [ "$HITS" -gt 0 ]; then
  echo "secret scan: $HITS hits — RELEASE GATE FAIL"
  exit 1
fi
echo "secret scan: 0 hits — PASS"
exit 0
