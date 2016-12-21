#!/bin/sh
# vim:set ft=sh:

set -e
set -u
set -x

case $(id -u) in
	(0)
		;;
	(*)
		echo "1..0 # SKIP Re-run as root"
		exit 0
		;;
esac

echo "1..1"

storage="$(mktemp -d)"

( cd "$storage"; apt-get --download-only source hello )

PYTHONPATH=$(pwd) ./run --storage="${storage}" bootstrap --size=23G
PYTHONPATH=$(pwd) ./run --storage="${storage}" sbuild-tarball --suite=sid
PYTHONPATH=$(pwd) ./run --storage="${storage}" sbuild --suite=sid "${storage}/"hello*.dsc
rm -fr "${storage}"

echo "ok 1"
