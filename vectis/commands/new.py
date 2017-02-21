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
from vectis.worker import (
        VirtWorker,
        )

logger = logging.getLogger(__name__)

def vmdebootstrap_argv(version, *,
        architecture,
        kernel_package,
        mirror,
        qemu_image_size,
        suite):
    argv = ['env',
            # We use apt-cacher-ng in non-proxy mode, to make it easier to
            # add extra apt sources later that can't go via this proxy.
            'AUTOPKGTEST_APT_PROXY=DIRECT',
            'MIRROR={}'.format(mirror),
            'RELEASE={}'.format(suite),

            'vmdebootstrap',
            '--log=/dev/stderr',
            '--verbose',
            '--serial-console',
            '--distribution={}'.format(suite),
            '--user=user',
            '--hostname=host',
            '--sparse',
            '--size={}'.format(qemu_image_size),
            '--mirror={}'.format(mirror),
            '--arch={}'.format(architecture),
            '--grub',
            '--no-extlinux',
        ]

    if kernel_package is not None:
        if version >= Version('1.4'):
            argv.append('--kernel-package={}'.format(kernel_package))
        else:
            argv.append('--no-kernel')
            argv.append('--package={}'.format(kernel_package))

    return argv

def new_ubuntu_cloud(*,
        architecture,
        mirror,
        out,
        qemu_image_size,
        suite,
        vendor):
    out_dir = os.path.dirname(out)
    argv = ['autopkgtest-buildvm-ubuntu-cloud']
    suite = str(vendor.get_suite(suite))

    argv.append('--arch={}'.format(architecture))
    argv.append('--disk-size={}'.format(qemu_image_size))
    argv.append('--mirror={}'.format(mirror))
    argv.append('--proxy=DIRECT')
    argv.append('--release={}'.format(suite))
    argv.append('--verbose')
    argv.append('--output-dir={}'.format(out_dir))

    image = '{}/autopkgtest-{}-{}.img'.format(out_dir, suite,
            architecture)

    try:
        subprocess.check_call(argv)
    except:
        if os.path.exists(image):
            os.unlink(image)
        raise
    else:
        return image

def new(*,
        apt_key,
        apt_key_package,
        architecture,
        components,
        kernel_package,
        mirror,
        out,
        qemu_image_size,
        suite,
        vmdebootstrap_options,
        vmdebootstrap_worker,
        vmdebootstrap_worker_suite):

    for suite in (vmdebootstrap_worker_suite, suite):
        for ancestor in suite.hierarchy:
            if ancestor.mirror is None:
                raise ArgumentError('mirror or apt_cacher_ng must be '
                        'configured for {}'.format(ancestor))

    with VirtWorker(vmdebootstrap_worker.split(),
            suite=vmdebootstrap_worker_suite,
            ) as worker:
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

        keyring = apt_key_package

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

        argv = vmdebootstrap_argv(version,
                architecture=architecture,
                kernel_package=kernel_package,
                mirror=mirror,
                qemu_image_size=qemu_image_size,
                suite=suite,
                )
        argv.extend(vmdebootstrap_options)

        debootstrap_args = []

        if worker.call(['test', '-f', apt_key]) == 0:
            logger.info('Found apt key worker:{}'.format(apt_key))
            debootstrap_args.append('keyring={}'.format(apt_key))
        elif os.path.exists(apt_key):
            logger.info('Found apt key host:{}, copying to worker:{}'.format(
                apt_key, '{}/apt-key.gpg'.format(worker.scratch)))
            worker.copy_to_guest(apt_key,
                    '{}/apt-key.gpg'.format(worker.scratch))
            debootstrap_args.append('keyring={}/apt-key.gpg'.format(
                worker.scratch))
        else:
            logger.warning('Apt key host:{} not found; leaving it out and '
                    'hoping for the best'.format(apt_key))

        debootstrap_args.append('components={}'.format(
            ','.join(components)))

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

    apt_key = args.apt_key
    apt_key_package = args.apt_key_package
    architecture = args.architecture
    components = args.components
    keep = args._keep
    kernel_package = args.get_kernel_package(architecture)
    mirror = args.mirror
    out = args.write_qemu_image
    qemu_image_size = args.qemu_image_size
    suite = args.suite
    vendor = args.vendor
    vmdebootstrap_options = args.vmdebootstrap_options
    vmdebootstrap_worker = args.vmdebootstrap_worker
    vmdebootstrap_worker_suite = args.vmdebootstrap_worker_suite

    os.makedirs(os.path.dirname(out), exist_ok=True)

    if False:
        created = new_ubuntu_cloud(
                architecture=architecture,
                mirror=mirror,
                out=out,
                qemu_image_size=qemu_image_size,
                suite=suite,
                vendor=vendor,
                )
    else:
        created = new(
                apt_key=apt_key,
                apt_key_package=apt_key_package,
                architecture=architecture,
                components=components,
                kernel_package=kernel_package,
                mirror=mirror,
                out=out,
                qemu_image_size=qemu_image_size,
                suite=suite,
                vmdebootstrap_options=vmdebootstrap_options,
                vmdebootstrap_worker=vmdebootstrap_worker,
                vmdebootstrap_worker_suite=vmdebootstrap_worker_suite,
                )

    try:
        with VirtWorker(['qemu', created],
                suite=suite,
                ) as worker:
            worker.set_up_apt()
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
        if keep:
            if created != out + '.new':
                os.rename(created, out + '.new')
        else:
            os.remove(created)

        raise
    else:
        os.rename(created, out)
