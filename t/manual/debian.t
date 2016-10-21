#!/bin/sh

set -e
set -x

storage="$(mktemp -d)"

#PYTHONPATH=$(pwd) ./run --storage="${storage}" bootstrap --size=23G
PYTHONPATH=$(pwd) ./run --storage="${storage}" new --size=23G --suite=jessie --bootstrap-machine=/srv/virt/autopkgtest-debian-sid-amd64.qcow2c
PYTHONPATH=$(pwd) ./run --storage="${storage}" new --size=23G --suite=sid --bootstrap-machine=/srv/virt/autopkgtest-debian-sid-amd64.qcow2c
