# Copyright © 2016-2017 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging
import os

from vectis.lxc import (
    set_up_lxc_net,
)
from vectis.worker import (
    VirtWorker,
)

logger = logging.getLogger(__name__)


def run(args):
    if args.suite is None:
        args.suite = args.default_suite

    architecture = args.architecture
    mirror = args.mirror
    storage = args.storage
    suite = args.suite
    vendor = args.vendor
    worker_argv = args.worker
    worker_suite = args.worker_suite

    apt_key_package = args.apt_key_package
    lxc_24bit_subnet = args.lxc_24bit_subnet

    os.makedirs(storage, exist_ok=True)

    rootfs_tarball = '{arch}/{vendor}/{suite}/lxc-rootfs.tar.gz'.format(
        arch=architecture,
        vendor=vendor,
        suite=suite,
    )
    meta_tarball = '{arch}/{vendor}/{suite}/lxc-meta.tar.gz'.format(
        arch=architecture,
        vendor=vendor,
        suite=suite,
    )
    logger.info('Creating tarballs %s, %s...', rootfs_tarball, meta_tarball)

    with VirtWorker(
            worker_argv, suite=worker_suite,
    ) as worker:
        logger.info('Installing debootstrap etc.')
        worker.check_call([
            'env',
            'DEBIAN_FRONTEND=noninteractive',
            'apt-get',
            '-y',
            '-t', worker_suite.apt_suite,
            'install',

            'debootstrap',
            'lxc',
            'python3',
        ])
        set_up_lxc_net(worker, lxc_24bit_subnet)

        # FIXME: The lxc templates only allow installing the apt keyring
        # to use, and do not allow passing --keyring to debootstrap
        keyring = apt_key_package

        if keyring is not None:
            worker.call([
                'env',
                'DEBIAN_FRONTEND=noninteractive',
                'apt-get',
                '-y',
                '-t', worker_suite.apt_suite,
                '--no-install-recommends',
                'install',

                keyring,
            ])

        # FIXME: This is silly, but it's a limitation of the lxc templates.
        # We have to provide exactly two apt URLs.
        security_suite = vendor.get_suite(str(suite) + '-security')

        if mirror is None:
            mirror = suite.mirror

        argv = [
            'env', 'DEBIAN_FRONTEND=noninteractive',
            worker.command_wrapper,
            '--',
            'lxc-create',
            '--template={}'.format(vendor),
            '--name={}-{}-{}'.format(vendor, suite, architecture),
            '--',
            '--release={}'.format(suite),
            '--arch={}'.format(architecture),
            '--mirror={}'.format(mirror),
            '--security-mirror={}'.format(security_suite.mirror),
        ]

        if str(vendor) == 'ubuntu':
            argv.append('--variant=minbase')

        worker.check_call(argv)

        worker.check_call([
            'tar', '-C',
            '/var/lib/lxc/{}-{}-{}/rootfs'.format(vendor, suite, architecture),
            '-f', '{}/rootfs.tar.gz'.format(worker.scratch),
            '--exclude=./var/cache/apt/archives/*.deb',
            '-z', '-c', '.',
        ])
        worker.check_call([
            'tar', '-C',
            '/var/lib/lxc/{}-{}-{}'.format(vendor, suite, architecture),
            '-f', '{}/meta.tar.gz'.format(worker.scratch),
            '-z', '-c', 'config',
        ])

        out = os.path.join(storage, rootfs_tarball)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        worker.copy_to_host(
            '{}/rootfs.tar.gz'.format(worker.scratch), out + '.new')
        # FIXME: smoke-test it?
        os.rename(out + '.new', out)

        out = os.path.join(storage, meta_tarball)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        worker.copy_to_host(
            '{}/meta.tar.gz'.format(worker.scratch), out + '.new')
        # FIXME: smoke-test it?
        os.rename(out + '.new', out)

    logger.info('Created tarballs %s, %s', rootfs_tarball, meta_tarball)
