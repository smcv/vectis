# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging
import os

from vectis.worker import Worker

logger = logging.getLogger(__name__)

def run(args):
    os.makedirs(args.storage, exist_ok=True)

    if args.suite is None:
        args.suite = args.default_suite

    sbuild_tarball = 'sbuild-{vendor}-{suite}-{arch}.tar.gz'.format(
            arch=args.architecture,
            vendor=args.vendor,
            suite=args.suite,
            )
    logger.info('Creating tarball %s...', sbuild_tarball)

    with Worker(args.worker.split()) as worker:
        logger.info('Installing debootstrap and sbuild')
        worker.set_up_apt(args.worker_suite)
        worker.check_call([
            'apt-get',
            '-y',
            '--no-install-recommends',
            'install',

            'debootstrap',
            'python3',
            'sbuild',
            'schroot',
            ])
        worker.check_call([
                'env', 'DEBIAN_FRONTEND=noninteractive',
                worker.command_wrapper,
                '--',
                'sbuild-createchroot',
                '--arch={}'.format(args.architecture),
                '--include=fakeroot,sudo,vim',
                '--components={}'.format(','.join(args.components)),
                '--make-sbuild-tarball={}/output.tar.gz'.format(worker.scratch),
                str(args.suite), '{}/chroot'.format(worker.scratch),
                args.mirror,
                '/usr/share/debootstrap/scripts/{}'.format(args.debootstrap_script),
            ])

        out = os.path.join(args.storage, sbuild_tarball)

        # Smoke-test the new tarball before being prepared to use it.
        if args._test_package:
            try:
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
                    args._test_package,
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
