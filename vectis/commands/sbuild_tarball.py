# Copyright © 2016-2017 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging
import os

from debian.debian_support import (
    Version,
)

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

    # From argv or configuration
    architecture = args.architecture
    components = args.components
    debootstrap_script = args.debootstrap_script
    keep = args._keep
    mirrors = args.get_mirrors()
    storage = args.storage
    suite = args.suite
    test_package = args._test_package
    uri = args._uri
    vendor = args.vendor
    worker_argv = args.worker
    worker_suite = args.worker_suite

    # From configuration
    apt_key = args.apt_key
    apt_key_package = args.apt_key_package

    os.makedirs(storage, exist_ok=True)

    for suite in (worker_suite, suite):
        for ancestor in suite.hierarchy:
            mirror = mirrors.lookup_suite(ancestor)
            if mirror is None:
                raise ArgumentError(
                    'No mirror configured for {}'.format(ancestor))

    if uri is None:
        uri = mirrors.lookup_suite(suite)

    sbuild_tarball = '{arch}/{vendor}/{suite}/sbuild.tar.gz'.format(
        arch=architecture,
        vendor=vendor,
        suite=suite,
    )
    logger.info('Creating tarball %s...', sbuild_tarball)

    with VirtWorker(
            worker_argv,
            mirrors=mirrors,
            storage=storage,
            suite=worker_suite,
    ) as worker:
        logger.info('Installing debootstrap and sbuild')
        worker.check_call([
            'env',
            'DEBIAN_FRONTEND=noninteractive',
            'apt-get',
            '-y',
            '--no-install-recommends',
            '-t', worker_suite.apt_suite,
            'install',

            'debootstrap',
            'python3',
            'sbuild',
            'schroot',
        ])

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

        debootstrap_args = []

        if worker.call(['test', '-f', apt_key]) == 0:
            logger.info('Found apt key worker:{}'.format(apt_key))
            debootstrap_args.append('--keyring={}'.format(apt_key))
        elif os.path.exists(apt_key):
            logger.info('Found apt key host:{}, copying to worker:{}'.format(
                apt_key, '{}/apt-key.gpg'.format(worker.scratch)))
            worker.copy_to_guest(
                apt_key, '{}/apt-key.gpg'.format(worker.scratch))
            debootstrap_args.append('--keyring={}/apt-key.gpg'.format(
                worker.scratch))
        else:
            logger.warning(
                'Apt key host:{} not found; leaving it out and hoping '
                'for the best'.format(apt_key))

        debootstrap_args.append(
            '--components={}'.format(','.join(components)))

        worker.check_call([
            'env', 'DEBIAN_FRONTEND=noninteractive',
            worker.command_wrapper,
            '--',
            'sbuild-createchroot',
            '--arch={}'.format(architecture),
            '--include=fakeroot,sudo,vim',
            '--components={}'.format(','.join(components)),
            '--make-sbuild-tarball={}/output.tar.gz'.format(worker.scratch),
        ] + debootstrap_args + [
            str(suite), '{}/chroot'.format(worker.scratch), uri,
            '/usr/share/debootstrap/scripts/{}'.format(debootstrap_script),
        ])

        out = os.path.join(storage, sbuild_tarball)
        os.makedirs(os.path.dirname(out), exist_ok=True)

        # Smoke-test the new tarball before being prepared to use it.
        if test_package:
            try:
                lines = worker.check_output(
                    [
                        'schroot',
                        '-c', '{}-{}-sbuild'.format(suite, architecture),
                        '--',
                        'sh', '-c',
                        'apt-get update >&2 && '
                        '( apt-cache showsrc --only-source "$1" || '
                        '  apt-cache showsrc "$1" ) | '
                        'sed -ne "s/^Version: *//p"',
                        'sh',  # argv[0]
                        test_package,
                    ],
                    universal_newlines=True).strip().splitlines()
                version = sorted(map(Version, lines))[-1]
                buildable = '{}_{}'.format(test_package, version)

                worker.check_call([
                    worker.command_wrapper,
                    '--chdir',
                    worker.scratch,
                    '--',
                    'runuser',
                    '-u', 'sbuild',
                    '--',
                    'sbuild',
                    '--arch', architecture,
                    '-c', '{}-{}-sbuild'.format(suite, architecture),
                    '-d', 'whatever',
                    '--no-run-lintian',
                    buildable,
                ])
            except:
                if keep:
                    worker.copy_to_host(
                        '{}/output.tar.gz'.format(worker.scratch),
                        out + '.new')

                raise

        worker.copy_to_host(
            '{}/output.tar.gz'.format(worker.scratch), out + '.new')
        os.rename(out + '.new', out)

    logger.info('Created tarball %s', sbuild_tarball)
