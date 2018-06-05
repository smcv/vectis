#!/bin/sh
# Copyright © 2016-2018 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

MYPYPATH=$("${PYTHON:-python3}" -c '
import sys

path = []

for p in sys.path:
    if "-packages" in p or "/usr" not in p:
        path.append(p)

print(":".join(path))')
export MYPYPATH

if [ "x${MYPY:=mypy}" = xfalse ]; then
    echo "1..0 # SKIP mypy not found"
elif "${MYPY}" \
        --python-executable="${PYTHON:=python3}" \
        --follow-imports=skip \
        -p vectis; then
    echo "1..1"
    echo "ok 1 - mypy reported no issues"
else
    echo "1..1"
    echo "not ok 1 # TODO mypy issues reported"
fi

# vim:set sw=4 sts=4 et:
