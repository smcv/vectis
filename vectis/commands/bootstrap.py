# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import os
import shutil
import subprocess
from tempfile import TemporaryDirectory

from vectis.commands.new import vmdebootstrap_argv

def run(args):
    with TemporaryDirectory() as scratch:
        subprocess.check_call(vmdebootstrap_argv(args,
            '/usr/share/autopkgtest/setup-commands/setup-testbed') +
                ['--image={}/output.raw'.format(scratch)])
        subprocess.check_call(['qemu-img', 'convert', '-f', 'raw',
            '-O', 'qcow2', '-c', '-p',
            '{}/output.raw'.format(scratch),
            '{}/output.qcow2'.format(scratch)])
        out = os.path.join(args.storage, args.qemu_image)
        shutil.move('{}/output.qcow2'.format(scratch), out + '.new')
        os.rename(out + '.new', out)
