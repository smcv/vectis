# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging
import os
import subprocess

logger = logging.getLogger(__name__)

def run_autopkgtest(args, testable, binaries=None):
    all_ok = True

    for test in args.autopkgtest:
        if test == 'qemu':
            image = args.autopkgtest_qemu_image

            if not image or not os.path.exists(image):
                continue

            # Run this in the host system, to avoid nested virtualization.
            argv = [
                'autopkgtest',
                '--apt-upgrade',
                '--no-built-binaries',
                # TODO: --output-dir
                # TODO: --setup-commands
                ]

            if binaries is not None:
                for b in binaries:
                    argv.append(b)

            argv.append(testable)

            argv.append('--')
            argv.append('qemu')
            argv.append(args.autopkgtest_qemu_image)

            status = subprocess.call(argv)
        else:
            logger.warning('Unknown autopkgtest setup: {}'.format(test))
            continue

        if status == 0:
            logger.info('{} autopkgtests passed'.format(test))
        elif status == 2:
            logger.info('{} autopkgtests passed or skipped'.format(test))
        elif status == 8:
            logger.info('No autopkgtests found in this package')
        elif status == 12:
            logger.warning('Failed to install test dependencies')
            all_ok = False
        elif status == 16:
            logger.warning(
                'Failed to set up testbed for {} autopkgtest'.format(test))
            all_ok = False
        else:
            logger.error('{} autopkgtests failed'.format(test))
            all_ok = False

    return all_ok
