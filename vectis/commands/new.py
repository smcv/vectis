# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
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
            '--mirror={}'.format(args.bootstrap_mirror),
            '--arch={}'.format(args.architecture),
        ]
    argv.append('--customize={}'.format(setup_script))

    if args.suite == 'wheezy':
        # FIXME: this assumes vmdebootstrap from jessie: different
        # options are needed for vmdebootstrap from sid.
        argv.extend([
            '--boottype=ext2',
            ])
    else:
        argv.extend([
            '--grub',
            '--no-mbr',
            '--no-extlinux',
            ])

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
            'mbr',
            'python3',
            'qemu-utils',
            'vmdebootstrap',
            ])

        machine.check_call([
                'env', 'DEBIAN_FRONTEND=noninteractive',
                machine.command_wrapper,
                '--',
                ] + vmdebootstrap_argv(args,
                    '/usr/share/autopkgtest/setup-commands/setup-testbed') + [
                '--image={}/output.raw'.format(machine.scratch)])
        machine.check_call(['qemu-img', 'convert', '-f', 'raw', '-O',
                'qcow2', '-c', '-p',
                '{}/output.raw'.format(machine.scratch),
                '{}/output.qcow2'.format(machine.scratch),
            ])
        out = os.path.join(args.storage, args.qemu_image)
        machine.copy_to_host('{}/output.qcow2'.format(machine.scratch),
                out + '.new')

        try:
            with Machine('qemu {}.new'.format(out)) as machine:
                machine.check_call(['apt-get', '-y', 'update'])
                machine.check_call(['apt-get',
                    '-y',
                    '--no-install-recommends',
                    'install',

                    'python3',
                    'sbuild',
                    'schroot',
                    ])
        except:
            os.remove(out + '.new')
            raise
        else:
            os.rename(out + '.new', out)
