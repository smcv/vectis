# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging
import os

from vectis.virt import Machine

logger = logging.getLogger(__name__)

def run(args):
    os.makedirs(args.storage, exist_ok=True)

    if args.suite is None:
        args.suite = args.default_suite

    sbuild_tarball = 'sbuild-{platform}-{suite}-{arch}.tar.gz'.format(
            arch=args.architecture,
            platform=args.platform,
            suite=args.suite,
            )
    logger.info('Creating tarball %s...', sbuild_tarball)

    with Machine(args.builder) as machine:
        logger.info('Installing debootstrap and sbuild')
        machine.check_call([
            'env', 'DEBIAN_FRONTEND=noninteractive',
            'apt-get', '-y', 'update',
            ])
        machine.check_call([
            'apt-get',
            '-y',
            '--no-install-recommends',
            'install',

            'debootstrap',
            'sbuild',
            'schroot',
            ])
        machine.check_call([
                'env', 'DEBIAN_FRONTEND=noninteractive',
                machine.command_wrapper,
                '--',
                'sbuild-createchroot',
                '--arch={}'.format(args.architecture),
                '--include=fakeroot,sudo,vim',
                '--components={}'.format(','.join(args.components)),
                '--make-sbuild-tarball={}/output.tar.gz'.format(machine.scratch),
                '--chroot-prefix=vectis',
                '--chroot-suffix=',
                args.suite, '{}/chroot'.format(machine.scratch),
                args.mirror,
                '/usr/share/debootstrap/scripts/{}'.format(args.debootstrap_script),
            ])

        # Smoke-test the new tarball before being prepared to use it.
        if args._test_package:
            machine.check_call([
                machine.command_wrapper,
                '--chdir',
                machine.scratch,
                '--',
                'runuser',
                '-u', 'sbuild',
                '--',
                'sbuild',
                '-c', 'vectis-{}'.format(args.architecture),
                '-d', 'whatever',
                '--no-run-lintian',
                args._test_package,
                ])

        out = os.path.join(args.storage, sbuild_tarball)
        machine.copy_to_host('{}/output.tar.gz'.format(machine.scratch), out + '.new')
        os.rename(out + '.new', out)

    logger.info('Created tarball %s', sbuild_tarball)
