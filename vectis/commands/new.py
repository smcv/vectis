# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: MIT
# (see vectis/__init__.py)

import os

from vectis.virt import Machine

def vmdebootstrap_argv(args, setup_script):
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
            '--size={}'.format(args.size),
            '--grub',
            '--no-mbr',
            '--no-extlinux',
            '--mirror={}'.format(args.bootstrap_mirror),
            '--arch={}'.format(args.architecture),
        ]
    argv.append('--customize={}'.format(setup_script))

    return argv

def run(args):
    os.makedirs(args.storage, exist_ok=True)

    with Machine(args.builder) as machine:
        machine.check_call([
            'env', 'DEBIAN_FRONTEND=noninteractive',
            'apt-get', '-y', 'update',
            ])
        machine.check_call([
            'env', 'DEBIAN_FRONTEND=noninteractive',
            'apt-get', '-y', 'upgrade',
            ])
        machine.check_call([
            'apt-get',
            '-y',
            '--no-install-recommends',
            'install',

            'autopkgtest',
            'python3',
            'qemu-utils',
            'vmdebootstrap',
            ])

        machine.check_call([
                'env', 'DEBIAN_FRONTEND=noninteractive',
                machine.command_wrapper,
                '--',
                ] + vmdebootstrap_argv(args,
                    '{}/setup-testbed'.format(machine.scratch)) + [
                '--image={}/output.raw'.format(machine.scratch)])
        machine.check_call(['qemu-img', 'convert', '-f', 'raw', '-O',
                'qcow2', '-c', '-p',
                '{}/output.raw'.format(machine.scratch),
                '{}/output.qcow2'.format(machine.scratch),
            ])
        out = os.path.join(args.storage, args.machine)
        machine.copy_to_host('{}/output.qcow2'.format(machine.scratch),
                out + '.new')
        # FIXME: smoke-test the new image before renaming
        #os.rename(out + '.new', out)
