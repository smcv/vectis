#!/bin/sh
# vim:set ft=sh sw=4 sts=4 et:

set -e
set -u
set -x

if [ -n "${VECTIS_UNINSTALLED:-}" ]; then
    VECTIS="${VECTIS_UNINSTALLED}/run"
else
    VECTIS=vectis
fi

storage="$(mktemp -d)"
arch="$(dpkg --print-architecture)"

if [ -z "${VECTIS_TEST_UBUNTU_MIRROR:-}" ]; then
    echo "1..0 # SKIP This test requires VECTIS_TEST_UBUNTU_MIRROR=http://192.168.122.1:3142/ubuntu or similar"
    exit 0
fi

echo "1..1"

"$VECTIS" --vendor=ubuntu --storage="${storage}" \
    new \
    --mirror="${VECTIS_TEST_UBUNTU_MIRROR}" \
    --suite=devel

image="$(cd "${storage}" && ls -1 vectis-ubuntu-*-"${arch}".qcow2)"

"$VECTIS" --vendor=debian --storage="${storage}" sbuild \
    --mirror="${VECTIS_TEST_UBUNTU_MIRROR}" \
    --worker="qemu $image" \
    --suite=devel \
    hello

rm -fr "${storage}"

echo "ok 1"
