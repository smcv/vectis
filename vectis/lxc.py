# Copyright © 2017 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging
import os
import textwrap
from tempfile import TemporaryDirectory

from vectis.util import (
        AtomicWriter,
        )
from vectis.worker import (
        VirtWorker,
        )

logger = logging.getLogger(__name__)

def set_up_lxc_net(worker, subnet):
    with TemporaryDirectory(prefix='vectis-lxc-') as tmp:
        with AtomicWriter(os.path.join(tmp, 'lxc-net')) as writer:
            writer.write(textwrap.dedent('''\
            USE_LXC_BRIDGE="true"
            LXC_BRIDGE="lxcbr0"
            LXC_ADDR="{subnet}.1"
            LXC_NETMASK="255.255.255.0"
            LXC_NETWORK="{subnet}.0/24"
            LXC_DHCP_RANGE="{subnet}.2,{subnet}.254"
            LXC_DHCP_MAX="253"
            LXC_DHCP_CONFILE=""
            LXC_DOMAIN=""
            ''').format(subnet=subnet))
        worker.copy_to_guest(os.path.join(tmp, 'lxc-net'),
                '/etc/default/lxc-net')

        with AtomicWriter(os.path.join(tmp, 'default.conf')) as writer:
            writer.write(textwrap.dedent('''\
            lxc.network.type = veth
            lxc.network.link = lxcbr0
            lxc.network.flags = up
            lxc.network.hwaddr = 00:16:3e:xx:xx:xx
            '''))
        worker.copy_to_guest(os.path.join(tmp, 'default.conf'),
                '/etc/lxc/default.conf')

    worker.check_call(['systemctl', 'enable', 'lxc-net'])
    worker.check_call(['systemctl', 'stop', 'lxc-net'])
    worker.check_call(['systemctl', 'start', 'lxc-net'])

def create_tarballs(args):
    os.makedirs(args.storage, exist_ok=True)

    if args.suite is None:
        args.suite = args.default_suite

    rootfs_tarball = '{arch}/{vendor}/{suite}/lxc-rootfs.tar.gz'.format(
            arch=args.architecture,
            vendor=args.vendor,
            suite=args.suite,
            )
    meta_tarball = '{arch}/{vendor}/{suite}/lxc-meta.tar.gz'.format(
            arch=args.architecture,
            vendor=args.vendor,
            suite=args.suite,
            )
    logger.info('Creating tarballs %s, %s...', rootfs_tarball, meta_tarball)

    with VirtWorker(args.worker.split(),
            suite=args.worker_suite,
            ) as worker:
        logger.info('Installing debootstrap etc.')
        worker.check_call([
            'env',
            'DEBIAN_FRONTEND=noninteractive',
            'apt-get',
            '-y',
            'install',

            'debootstrap',
            'lxc',
            'python3',
            ])
        set_up_lxc_net(worker, args.lxc_24bit_subnet)

        # FIXME: The lxc templates only allow installing the apt keyring
        # to use, and do not allow passing --keyring to debootstrap
        keyring = args.apt_key_package

        if keyring is not None:
            worker.call([
                'env',
                'DEBIAN_FRONTEND=noninteractive',
                'apt-get',
                '-y',
                '--no-install-recommends',
                'install',

                keyring,
                ])

        # FIXME: This is silly, but it's a limitation of the lxc templates.
        # We have to provide exactly two apt URLs.
        security_suite = args.vendor.get_suite(str(args.suite) + '-security')

        argv = [
                'env', 'DEBIAN_FRONTEND=noninteractive',
                worker.command_wrapper,
                '--',
                'lxc-create',
                '--template={}'.format(args.vendor),
                '--name={}-{}-{}'.format(args.vendor, args.suite,
                    args.architecture),
                '--',
                '--release={}'.format(args.suite),
                '--arch={}'.format(args.architecture),
                '--mirror={}'.format(args.mirror),
                '--security-mirror={}'.format(security_suite.mirror),
                ]

        if str(args.vendor) == 'ubuntu':
            argv.append('--variant=minbase')

        worker.check_call(argv)

        worker.check_call(['tar', '-C',
            '/var/lib/lxc/{}-{}-{}/rootfs'.format(args.vendor, args.suite,
                args.architecture),
            '-f', '{}/rootfs.tar.gz'.format(worker.scratch),
            '-z', '-c', '.'])
        worker.check_call(['tar', '-C',
            '/var/lib/lxc/{}-{}-{}'.format(args.vendor, args.suite,
                args.architecture),
            '-f', '{}/meta.tar.gz'.format(worker.scratch),
            '-z', '-c', 'config'])

        out = os.path.join(args.storage, rootfs_tarball)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        worker.copy_to_host('{}/rootfs.tar.gz'.format(worker.scratch), out + '.new')
        # FIXME: smoke-test it?
        os.rename(out + '.new', out)

        out = os.path.join(args.storage, meta_tarball)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        worker.copy_to_host('{}/meta.tar.gz'.format(worker.scratch), out + '.new')
        # FIXME: smoke-test it?
        os.rename(out + '.new', out)

    logger.info('Created tarballs %s, %s', rootfs_tarball, meta_tarball)
