# Copyright © 2016-2017 Simon McVittie
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


def vmdebootstrap_argv(
        version,
        *,
        architecture,
        components,
        debootstrap_version,
        kernel_package,
        merged_usr,
        qemu_image_size,
        suite,
        uri):
    default_name = 'autopkgtest.qcow2'
    argv = [
        'env',
        # We use apt-cacher-ng in non-proxy mode, to make it easier to
        # add extra apt sources later that can't go via this proxy.
        'AUTOPKGTEST_APT_PROXY=DIRECT',
        'MIRROR={}'.format(uri),
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
        '--mirror={}'.format(uri),
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

    debootstrap_args = []

    debootstrap_args.append('components={}'.format(
        ','.join(components)))

    if debootstrap_version >= Version('1.0.86~'):
        if merged_usr:
            debootstrap_args.append('merged-usr')
            default_name = 'autopkgtest-merged-usr.qcow2'
        else:
            # piuparts really doesn't like merged /usr
            debootstrap_args.append('no-merged-usr')

    return argv, debootstrap_args, default_name


def new_ubuntu_cloud(
        *,
        architecture,
        default_dir,
        out,
        qemu_image_size,
        suite,
        uri,
        vendor):
    if out is None:
        out = os.path.join(default_dir, 'autopkgtest.qcow2')

    out_dir = os.path.dirname(out) or os.curdir
    argv = ['autopkgtest-buildvm-ubuntu-cloud']

    argv.append('--arch={}'.format(architecture))
    argv.append('--disk-size={}'.format(qemu_image_size))
    argv.append('--mirror={}'.format(uri))
    argv.append('--proxy=DIRECT')
    argv.append('--release={}'.format(suite))
    argv.append('--verbose')
    argv.append('--output-dir={}'.format(out_dir))

    image = '{}/autopkgtest-{}-{}.img'.format(out_dir, suite, architecture)

    try:
        subprocess.check_call(argv)
    except:
        if os.path.exists(image):
            os.unlink(image)
        raise
    else:
        return image, out


def new(
        *,
        apt_key,
        apt_key_package,
        architecture,
        components,
        default_dir,
        kernel_package,
        merged_usr,
        mirrors,
        out,
        qemu_image_size,
        storage,
        suite,
        uri,
        vmdebootstrap_options,
        vmdebootstrap_worker,
        vmdebootstrap_worker_suite):

    for suite in (vmdebootstrap_worker_suite, suite):
        for ancestor in suite.hierarchy:
            mirror = mirrors.lookup_suite(ancestor)
            if mirror is None:
                raise ArgumentError(
                    'No mirror configured for {}'.format(ancestor))

    with VirtWorker(
            vmdebootstrap_worker,
            mirrors=mirrors,
            storage=storage,
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
            '-t', vmdebootstrap_worker_suite.apt_suite,
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
                '-t', vmdebootstrap_worker_suite.apt_suite,
                '--no-install-recommends',
                'install',
                p])

        version = worker.dpkg_version('vmdebootstrap')
        debootstrap_version = worker.dpkg_version('debootstrap')

        argv, debootstrap_args, default_name = vmdebootstrap_argv(
            version,
            architecture=architecture,
            components=components,
            debootstrap_version=debootstrap_version,
            kernel_package=kernel_package,
            qemu_image_size=qemu_image_size,
            suite=suite,
            uri=uri,
            merged_usr=merged_usr,
        )
        argv.extend(vmdebootstrap_options)

        if worker.call(['test', '-f', apt_key]) == 0:
            logger.info('Found apt key worker:{}'.format(apt_key))
            debootstrap_args.append('keyring={}'.format(apt_key))
        elif os.path.exists(apt_key):
            logger.info('Found apt key host:{}, copying to worker:{}'.format(
                apt_key, '{}/apt-key.gpg'.format(worker.scratch)))
            worker.copy_to_guest(
                apt_key, '{}/apt-key.gpg'.format(worker.scratch))
            debootstrap_args.append('keyring={}/apt-key.gpg'.format(
                worker.scratch))
        else:
            logger.warning('Apt key host:{} not found; leaving it out and '
                           'hoping for the best'.format(apt_key))

        if debootstrap_args:
            argv.append('--debootstrapopts={}'.format(
                ' '.join(debootstrap_args)))

        worker.copy_to_guest(
            os.path.join(os.path.dirname(__file__), '..', 'setup-testbed'),
            '{}/setup-testbed'.format(worker.scratch))
        worker.check_call([
            'chmod', '0755', '{}/setup-testbed'.format(worker.scratch)])
        worker.check_call([
            'env', 'DEBIAN_FRONTEND=noninteractive',
            worker.command_wrapper,
            '--',
        ] + argv + [
            '--customize={}/setup-testbed'.format(worker.scratch),
            '--image={}/output.raw'.format(worker.scratch),
        ])

        worker.check_call([
            'qemu-img', 'convert', '-f', 'raw', '-O',
            'qcow2', '-c', '-p',
            '{}/output.raw'.format(worker.scratch),
            '{}/output.qcow2'.format(worker.scratch),
        ])

        if out is None:
            out = os.path.join(default_dir, default_name)

        os.makedirs(os.path.dirname(out) or os.curdir, exist_ok=True)
        worker.copy_to_host(
            '{}/output.qcow2'.format(worker.scratch), out + '.new')

    return out + '.new', out


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
    mirrors = args.get_mirrors()
    out = args.write_qemu_image
    qemu_image_size = args.qemu_image_size
    storage = args.storage
    uri = args._uri
    vendor = args.vendor
    suite = args.get_suite(vendor, args.suite)
    vmdebootstrap_options = args.vmdebootstrap_options
    vmdebootstrap_worker = args.vmdebootstrap_worker
    vmdebootstrap_worker_suite = args.vmdebootstrap_worker_suite
    default_dir = os.path.join(
        storage, architecture, str(vendor), str(suite))

    if uri is None:
        uri = mirrors.lookup_suite(suite)

    if False:
        created, out = new_ubuntu_cloud(
            architecture=architecture,
            default_dir=default_dir,
            out=out,
            qemu_image_size=qemu_image_size,
            suite=suite,
            uri=uri,
            vendor=vendor,
        )
    else:
        created, out = new(
            apt_key=apt_key,
            apt_key_package=apt_key_package,
            architecture=architecture,
            components=components,
            default_dir=default_dir,
            kernel_package=kernel_package,
            merged_usr=args._merged_usr,
            mirrors=mirrors,
            out=out,
            qemu_image_size=qemu_image_size,
            storage=storage,
            suite=suite,
            uri=uri,
            vmdebootstrap_options=vmdebootstrap_options,
            vmdebootstrap_worker=vmdebootstrap_worker,
            vmdebootstrap_worker_suite=vmdebootstrap_worker_suite,
        )

    try:
        with VirtWorker(
                ['qemu', created],
                mirrors=mirrors,
                storage=storage,
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
