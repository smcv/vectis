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

    minbase_tarball = 'minbase-{vendor}-{suite}-{arch}.tar.gz'.format(
            arch=args.architecture,
            vendor=args.vendor,
            suite=args.suite,
            )
    logger.info('Creating tarball %s...', minbase_tarball)

    with Worker(args.worker) as worker:
        logger.info('Installing debootstrap')
        worker.set_up_apt(args.worker_suite)
        worker.check_call([
            'apt-get',
            '-y',
            '--no-install-recommends',
            'install',

            'debootstrap',
            'python3',
            ])
        worker.check_call([
                'env', 'DEBIAN_FRONTEND=noninteractive',
                worker.command_wrapper,
                '--',
                'debootstrap',
                '--arch={}'.format(args.architecture),
                '--components={}'.format(','.join(args.components)),
                '--variant=minbase',
                '--verbose',
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
        worker.copy_to_host('{}/output.tar.gz'.format(worker.scratch), out + '.new')
        # FIXME: smoke-test it?
        os.rename(out + '.new', out)

    logger.info('Created tarball %s', minbase_tarball)
