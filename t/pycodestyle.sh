#!/bin/sh
# Copyright © 2016-2018 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

if [ "x${PYCODESTYLE:=pycodestyle}" = xfalse ] || \
        [ -z "$(command -v "$PYCODESTYLE")" ]; then
    echo "1..0 # SKIP pycodestyle not found"
elif "${PYCODESTYLE}" vectis/ >&2; then
    echo "1..1"
    echo "ok 1 - $PYCODESTYLE reported no issues"
else
    echo "1..1"
    echo "not ok 1 # TODO $PYCODESTYLE issues reported"
fi

# vim:set sw=4 sts=4 et:
