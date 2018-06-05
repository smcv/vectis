# Copyright © 2016-2017 Simon McVittie
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
    mirrors = args.get_mirrors()
    out = args.write_qemu_image
    qemu_image_size = args.qemu_image_size
    storage = args.storage
    vendor = args.vendor
    suite = args.get_suite(vendor, args.suite)
    uri = args._uri
    vmdebootstrap_options = args.vmdebootstrap_options
    default_dir = os.path.join(
        storage, architecture, str(vendor), str(suite))

    if uri is None:
        uri = mirrors.lookup_suite(suite)

    try:
        version = subprocess.check_output(
            ['dpkg-query', '-W', '-f${Version}', 'vmdebootstrap'],
            universal_newlines=True).rstrip('\n')
    except subprocess.CalledProcessException:
        # non-dpkg host, guess a recent version
        version = Version('1.7')
        debootstrap_version = Version('1.0.89')
    else:
        version = Version(version)
        debootstrap_version = subprocess.check_output(
            ['dpkg-query', '-W', '-f${Version}', 'debootstrap'],
            universal_newlines=True).rstrip('\n')
        debootstrap_version = Version(debootstrap_version)

    with TemporaryDirectory(prefix='vectis-bootstrap-') as scratch:
        argv = [
            'sudo',
            os.path.join(
                os.path.dirname(__file__), os.pardir,
                'vectis-command-wrapper'),
            '--',
        ]
        vmdb_argv, debootstrap_argv, default_name = vmdebootstrap_argv(
            version,
            architecture=architecture,
            components=args.components,
            debootstrap_version=debootstrap_version,
            kernel_package=kernel_package,
            qemu_image_size=qemu_image_size,
            suite=suite,
            uri=uri,
            merged_usr=args._merged_usr,
        )
        argv.extend(vmdb_argv)
        argv.append('--debootstrapopts=' + ' '.join(debootstrap_argv))
        argv.extend(vmdebootstrap_options)
        argv.append(
            '--customize={}'.format(os.path.join(
                os.path.dirname(__file__), os.pardir, 'setup-testbed')))
        argv.append('--owner={}'.format(pwd.getpwuid(os.getuid())[0]))
        argv.append('--image={}/output.raw'.format(scratch))

        subprocess.check_call(argv)
        subprocess.check_call([
            'qemu-img', 'convert', '-f', 'raw',
            '-O', 'qcow2', '-c', '-p',
            '{}/output.raw'.format(scratch),
            '{}/output.qcow2'.format(scratch),
        ])

        if out is None:
            out = os.path.join(default_dir, default_name)

        os.makedirs(os.path.dirname(out) or os.curdir, exist_ok=True)
        shutil.move('{}/output.qcow2'.format(scratch), out + '.new')

        try:
            with VirtWorker(
                    ['qemu', '{}.new'.format(out)],
                    storage=storage,
                    suite=suite,
                    mirrors=mirrors) as worker:
                worker.check_call([
                    'env',
                    'DEBIAN_FRONTEND=noninteractive',
                    'apt-get',
                    '-y',
                    '--no-install-recommends',
                    '-t', suite.apt_suite,
                    'install',

                    'python3',
                    'sbuild',
                    'schroot',
                ])
        except Exception:
            if not keep:
                os.remove(out + '.new')
            raise
        else:
            os.rename(out + '.new', out)
