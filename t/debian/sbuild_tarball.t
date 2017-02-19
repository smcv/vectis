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

: "${XDG_CACHE_HOME:="${HOME}/.cache"}"
arch="$(dpkg --print-architecture)"

if ! testing="$(debian-distro-info --testing)"; then
    echo "1..0 # SKIP Could not determine current Debian testing suite"
    exit 0
fi

# Currently used for the sbuild worker
if ! [ -f "${XDG_CACHE_HOME}/vectis/${arch}/debian/jessie/autopkgtest.qcow2" ]; then
    echo "1..0 # SKIP ${arch}/debian/jessie/autopkgtest.qcow2 not found"
    exit 0
fi

if ! [ -f "${XDG_CACHE_HOME}/vectis/${arch}/debian/${testing}/autopkgtest.qcow2" ]; then
    echo "1..0 # SKIP ${arch}/debian/${testing}/autopkgtest.qcow2 not found"
    exit 0
fi

if [ -z "${VECTIS_TEST_DEBIAN_MIRROR:-}" ]; then
    echo "1..0 # SKIP This test requires VECTIS_TEST_DEBIAN_MIRROR=http://192.168.122.1:3142/debian or similar"
    exit 0
fi

storage="$(mktemp --tmpdir -d vectis-test-XXXXXXXXXX)"

mkdir -p "${storage}/${arch}/debian/jessie"
mkdir -p "${storage}/${arch}/debian/${testing}"
ln -s "${XDG_CACHE_HOME}/vectis/${arch}/debian/jessie/autopkgtest.qcow2" "${storage}/${arch}/debian/jessie/"
ln -s "${XDG_CACHE_HOME}/vectis/${arch}/debian/${testing}/autopkgtest.qcow2" "${storage}/${arch}/debian/${testing}/"

echo "1..1"

$VECTIS --vendor=debian --storage="${storage}" sbuild-tarball \
    --mirror="${VECTIS_TEST_DEBIAN_MIRROR}" \
    --suite="${testing}" >&2
$VECTIS --vendor=debian --storage="${storage}" sbuild \
    --mirror="${VECTIS_TEST_DEBIAN_MIRROR}" \
    --suite="${testing}" init-system-helpers >&2
rm -fr "${storage}"

echo "ok 1"
