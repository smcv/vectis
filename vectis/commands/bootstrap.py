# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import os
import pwd
import shutil
import subprocess
from tempfile import TemporaryDirectory

from debian.debian_support import (
        Version,
        )

from vectis.commands.new import vmdebootstrap_argv
from vectis.error import ArgumentError
from vectis.worker import Worker

def run(args):
    if args.suite is None:
        if args.worker_suite is not None:
            args.suite = args.worker_suite
        else:
            raise ArgumentError('--suite must be specified')

    try:
        version = subprocess.check_output(
                ['dpkg-query', '-W', '-f${Version}', 'vmdebootstrap'],
                universal_newlines=True).rstrip('\n')
    except:
        # non-dpkg host, guess a recent version
        version = Version('1.7')
    else:
        version = Version(version)

    with TemporaryDirectory(prefix='vectis-bootstrap-') as scratch:
        subprocess.check_call(['sudo',
                ] + vmdebootstrap_argv(version, args) + [
                '--customize={}'.format(
                    os.path.join(os.path.dirname(__file__),
                        os.pardir, 'setup-testbed')),
                '--owner={}'.format(pwd.getpwuid(os.getuid())[0]),
                '--image={}/output.raw'.format(scratch),
                ])
        subprocess.check_call(['qemu-img', 'convert', '-f', 'raw',
            '-O', 'qcow2', '-c', '-p',
            '{}/output.raw'.format(scratch),
            '{}/output.qcow2'.format(scratch)])
        out = args.write_qemu_image
        os.makedirs(os.path.dirname(out), exist_ok=True)
        shutil.move('{}/output.qcow2'.format(scratch), out + '.new')

        try:
            with Worker(['qemu', '{}.new'.format(out)]) as worker:
                worker.set_up_apt(args.suite,
                        mirror=args.mirror)
                worker.check_call([
                    'env',
                    'DEBIAN_FRONTEND=noninteractive',
                    'apt-get',
                    '-y',
                    '--no-install-recommends',
                    'install',

                    'python3',
                    'sbuild',
                    'schroot',
                    ])
        except:
            if not args._keep:
                os.remove(out + '.new')
            raise
        else:
            os.rename(out + '.new', out)
