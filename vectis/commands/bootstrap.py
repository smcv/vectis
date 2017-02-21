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
from vectis.worker import (
        VirtWorker,
        )

def run(args):
    if args.suite is None:
        if args.worker_suite is not None:
            args.suite = args.worker_suite
        else:
            raise ArgumentError('--suite must be specified')

    architecture = args.architecture
    keep = args._keep
    kernel_package = args.get_kernel_package(architecture)
    mirror = args.mirror
    out = args.write_qemu_image
    qemu_image_size = args.qemu_image_size
    suite = args.suite
    vmdebootstrap_options = args.vmdebootstrap_options

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
        argv = [
                'sudo',
                os.path.join(os.path.dirname(__file__),
                    os.pardir, 'vectis-command-wrapper'),
                '--',
                ]
        argv.extend(vmdebootstrap_argv(version,
                architecture=architecture,
                kernel_package=kernel_package,
                mirror=mirror,
                qemu_image_size=qemu_image_size,
                suite=suite,
                ))
        argv.extend(vmdebootstrap_options)
        argv.append('--customize={}'.format(
                    os.path.join(os.path.dirname(__file__),
                        os.pardir, 'setup-testbed')))
        argv.append('--owner={}'.format(pwd.getpwuid(os.getuid())[0]))
        argv.append('--image={}/output.raw'.format(scratch))

        subprocess.check_call(argv)
        subprocess.check_call(['qemu-img', 'convert', '-f', 'raw',
            '-O', 'qcow2', '-c', '-p',
            '{}/output.raw'.format(scratch),
            '{}/output.qcow2'.format(scratch)])
        os.makedirs(os.path.dirname(out), exist_ok=True)
        shutil.move('{}/output.qcow2'.format(scratch), out + '.new')

        try:
            with VirtWorker(['qemu', '{}.new'.format(out)],
                    suite=suite, mirror=mirror) as worker:
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
            if not keep:
                os.remove(out + '.new')
            raise
        else:
            os.rename(out + '.new', out)
