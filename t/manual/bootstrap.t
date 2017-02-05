#!/bin/sh
# vim:set ft=sh sw=4 sts=4 et:

set -e
set -u
set -x

if [ -z "${VECTIS_TEST_SUDO:-}" ]; then
    echo "1..0 # SKIP This test requires VECTIS_TEST_SUDO=sudo or similar"
    exit 0
fi

if [ -z "${VECTIS_TEST_DEBIAN_MIRROR:-}" ]; then
    echo "1..0 # SKIP This test requires VECTIS_TEST_DEBIAN_MIRROR=http://192.168.122.1:3142/debian or similar"
    exit 0
fi

echo "1..1"

storage="$(mktemp -d)"

( cd "$storage"; apt-get --download-only source hello )

PYTHONPATH=$(pwd) "$VECTIS_TEST_SUDO" ./run --storage="${storage}" bootstrap \
    --mirror="${VECTIS_TEST_DEBIAN_MIRROR}" --size=23G
PYTHONPATH=$(pwd) ./run --storage="${storage}" sbuild-tarball \
    --mirror="${VECTIS_TEST_DEBIAN_MIRROR}" --suite=sid
PYTHONPATH=$(pwd) ./run --storage="${storage}" sbuild \
    --mirror="${VECTIS_TEST_DEBIAN_MIRROR}" --suite=sid "${storage}/"hello*.dsc
rm -fr "${storage}"

echo "ok 1"
