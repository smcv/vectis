# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging
import os
import subprocess
import textwrap
from tempfile import TemporaryDirectory

from vectis.util import (
        AtomicWriter,
        )

logger = logging.getLogger(__name__)

def run_autopkgtest(args, testable, binaries=None):
    with TemporaryDirectory(prefix='vectis-autopkgtest-') as tmp:
        _run_autopkgtest(tmp, args, testable, binaries)

def _run_autopkgtest(tmp, args, testable, binaries=None):
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

            # FIXME: duplicate of code in Worker
            with AtomicWriter(os.path.join(tmp, 'sources.list')) as writer:
                for ancestor in args.suite.hierarchy:
                    if args.components:
                        filtered_components = (set(args.components) &
                                set(ancestor.all_components))
                    else:
                        filtered_components = ancestor.components

                    writer.write(textwrap.dedent('''
                    deb {mirror} {suite} {components}
                    deb-src {mirror} {suite} {components}
                    ''').format(
                        components=' '.join(filtered_components),
                        mirror=ancestor.mirror,
                        suite=ancestor.apt_suite,
                    ))

                    if ancestor.apt_key is not None:
                        argv.append('--copy={}:{}'.format(
                            ancestor.apt_key,
                            '/etc/apt/trusted.gpg.d/' +
                            os.path.basename(ancestor.apt_key)))

            argv.append('--copy={}:{}'.format(
                        os.path.join(tmp, 'sources.list'),
                        '/etc/apt/sources.list'))

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
