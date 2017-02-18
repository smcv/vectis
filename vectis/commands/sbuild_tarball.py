# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging
import os

from debian.debian_support import (
        Version,
        )

from vectis.error import ArgumentError
from vectis.worker import Worker

logger = logging.getLogger(__name__)

def run(args):
    os.makedirs(args.storage, exist_ok=True)

    if args.suite is None:
        if args.default_suite is not None:
            args.suite = args.default_suite
        else:
            raise ArgumentError('--suite must be specified')

    for suite in (args.worker_suite, args.suite):
        for ancestor in suite.hierarchy:
            if ancestor.mirror is None:
                raise ArgumentError('mirror or apt_cacher_ng must be '
                        'configured for {}'.format(ancestor))

    sbuild_tarball = '{arch}/{vendor}/{suite}/sbuild.tar.gz'.format(
            arch=args.architecture,
            vendor=args.vendor,
            suite=args.suite,
            )
    logger.info('Creating tarball %s...', sbuild_tarball)

    with Worker(args.worker.split()) as worker:
        logger.info('Installing debootstrap and sbuild')
        worker.set_up_apt(args.worker_suite)
        worker.check_call([
            'env',
            'DEBIAN_FRONTEND=noninteractive',
            'apt-get',
            '-y',
            '--no-install-recommends',
            'install',

            'debootstrap',
            'python3',
            'sbuild',
            'schroot',
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
                'sbuild-createchroot',
                '--arch={}'.format(args.architecture),
                '--include=fakeroot,sudo,vim',
                '--components={}'.format(','.join(args.components)),
                '--make-sbuild-tarball={}/output.tar.gz'.format(worker.scratch),
            ] + debootstrap_args + [
                str(args.suite), '{}/chroot'.format(worker.scratch),
                args.mirror,
                '/usr/share/debootstrap/scripts/{}'.format(args.debootstrap_script),
            ])

        out = os.path.join(args.storage, sbuild_tarball)
        os.makedirs(os.path.dirname(out), exist_ok=True)

        # Smoke-test the new tarball before being prepared to use it.
        if args._test_package:
            try:
                lines = worker.check_output([
                            'schroot',
                            '-c', '{}-{}-sbuild'.format(args.suite,
                                args.architecture),
                            '--',
                            'sh', '-c',
                            'apt-get update >&2 && '
                            '( apt-cache showsrc --only-source "$1" || '
                            '  apt-cache showsrc "$1" ) | '
                            'sed -ne "s/^Version: *//p"',
                            'sh', # argv[0]
                            args._test_package],
                        universal_newlines=True).strip().splitlines()
                version = sorted(map(Version, lines))[-1]
                buildable = '{}_{}'.format(args._test_package, version)

                worker.check_call([
                    worker.command_wrapper,
                    '--chdir',
                    worker.scratch,
                    '--',
                    'runuser',
                    '-u', 'sbuild',
                    '--',
                    'sbuild',
                    '-c', '{}-{}-sbuild'.format(args.suite, args.architecture),
                    '-d', 'whatever',
                    '--no-run-lintian',
                    buildable,
                    ])
            except:
                if args._keep:
                    worker.copy_to_host(
                            '{}/output.tar.gz'.format(worker.scratch),
                            out + '.new')

                raise

        worker.copy_to_host('{}/output.tar.gz'.format(worker.scratch), out + '.new')
        os.rename(out + '.new', out)

    logger.info('Created tarball %s', sbuild_tarball)
