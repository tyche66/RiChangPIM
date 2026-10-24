#!/bin/bash
export PATH="$HOME/.nvm/versions/node/v24.18.0/bin:$PATH"
cd /home/AI-PIM/RiChangPIM/frontend || exit 9
./node_modules/.bin/eslint . -f unix 2>&1 | tail -15
