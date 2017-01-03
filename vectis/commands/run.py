# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging

from vectis.error import ArgumentError
from vectis.virt import Machine

logger = logging.getLogger(__name__)

def run(args):
    if args._shell_command is None and not args._argv:
        raise ArgumentError('Usage: vectis run -- PROGRAM [$1 [$2...]] '
                'or vectis run -c "shell one-liner" [$0 [$1 [$2...]]]')

    with Machine('qemu {}'.format(args.qemu_image)) as machine:
        if args._shell_command is not None:
            machine.check_call(['sh', '-c', args._shell_command] +
                    args._argv)
        else:
            machine.check_call(args._argv)
