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
    os.makedirs(args.storage, exist_ok=True)

    if args.suite is None:
        if args.default_suite is not None:
            args.suite = args.default_suite
        else:
            raise ArgumentError('--suite must be specified')

    if args.mirror is None:
        raise ArgumentError('mirror or apt_cacher_ng must be configured')

    for suite in (args.worker_suite, args.suite):
        for ancestor in suite.hierarchy:
            if ancestor.mirror is None:
                raise ArgumentError('mirror or apt_cacher_ng must be '
                        'configured for {}'.format(ancestor))

    minbase_tarball = '{arch}/{vendor}/{suite}/minbase.tar.gz'.format(
            arch=args.architecture,
            vendor=args.vendor,
            suite=args.suite,
            )
    logger.info('Creating tarball %s...', minbase_tarball)

    with VirtWorker(args.worker.split(),
            suite=args.worker_suite,
            ) as worker:
        logger.info('Installing debootstrap')
        worker.check_call([
            'env',
            'DEBIAN_FRONTEND=noninteractive',
            'apt-get',
            '-y',
            '--no-install-recommends',
            'install',

            'debootstrap',
            'python3',
            ])

        keyring = args.apt_key_package

        if keyring is not None:
            worker.call([
                'env',
                'DEBIAN_FRONTEND=noninteractive',
                'apt-get',
                '-y',
                '--no-install-recommends',
                'install',

                keyring,
                ])

        debootstrap_args = []

        if worker.call(['test', '-f', args.apt_key]) == 0:
            logger.info('Found apt key worker:{}'.format(args.apt_key))
            debootstrap_args.append('--keyring={}'.format(args.apt_key))
        elif os.path.exists(args.apt_key):
            logger.info('Found apt key host:{}, copying to worker:{}'.format(
                args.apt_key, '{}/apt-key.gpg'.format(worker.scratch)))
            worker.copy_to_guest(args.apt_key,
                    '{}/apt-key.gpg'.format(worker.scratch))
            debootstrap_args.append('--keyring={}/apt-key.gpg'.format(
                worker.scratch))
        else:
            logger.warning('Apt key host:{} not found; leaving it out and '
                    'hoping for the best'.format(args.apt_key))

        debootstrap_args.append('--components={}'.format(
            ','.join(args.components)))

        worker.check_call([
                'env', 'DEBIAN_FRONTEND=noninteractive',
                worker.command_wrapper,
                '--',
                'debootstrap',
                '--arch={}'.format(args.architecture),
                '--components={}'.format(','.join(args.components)),
                '--variant=minbase',
                '--verbose',
            ] + debootstrap_args + [
                str(args.suite), '{}/chroot'.format(worker.scratch),
                args.mirror,
                '/usr/share/debootstrap/scripts/{}'.format(args.debootstrap_script),
            ])
        worker.check_call(['chroot', '{}/chroot'.format(worker.scratch),
            'apt-get', 'clean'])
        worker.check_call(['tar', '-C', '{}/chroot'.format(worker.scratch),
            '-f', '{}/output.tar.gz'.format(worker.scratch),
            '-z', '-c', '.'])

        out = os.path.join(args.storage, minbase_tarball)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        worker.copy_to_host('{}/output.tar.gz'.format(worker.scratch), out + '.new')
        # FIXME: smoke-test it?
        os.rename(out + '.new', out)

    logger.info('Created tarball %s', minbase_tarball)
