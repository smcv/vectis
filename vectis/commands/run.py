# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging

from vectis.error import ArgumentError
from vectis.worker import Worker

logger = logging.getLogger(__name__)

def run(args):
    if args._shell_command is None and not args._argv:
        raise ArgumentError('Usage: vectis run -- PROGRAM [$1 [$2...]] '
                'or vectis run -c "shell one-liner" [$0 [$1 [$2...]]]')

    if args.suite is None:
        if args.default_suite is not None:
            args.suite = args.default_suite
        else:
            raise ArgumentError('--suite must be specified')

    for suite in (args.suite,):
        for ancestor in suite.hierarchy:
            if ancestor.mirror is None:
                raise ArgumentError('mirror or apt_cacher_ng must be '
                        'configured for {}'.format(ancestor))

    with Worker(['qemu', args.qemu_image]) as worker:
        worker.set_up_apt(args.suite)
        if args._shell_command is not None:
            worker.check_call(['sh', '-c', args._shell_command] +
                    args._argv)
        else:
            worker.check_call(args._argv)
