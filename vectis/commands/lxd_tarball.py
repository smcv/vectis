# Copyright © 2016-2018 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging
import os

from vectis.lxc import (
    set_up_lxd_net,
)
from vectis.worker import (
    VirtWorker,
)

logger = logging.getLogger(__name__)


def run(args):
    if args.suite is None:
        args.suite = args.default_suite

    architecture = args.architecture
    mirrors = args.get_mirrors()
    storage = args.storage
    suite = args.suite
    uri = args._uri
    vendor = args.vendor
    worker_argv = args.lxd_worker
    worker_suite = args.lxd_worker_suite
    lxc_24bit_subnet = args.lxc_24bit_subnet

    if uri is None:
        uri = mirrors.lookup_suite(suite)

    os.makedirs(storage, exist_ok=True)

    tarball = '{arch}/{vendor}/{suite}/lxd-autopkgtest.tar.gz'.format(
        arch=architecture,
        vendor=vendor,
        suite=suite,
    )
    logger.info('Creating tarball %s...', tarball)

    with VirtWorker(
            worker_argv,
            mirrors=mirrors,
            storage=storage,
            suite=worker_suite,
    ) as worker:
        logger.info('Installing debootstrap etc.')
        worker.check_call([
            'env',
            'DEBIAN_FRONTEND=noninteractive',
            'apt-get',
            '-y',
            '-t', worker_suite.apt_suite,
            'install',

            'autopkgtest',
            'debootstrap',
            'lxd',
            'lxd-client',
            'python3',
        ])
        worker.check_call([
            'lxd',
            'init',
            '--auto',
            '--debug',
            '--verbose',
        ])
        set_up_lxd_net(worker, lxc_24bit_subnet)

        worker.check_call([
            'env',
            'MIRROR={}'.format(uri),
            'RELEASE={}'.format(suite),
            worker.command_wrapper,
            '--',
            'autopkgtest-build-lxd',
            'images:{}/{}/{}'.format(vendor, suite, architecture),
        ])

        info = worker.check_output([
            'lxc', 'image', 'info',
            'autopkgtest/{}/{}/{}'.format(vendor, suite, architecture),
        ])

        for line in info.splitlines():
            if line.startswith(b'Fingerprint: '):
                fingerprint = line.split(b':', 1)[1].strip().decode('ascii')
                break
        else:
            raise Exception('Cannot find image fingerprint')

        worker.check_call([
            'lxc', 'image', 'export',
            'autopkgtest/{}/{}/{}'.format(vendor, suite, architecture),
            worker.scratch,
        ])

        out = os.path.join(storage, tarball)
        os.makedirs(os.path.dirname(out) or os.curdir, exist_ok=True)
        worker.copy_to_host(
            '{}/{}.tar.gz'.format(worker.scratch, fingerprint),
            out + '.new')
        os.rename(out + '.new', out)

    logger.info('Created tarball %s', tarball)
