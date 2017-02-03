# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import os
import shutil
import subprocess
from tempfile import TemporaryDirectory

from vectis.commands.new import vmdebootstrap_argv
from vectis.error import ArgumentError
from vectis.virt import Machine

def run(args):
    if args.suite is None:
        if args.unstable_suite is not None:
            args.suite = args.unstable_suite
        else:
            raise ArgumentError('--suite must be specified')

    with TemporaryDirectory() as scratch:
        subprocess.check_call(vmdebootstrap_argv(args,
            '/usr/share/autopkgtest/setup-commands/setup-testbed') +
                ['--image={}/output.raw'.format(scratch)])
        subprocess.check_call(['qemu-img', 'convert', '-f', 'raw',
            '-O', 'qcow2', '-c', '-p',
            '{}/output.raw'.format(scratch),
            '{}/output.qcow2'.format(scratch)])
        out = args.write_qemu_image
        shutil.move('{}/output.qcow2'.format(scratch), out + '.new')

        try:
            with Machine('qemu {}.new'.format(out)) as machine:
                machine.check_call(['apt-get', '-y', 'update'])
                machine.check_call(['apt-get',
                    '-y',
                    '--no-install-recommends',
                    'install',

                    'python3',
                    'sbuild',
                    'schroot',
                    ])
        except:
            os.remove(out + '.new')
            raise
        else:
            os.rename(out + '.new', out)
