#!/usr/bin/env bash
set -euo pipefail

CERT_DIR="${1:-docker/nginx/certs}"
mkdir -p "$CERT_DIR"
chmod 700 "$CERT_DIR"

openssl req -x509 -nodes -newkey rsa:2048 -sha256 -days 365 \
  -keyout "$CERT_DIR/tls.key" \
  -out "$CERT_DIR/tls.crt" \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

chmod 600 "$CERT_DIR/tls.key"
echo "Development TLS certificate created in $CERT_DIR"
