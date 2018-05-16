# Copyright © 2016-2018 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging
import os
import textwrap
from tempfile import TemporaryDirectory

from vectis.error import ArgumentError
from vectis.worker import (
    VirtWorker,
)
from vectis.util import (
    AtomicWriter,
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

    tarball = '{arch}/{vendor}/{suite}/pbuilder.tar.gz'.format(
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
        logger.info('Installing debootstrap and pbuilder')
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
            'pbuilder',
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

        pbuilder_args = [
            'create',
            '--aptcache', '',
            '--architecture', architecture,
            '--components', ' '.join(components),
            '--basetgz', '{}/output.tar.gz'.format(worker.scratch),
            '--mirror', uri,
            '--distribution', str(suite),
        ]
        debootstrap_args = []

        if worker.call(['test', '-f', apt_key]) == 0:
            logger.info('Found apt key worker:{}'.format(apt_key))
            pbuilder_args.append('--keyring')
            pbuilder_args.append(apt_key)
            debootstrap_args.append('--keyring={}'.format(apt_key))
        elif os.path.exists(apt_key):
            logger.info('Found apt key host:{}, copying to worker:{}'.format(
                apt_key, '{}/apt-key.gpg'.format(worker.scratch)))
            worker.copy_to_guest(
                apt_key, '{}/apt-key.gpg'.format(worker.scratch))
            pbuilder_args.append('--keyring')
            pbuilder_args.append('{}/apt-key.gpg'.format(worker.scratch))
            debootstrap_args.append('--keyring={}/apt-key.gpg'.format(
                worker.scratch))
        else:
            logger.warning(
                'Apt key host:{} not found; leaving it out and hoping '
                'for the best'.format(apt_key))

        for arg in debootstrap_args:
            pbuilder_args.append('--debootstrapopts')
            pbuilder_args.append(arg)

        worker.check_call([
            'touch', '/root/.pbuilderrc',
        ])
        logger.info('pbuilder %r', pbuilder_args)
        worker.check_call([
            'env', 'DEBIAN_FRONTEND=noninteractive',
            worker.command_wrapper,
            '--',
            'pbuilder',
        ] + pbuilder_args)

        out = os.path.join(storage, tarball)
        os.makedirs(os.path.dirname(out) or os.curdir, exist_ok=True)

        # Smoke-test the new tarball before being prepared to use it.
        if test_package:
            with TemporaryDirectory(prefix='vectis-pbuilder-') as tmp:
                with AtomicWriter(os.path.join(tmp, 'script')) as writer:
                    writer.write(textwrap.dedent('''\
                    #!/bin/sh
                    set -e
                    set -u
                    cd "$2"
                    perl -ne 'print $_; if (s/^deb\s/deb-src /) { print $_ }' \
                            < /etc/apt/sources.list \
                            > /etc/apt/sources.list.new
                    mv /etc/apt/sources.list.new /etc/apt/sources.list
                    apt-get update >&2
                    apt-get --download-only source "$1" >&2
                    mv *.dsc "$1.dsc"
                    '''))
                worker.copy_to_guest(
                    os.path.join(tmp, 'script'),
                    '{}/script'.format(worker.scratch))

            worker.check_call([
                'chmod',
                '0755',
                '{}/script'.format(worker.scratch),
            ])

            try:
                lines = worker.check_output(
                    [
                        'pbuilder',
                        'execute',
                        '--aptcache', '',
                        '--basetgz', '{}/output.tar.gz'.format(worker.scratch),
                        '--bindmounts', '{}'.format(worker.scratch),
                        '--',
                        '{}/script'.format(worker.scratch),
                        test_package,
                        worker.scratch,
                    ],
                    universal_newlines=True).strip().splitlines()
                #assert len(lines) == 1
                logger.info('%r', lines)

                worker.check_call([
                    worker.command_wrapper,
                    '--chdir',
                    worker.scratch,
                    '--',
                    'pbuilder',
                    'build',
                    '--aptcache', '',
                    '--basetgz', '{}/output.tar.gz'.format(worker.scratch),
                    '{}.dsc'.format(test_package),
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

    logger.info('Created tarball %s', tarball)
