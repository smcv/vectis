#!/bin/sh
# Copyright © 2016-2018 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

set -e
set -u

i=0

: "${SHELLCHECK:=shellcheck}"
exec 3>&1
exec >&2

if [ -z "$(command -v "$SHELLCHECK")" ]; then
    echo "1..0 # SKIP $SHELLCHECK not found" >&3
    exit 0
fi

for script in \
    t/*.sh \
    t/debian/*.t \
    t/ubuntu/*.t \
    vectis/setup-testbed \
; do
    i=$(( i + 1 ))

    if "$SHELLCHECK" "$script"; then
        echo "ok $i - $script" >&3
    else
        echo "not ok $i # TODO - $SHELLCHECK reported issues in $script" >&3
    fi
done

echo "1..$i" >&3

# vim:set sw=4 sts=4 et:
