#!/usr/bin/env bash

[ -f .coverage ] && \rm .coverage
PYTHONPATH="$(pwd)" uv run coverage run -m pytest tests/ -v "$@"
uv run coverage report -m --omit="tests/*"
