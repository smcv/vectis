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

if ! stable="$(debian-distro-info --stable)"; then
    echo "1..0 # SKIP Could not determine current Debian stable suite"
    exit 0
fi

if ! testing="$(debian-distro-info --testing)"; then
    echo "1..0 # SKIP Could not determine current Debian testing suite"
    exit 0
fi

# Currently used for the sbuild worker
if ! [ -f "${XDG_CACHE_HOME}/vectis/${arch}/debian/${stable}/autopkgtest.qcow2" ]; then
    echo "1..0 # SKIP ${arch}/debian/${stable}/autopkgtest.qcow2 not found"
    exit 0
fi

if ! [ -f "${XDG_CACHE_HOME}/vectis/${arch}/debian/${testing}/autopkgtest.qcow2" ]; then
    echo "1..0 # SKIP ${storage}/vectis/${arch}/debian/${testing}/autopkgtest.qcow2 not found"
    exit 0
fi

if ! [ -f "${XDG_CACHE_HOME}/vectis/${arch}/debian/${testing}/sbuild.tar.gz" ]; then
    echo "1..0 # SKIP ${storage}/vectis/${arch}/debian/${testing}/sbuild.tar.gz not found"
    exit 0
fi

if [ -z "${VECTIS_TEST_DEBIAN_MIRROR:-}" ]; then
    echo "1..0 # SKIP This test requires VECTIS_TEST_DEBIAN_MIRROR=http://192.168.122.1:3142/debian or similar"
    exit 0
fi

storage="$(mktemp --tmpdir -d vectis-test-XXXXXXXXXX)"

mkdir -p "${storage}/${arch}/debian/${stable}"
mkdir -p "${storage}/${arch}/debian/${testing}"
ln -s "${XDG_CACHE_HOME}/vectis/${arch}/debian/${stable}/autopkgtest.qcow2" "${storage}/${arch}/debian/${stable}/"
ln -s "${XDG_CACHE_HOME}/vectis/${arch}/debian/${testing}/autopkgtest.qcow2" "${storage}/${arch}/debian/${testing}/"
ln -s "${XDG_CACHE_HOME}/vectis/${arch}/debian/${testing}/sbuild.tar.gz" "${storage}/${arch}/debian/${testing}/"
# doesn't have to exist
ln -s "${XDG_CACHE_HOME}/vectis/${arch}/debian/${testing}/minbase.tar.gz" "${storage}/${arch}/debian/${testing}/"

echo "1..1"

$VECTIS --vendor=debian --storage="${storage}" \
    new \
    --mirror="debian=${VECTIS_TEST_DEBIAN_MIRROR}" \
    --suite="${testing}" >&2
test ! -L "${storage}/${arch}/debian/${testing}/autopkgtest.qcow2"
$VECTIS --vendor=debian --storage="${storage}" sbuild \
    --mirror="debian=${VECTIS_TEST_DEBIAN_MIRROR}" \
    --suite="${testing}" \
    grep >&2
rm -fr "${storage}"

echo "ok 1"
