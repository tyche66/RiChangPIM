#!/bin/bash
# 容器内安装 Linux 版 Node（官方二进制，不污染宿主 node_modules），返回版本号
set -uo pipefail
NODE_VER="${NODE_VER:-24.18.0}"
PREFIX=/usr/local/node
BIN="$PREFIX/bin/node"
if [ ! -x "$BIN" ]; then
  mkdir -p "$PREFIX"
  TARBALL="/tmp/node-v${NODE_VER}-linux-x64.tar.xz"
  if [ ! -f "$TARBALL" ]; then
    curl -fsSL "https://nodejs.org/dist/v${NODE_VER}/node-v${NODE_VER}-linux-x64.tar.xz" -o "$TARBALL" || exit 2
  fi
  tar -xJf "$TARBALL" -C "$PREFIX" --strip-components=1 || exit 3
fi
"$BIN" --version