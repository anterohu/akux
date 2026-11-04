#!/usr/bin/env bash
# Akux – käynnistys Linuxissa ja macOS:ssä
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Asennetaan ohjelman tarvitsemat osat. Tämä tehdään vain ensimmäisellä kerralla."
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python -m akux "$@"
