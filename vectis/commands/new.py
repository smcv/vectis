# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import os
import subprocess

from debian.debian_support import (
        Version,
        )

from vectis.worker import Worker

def vmdebootstrap_argv(version, args, setup_script):
    argv = ['env',
            # We use apt-cacher-ng in non-proxy mode, to make it easier to
            # add extra apt sources later that can't go via this proxy.
            'AUTOPKGTEST_APT_PROXY=DIRECT',
            'MIRROR={}'.format(args.mirror),
            'RELEASE={}'.format(args.suite),

            'vmdebootstrap',
            '--log=/dev/stderr',
            '--verbose',
            '--serial-console',
            '--distribution={}'.format(args.suite),
            '--user=user',
            '--hostname=host',
            '--sparse',
            '--size={}'.format(args.qemu_image_size),
            '--mirror={}'.format(args.bootstrap_mirror),
            '--arch={}'.format(args.architecture),
            '--grub',
            '--no-mbr',
            '--no-extlinux',
        ]
    argv.append('--customize={}'.format(setup_script))

    kernel = args.get_kernel_package(args.architecture)

    if kernel is not None:
        if version >= Version('1.4'):
            argv.append('--kernel-package={}'.format(kernel))
        else:
            argv.append('--no-kernel')
            argv.append('--package={}'.format(kernel))

    argv.extend(args.vmdebootstrap_options)

    return argv

def new_ubuntu_cloud(args, out):
    out_dir = os.path.dirname(out)
    argv = ['autopkgtest-buildvm-ubuntu-cloud']
    suite = str(args.vendor.get_suite(args.suite))

    argv.append('--arch={}'.format(args.architecture))
    argv.append('--disk-size={}'.format(args.qemu_image_size))
    argv.append('--mirror={}'.format(args.mirror))
    argv.append('--proxy=DIRECT')
    argv.append('--release={}'.format(suite))
    argv.append('--verbose')
    argv.append('--output-dir={}'.format(out_dir))

    image = '{}/autopkgtest-{}-{}.img'.format(out_dir, suite,
            args.architecture)

    try:
        subprocess.check_call(argv)
    except:
        if os.path.exists(image):
            os.unlink(image)
        raise
    else:
        return image

def new(args, out):
    with Worker(args.vmdebootstrap_worker.split()) as worker:
        worker.set_up_apt(args.vmdebootstrap_worker_suite)
        worker.check_call([
            'env', 'DEBIAN_FRONTEND=noninteractive',
            'apt-get', '-y', 'upgrade',
            ])
        worker.check_call([
            'apt-get',
            '-y',
            '--no-install-recommends',
            'install',

            'autopkgtest',
            'mbr',
            'python3',
            'qemu-utils',
            'vmdebootstrap',
            ])

        version = worker.dpkg_version('vmdebootstrap')

        worker.check_call([
                'env', 'DEBIAN_FRONTEND=noninteractive',
                worker.command_wrapper,
                '--',
                ] + vmdebootstrap_argv(version, args,
                    '/usr/share/autopkgtest/setup-commands/setup-testbed') + [
                '--image={}/output.raw'.format(worker.scratch)])
        worker.check_call(['qemu-img', 'convert', '-f', 'raw', '-O',
                'qcow2', '-c', '-p',
                '{}/output.raw'.format(worker.scratch),
                '{}/output.qcow2'.format(worker.scratch),
            ])
        worker.copy_to_host('{}/output.qcow2'.format(worker.scratch),
                out + '.new')

    return out + '.new'

def run(args):
    os.makedirs(args.storage, exist_ok=True)
    out = args.write_qemu_image

    if False:
        created = new_ubuntu_cloud(args, out)
    else:
        created = new(args, out)

    try:
        with Worker(['qemu', created]) as worker:
            worker.set_up_apt(args.suite)
            worker.check_call(['apt-get', '-y', 'update'])
            worker.check_call(['apt-get',
                '-y',
                '--no-install-recommends',
                'install',

                'python3',
                'sbuild',
                'schroot',
                ])
    except:
        if args._keep:
            if created != out + '.new':
                os.rename(created, out + '.new')
        else:
            os.remove(created)

        raise
    else:
        os.rename(created, out)
