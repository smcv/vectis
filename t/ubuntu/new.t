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

if [ -z "${VECTIS_TEST_UBUNTU_MIRROR:-}" ]; then
    echo "1..0 # SKIP This test requires VECTIS_TEST_UBUNTU_MIRROR=http://192.168.122.1:3142/ubuntu or similar"
    exit 0
fi

if ! lts="$(ubuntu-distro-info --lts)"; then
    echo "1..0 # SKIP Could not determine current Ubuntu LTS suite"
    exit 0
fi

ln -s "${XDG_CACHE_HOME:-"${HOME}/.cache"}/vectis/vectis-ubuntu-${lts}-${arch}.qcow2" "${storage}"
ln -s "${XDG_CACHE_HOME:-"${HOME}/.cache"}/vectis/sbuild-ubuntu-${lts}-${arch}.tar.gz" "${storage}"

if ! [ -f "${storage}/vectis-ubuntu-${lts}-${arch}.qcow2" ]; then
    echo "1..0 # SKIP XDG_CACHE_HOME/vectis/vectis-ubuntu-${lts}-${arch}.qcow2 not found"
    exit 0
fi

if ! [ -f "${storage}/sbuild-ubuntu-${lts}-${arch}.tar.gz" ]; then
    echo "1..0 # SKIP XDG_CACHE_HOME/vectis/sbuild-ubuntu-${lts}-${arch}.tar.gz not found"
    exit 0
fi

echo "1..1"

$VECTIS --vendor=ubuntu --storage="${storage}" \
    new \
    --mirror="${VECTIS_TEST_UBUNTU_MIRROR}" \
    --suite="${lts}"

$VECTIS --vendor=ubuntu --storage="${storage}" sbuild \
    --mirror="${VECTIS_TEST_UBUNTU_MIRROR}" \
    --worker-suite="${lts}" \
    --suite="${lts}" \
    hello

rm -fr "${storage}"

echo "ok 1"
