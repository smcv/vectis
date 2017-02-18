# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging
import os
import subprocess

from debian.debian_support import (
        Version,
        )

from vectis.error import ArgumentError
from vectis.worker import Worker

logger = logging.getLogger(__name__)

def vmdebootstrap_argv(version, args):
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
            '--no-extlinux',
        ]

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

        worker_packages = [
            'autopkgtest',
            'grub2-common',
            'python3',
            'qemu-utils',
            'vmdebootstrap',
            ]

        # Optional (x86 only, but necessary for wheezy)
        optional_worker_packages = [
            'extlinux',
            'mbr',
            ]

        keyring = args.apt_key_package

        if keyring is not None:
            optional_worker_packages.append(keyring)

        worker.check_call([
            'env',
            'DEBIAN_FRONTEND=noninteractive',
            'apt-get',
            '-y',
            '--no-install-recommends',
            'install',
            ] + worker_packages)

        # Failure is ignored for these non-critical packages
        for p in optional_worker_packages:
            worker.call([
                'env',
                'DEBIAN_FRONTEND=noninteractive',
                'apt-get',
                '-y',
                '--no-install-recommends',
                'install',
                p])

        version = worker.dpkg_version('vmdebootstrap')

        argv = vmdebootstrap_argv(version, args)

        debootstrap_args = []

        if worker.call(['test', '-f', args.apt_key]) == 0:
            logger.info('Found apt key worker:{}'.format(args.apt_key))
            debootstrap_args.append('keyring={}'.format(args.apt_key))
        elif os.path.exists(args.apt_key):
            logger.info('Found apt key host:{}, copying to worker:{}'.format(
                args.apt_key, '{}/apt-key.gpg'.format(worker.scratch)))
            worker.copy_to_guest(args.apt_key,
                    '{}/apt-key.gpg'.format(worker.scratch))
            debootstrap_args.append('keyring={}/apt-key.gpg'.format(
                worker.scratch))
        else:
            logger.warning('Apt key host:{} not found; leaving it out and '
                    'hoping for the best'.format(args.apt_key))

        debootstrap_args.append('components={}'.format(
            ','.join(args.components)))

        if debootstrap_args:
            argv.append('--debootstrapopts={}'.format(
                ' '.join(debootstrap_args)))

        worker.copy_to_guest(
                os.path.join(os.path.dirname(__file__), '..', 'setup-testbed'),
                '{}/setup-testbed'.format(worker.scratch))
        worker.check_call(['chmod', '0755',
            '{}/setup-testbed'.format(worker.scratch)])
        worker.check_call([
                'env', 'DEBIAN_FRONTEND=noninteractive',
                worker.command_wrapper,
                '--',
                ] + argv + [
                '--customize={}/setup-testbed'.format(worker.scratch),
                '--image={}/output.raw'.format(worker.scratch),
                ])

        worker.check_call(['qemu-img', 'convert', '-f', 'raw', '-O',
                'qcow2', '-c', '-p',
                '{}/output.raw'.format(worker.scratch),
                '{}/output.qcow2'.format(worker.scratch),
            ])
        worker.copy_to_host('{}/output.qcow2'.format(worker.scratch),
                out + '.new')

    return out + '.new'

def run(args):
    if args.suite is None:
        if args.default_suite is not None:
            args.suite = args.default_suite
        else:
            raise ArgumentError('--suite must be specified')

    out = args.write_qemu_image
    os.makedirs(os.path.dirname(out), exist_ok=True)

    if False:
        created = new_ubuntu_cloud(args, out)
    else:
        created = new(args, out)

    try:
        with Worker(['qemu', created]) as worker:
            worker.set_up_apt(args.suite)
            worker.check_call(['apt-get', '-y', 'update'])
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
        if args._keep:
            if created != out + '.new':
                os.rename(created, out + '.new')
        else:
            os.remove(created)

        raise
    else:
        os.rename(created, out)
