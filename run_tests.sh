#!/usr/bin/env bash

py_ver=$(python -c 'import sys; print(sys.version)')
echo "Python version: ${py_ver}"
[ -f .coverage ] && \rm .coverage
PYTHONPATH="$(pwd)" coverage run -m pytest tests/ -v "$@"
coverage report -m --omit="tests/*"
