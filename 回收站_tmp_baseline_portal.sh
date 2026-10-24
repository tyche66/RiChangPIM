#!/bin/bash
export PATH="$HOME/.nvm/versions/node/v24.18.0/bin:$PATH"
cd /home/AI-PIM/RiChangPIM/portal || exit 9
./node_modules/.bin/vite build > /tmp/portal-build.log 2>&1
echo "portal build exit=$?"
tail -4 /tmp/portal-build.log
