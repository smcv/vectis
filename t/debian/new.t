#!/bin/sh
# vim:set ft=sh sw=4 sts=4 et:

set -e
set -u
set -x

if [ -n "${VECTIS_UNINSTALLED:-}" ]; then
    VECTIS="${PYTHON:-python3} ${VECTIS_UNINSTALLED}/run"
else
    VECTIS=vectis
fi

storage="$(mktemp --tmpdir -d vectis-test-XXXXXXXXXX)"
arch="$(dpkg --print-architecture)"

mkdir -p "${storage}/${arch}/debian/sid"
ln -s "${XDG_CACHE_HOME:-"${HOME}/.cache"}/vectis/${arch}/debian/sid/autopkgtest.qcow2" "${storage}/${arch}/debian/sid/"
ln -s "${XDG_CACHE_HOME:-"${HOME}/.cache"}/vectis/${arch}/debian/sid/sbuild.tar.gz" "${storage}/${arch}/debian/sid/"

if ! [ -f "${storage}/${arch}/debian/sid/autopkgtest.qcow2" ]; then
    echo "1..0 # SKIP ${storage}/vectis/${arch}/debian/sid/autopkgtest.qcow2 not found"
    exit 0
fi

if ! [ -f "${storage}/${arch}/debian/sid/sbuild.tar.gz" ]; then
    echo "1..0 # SKIP ${storage}/vectis/${arch}/debian/sid/sbuild.tar.gz not found"
    exit 0
fi

if [ -z "${VECTIS_TEST_DEBIAN_MIRROR:-}" ]; then
    echo "1..0 # SKIP This test requires VECTIS_TEST_DEBIAN_MIRROR=http://192.168.122.1:3142/debian or similar"
    exit 0
fi

echo "1..1"

$VECTIS --vendor=debian --storage="${storage}" \
    new \
    --mirror="${VECTIS_TEST_DEBIAN_MIRROR}" \
    --worker="qemu ${storage}/${arch}/debian/sid/autopkgtest.qcow2" \
    --suite=sid
test ! -L "${storage}/${arch}/debian/sid/autopkgtest.qcow2"
$VECTIS --vendor=debian --storage="${storage}" sbuild \
    --mirror="${VECTIS_TEST_DEBIAN_MIRROR}" \
    --worker="qemu ${storage}/${arch}/debian/sid/autopkgtest.qcow2" \
    --suite=sid \
    hello
rm -fr "${storage}"

echo "ok 1"
