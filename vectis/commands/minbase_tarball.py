# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging
import os

from vectis.error import ArgumentError
from vectis.worker import (
        VirtWorker,
        )

logger = logging.getLogger(__name__)

def run(args):
    if args.suite is None:
        if args.default_suite is not None:
            args.suite = args.default_suite
        else:
            raise ArgumentError('--suite must be specified')

    architecture = args.architecture
    mirror = args.mirror
    storage = args.storage
    suite = args.suite
    vendor = args.vendor
    worker_argv = args.worker
    worker_suite = args.worker_suite

    apt_key = args.apt_key
    apt_key_package = args.apt_key_package

    os.makedirs(storage, exist_ok=True)

    if mirror is None:
        raise ArgumentError('mirror or apt_cacher_ng must be configured')

    for suite in (worker_suite, suite):
        for ancestor in suite.hierarchy:
            if ancestor.mirror is None:
                raise ArgumentError('mirror or apt_cacher_ng must be '
                        'configured for {}'.format(ancestor))

    minbase_tarball = '{arch}/{vendor}/{suite}/minbase.tar.gz'.format(
            arch=architecture,
            vendor=vendor,
            suite=suite,
            )
    logger.info('Creating tarball %s...', minbase_tarball)

    with VirtWorker(worker_argv.split(),
            suite=worker_suite,
            ) as worker:
        logger.info('Installing debootstrap')
        worker.check_call([
            'env',
            'DEBIAN_FRONTEND=noninteractive',
            'apt-get',
            '-y',
            '-t', worker_suite.apt_suite,
            '--no-install-recommends',
            'install',

            'debootstrap',
            'python3',
            ])

        if apt_key_package is not None:
            worker.call([
                'env',
                'DEBIAN_FRONTEND=noninteractive',
                'apt-get',
                '-y',
                '-t', worker_suite.apt_suite,
                '--no-install-recommends',
                'install',

                apt_key_package,
                ])

        debootstrap_args = []

        if worker.call(['test', '-f', apt_key]) == 0:
            logger.info('Found apt key worker:{}'.format(apt_key))
            debootstrap_args.append('--keyring={}'.format(apt_key))
        elif os.path.exists(apt_key):
            logger.info('Found apt key host:{}, copying to worker:{}'.format(
                apt_key, '{}/apt-key.gpg'.format(worker.scratch)))
            worker.copy_to_guest(apt_key,
                    '{}/apt-key.gpg'.format(worker.scratch))
            debootstrap_args.append('--keyring={}/apt-key.gpg'.format(
                worker.scratch))
        else:
            logger.warning('Apt key host:{} not found; leaving it out and '
                    'hoping for the best'.format(apt_key))

        debootstrap_args.append('--components={}'.format(
            ','.join(args.components)))

        worker.check_call([
                'env', 'DEBIAN_FRONTEND=noninteractive',
                worker.command_wrapper,
                '--',
                'debootstrap',
                '--arch={}'.format(architecture),
                '--components={}'.format(','.join(args.components)),
                '--variant=minbase',
                '--verbose',
            ] + debootstrap_args + [
                str(suite), '{}/chroot'.format(worker.scratch),
                mirror,
                '/usr/share/debootstrap/scripts/{}'.format(args.debootstrap_script),
            ])
        worker.check_call(['chroot', '{}/chroot'.format(worker.scratch),
            'apt-get', 'clean'])
        worker.check_call(['tar', '-C', '{}/chroot'.format(worker.scratch),
            '-f', '{}/output.tar.gz'.format(worker.scratch),
            '-z', '-c', '.'])

        out = os.path.join(storage, minbase_tarball)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        worker.copy_to_host('{}/output.tar.gz'.format(worker.scratch), out + '.new')
        # FIXME: smoke-test it?
        os.rename(out + '.new', out)

    logger.info('Created tarball %s', minbase_tarball)
