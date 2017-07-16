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

if [ -z "${VECTIS_TEST_UBUNTU_MIRROR:-}" ]; then
    echo "1..0 # SKIP This test requires VECTIS_TEST_UBUNTU_MIRROR=http://192.168.122.1:3142/ubuntu or similar"
    exit 0
fi

if ! lts="$(ubuntu-distro-info --lts)"; then
    echo "1..0 # SKIP Could not determine current Ubuntu LTS suite"
    exit 0
fi

: "${XDG_CACHE_HOME:="${HOME}/.cache"}"
arch="$(dpkg --print-architecture)"

if ! [ -f "${XDG_CACHE_HOME}/vectis/${arch}/ubuntu/${lts}/autopkgtest.qcow2" ]; then
    echo "1..0 # SKIP XDG_CACHE_HOME/vectis/${arch}/ubuntu/${lts}/autopkgtest.qcow2 not found"
    exit 0
fi

if ! [ -f "${XDG_CACHE_HOME}/vectis/${arch}/ubuntu/${lts}/sbuild.tar.gz" ]; then
    echo "1..0 # SKIP XDG_CACHE_HOME/vectis/${arch}/ubuntu/${lts}/sbuild.tar.gz not found"
    exit 0
fi

storage="$(mktemp --tmpdir -d vectis-test-XXXXXXXXXX)"

mkdir -p "${storage}/${arch}/ubuntu/${lts}"
ln -s "${XDG_CACHE_HOME}/vectis/${arch}/ubuntu/${lts}/autopkgtest.qcow2" "${storage}/${arch}/ubuntu/${lts}/"
ln -s "${XDG_CACHE_HOME}/vectis/${arch}/ubuntu/${lts}/sbuild.tar.gz" "${storage}/${arch}/ubuntu/${lts}/"

echo "1..1"

$VECTIS --vendor=ubuntu --storage="${storage}" \
    new \
    --mirror="ubuntu=${VECTIS_TEST_UBUNTU_MIRROR}" \
    --suite="${lts}" >&2

$VECTIS --vendor=ubuntu --storage="${storage}" sbuild \
    --mirror="ubuntu=${VECTIS_TEST_UBUNTU_MIRROR}" \
    --worker-suite="${lts}" \
    --suite="${lts}" \
    grep >&2

rm -fr "${storage}"

echo "ok 1"
