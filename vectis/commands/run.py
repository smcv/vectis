# Copyright © 2016-2017 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging

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

    argv = args._argv
    mirrors = args.get_mirrors()
    qemu_image = args.qemu_image
    shell_command = args._shell_command
    suite = args.suite

    if shell_command is None and not argv:
        raise ArgumentError(
            'Usage: vectis run -- PROGRAM [$1 [$2...]] or vectis run '
            '-c "shell one-liner" [$0 [$1 [$2...]]]')

    for suite in (suite,):
        for ancestor in suite.hierarchy:
            mirror = mirrors.lookup_suite(ancestor)
            if mirror is None:
                raise ArgumentError(
                    'No mirror configured for {}'.format(ancestor))

    with VirtWorker(
            ['qemu', qemu_image],
            mirrors=mirrors,
            suite=suite) as worker:
        if shell_command is not None:
            worker.check_call(['sh', '-c', shell_command] + argv)
        else:
            worker.check_call(argv)
