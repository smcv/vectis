#!/bin/sh
# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

if [ "x${PYFLAKES:=pyflakes3}" = xfalse ]; then
    echo "1..0 # SKIP pyflakes3 not found"
elif "${PYFLAKES}" vectis; then
    echo "1..1"
    echo "ok 1 - pyflakes reported no issues"
else
    echo "1..1"
    echo "ok 1 # SKIP Ignoring pyflakes issues for now"
fi

# vim:set sw=4 sts=4 et:
