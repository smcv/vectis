#!/bin/sh
# vim:set ft=sh:

set -e
set -u
set -x

storage="$(mktemp -d)"
arch="$(dpkg --print-architecture)"

ln -s "${XDG_CACHE_HOME:-"${HOME}/.cache"}"/vectis/vectis-debian-sid-${arch}.qcow2 "${storage}"
ln -s "${XDG_CACHE_HOME:-"${HOME}/.cache"}"/vectis/sbuild-debian-sid-${arch}.tar.gz "${storage}"

if ! [ -f "${storage}/vectis-debian-sid-${arch}.qcow2" ]; then
	echo "1..0 # SKIP vectis-debian-sid-${arch}.qcow2 not found"
	exit 0
fi

if ! [ -f "${storage}/sbuild-debian-sid-${arch}.tar.gz" ]; then
	echo "1..0 # SKIP sbuild-debian-sid-${arch}.tar.gz not found"
	exit 0
fi

echo "1..1"

PYTHONPATH=$(pwd) ./run --platform=debian --storage="${storage}" \
	new \
	--builder='qemu ${storage}/vectis-debian-sid-${architecture}.qcow2' \
	--suite=sid
test ! -L "${storage}/vectis-debian-sid-${arch}.qcow2"
PYTHONPATH=$(pwd) ./run --platform=debian --storage="${storage}" sbuild \
	--builder='qemu ${storage}/vectis-debian-sid-${architecture}.qcow2' \
	--suite=sid \
	hello
rm -fr "${storage}"

echo "ok 1"
