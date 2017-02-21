# Copyright © 2015-2017 Simon McVittie
# SPDX-License-Identifier: MIT
# (see vectis/__init__.py)

import argparse
import importlib
import logging
import subprocess

from vectis.config import (Config)
from vectis.error import (Error)

logger = logging.getLogger(__name__)

def add_worker_options(p, context=None, context_implicit=False):
    if context is None:
        arg_prefix = ''
        dest_prefix = ''
    elif context_implicit:
        arg_prefix = ''
        dest_prefix = context + '_'
    else:
        arg_prefix = context + '-'
        dest_prefix = context + '_'

    p.add_argument('--{}worker'.format(arg_prefix),
            dest=dest_prefix + 'worker',
            help='Virtual machine to use to create it '
            '[default: {}]'.format(
                getattr(args, dest_prefix + 'worker')))

    p.add_argument('--{}worker-vendor'.format(arg_prefix),
            dest=dest_prefix + 'worker_vendor',
            help='Virtual machine vendor to use '
            '[default: {}]'.format(
                getattr(args, dest_prefix + 'worker_vendor')))

    p.add_argument('--{}worker-suite'.format(arg_prefix),
            dest=dest_prefix + 'worker_suite',
            help='Virtual machine suite to use '
            '[default: {}]'.format(
                getattr(args, dest_prefix + 'worker_suite')))

args = Config()

base = argparse.ArgumentParser(argument_default=argparse.SUPPRESS,
        add_help=False)
base.add_argument('--storage',
        help='Directory for VM images and schroot tarballs '
        '[default: {}]'.format(args.storage))
base.add_argument('--vendor',
        help='OS distribution or isolated environment to work with '
        '[default: {}]'.format(args.vendor))
base.add_argument('--archive',
        help='OS distribution to look for on mirrors '
        '[default: {}]'.format(args.vendor))
base.add_argument('--mirror', help='Mirror to use')

parser = argparse.ArgumentParser(
        description='Do Debian-related things in a virtual machine.',
        argument_default=argparse.SUPPRESS,
        parents=(base,),
        )
subparsers = parser.add_subparsers(metavar='COMMAND', dest='_subcommand')

help=('Create an autopkgtest virtual machine without using an existing '
    'virtual machine (must be run as root)')
p = subparsers.add_parser('bootstrap',
        help=help, description=help,
        argument_default=argparse.SUPPRESS,
        parents=(base,),
        )
p.add_argument('--size', dest='qemu_image_size',
        help='Size of image [default: {}]'.format(args.qemu_image_size))
p.add_argument('--qemu-image', dest='write_qemu_image',
        help='Virtual machine image to create '
        '[default: {}]'.format(args.write_qemu_image))
p.add_argument('--suite',
        help='Release suite [default: {}]'.format(args.default_suite))
p.add_argument('--architecture', '--arch',
        help='dpkg architecture [default: {}]'.format(args.architecture))
p.add_argument('--keep', action='store_true', default=False, dest='_keep',
        help='Keep the new image even if testing fails')

help = 'Create an autopkgtest virtual machine'
p = subparsers.add_parser('new',
        help=help, description=help,
        argument_default=argparse.SUPPRESS,
        parents=(base,),
        )
p.add_argument('--size', dest='qemu_image_size',
        help='Size of image [default: {}]'.format(args.qemu_image_size))
p.add_argument('--qemu-image', dest='write_qemu_image',
        help='Virtual machine image to create '
        '[default: {}]'.format(args.write_qemu_image))
add_worker_options(p, context='vmdebootstrap', context_implicit=True)
p.add_argument('--suite',
        help='Release suite [default: {}]'.format(args.default_suite))
p.add_argument('--architecture', '--arch',
        help='dpkg architecture [default: {}]'.format(args.architecture))
p.add_argument('--keep', action='store_true', default=False, dest='_keep',
        help='Keep the new image even if testing fails')

help = 'Run a script or command'
p = subparsers.add_parser('run',
        help=help, description=help,
        argument_default=argparse.SUPPRESS,
        conflict_handler='resolve',
        parents=(base,),
        )
p.add_argument('--qemu-image',
        help='Virtual machine image to use '
        '[default: {}]'.format(args.qemu_image))
p.add_argument('-c', '--shell-command', dest='_shell_command',
        default=None,
        help='Run this shell command')
p.add_argument('_argv', metavar='ARGV',
        help='Argument vector', nargs='*',
        default=[])
p.add_argument('--suite',
        help='Release suite [default: {}]'.format(args.default_suite))

help = 'Create a schroot tarball with sbuild-createchroot'
p = subparsers.add_parser('sbuild-tarball',
        help=help, description=help,
        argument_default=argparse.SUPPRESS,
        parents=(base,),
        )
add_worker_options(p)
p.add_argument('--debootstrap-script',
        help='debootstrap script to run '
        '[default: {}]'.format(args.debootstrap_script))
p.add_argument('--suite',
        help='Release suite [default: {}]'.format(args.default_suite))
p.add_argument('--architecture', '--arch',
        help='dpkg architecture [default: {}]'.format(args.architecture))
p.add_argument('--test-package', dest='_test_package',
        help='An architecture-dependent test package to build as a smoke-test',
        default='hostname')
p.add_argument('--keep', action='store_true', default=False, dest='_keep',
        help='Keep the new tarball even if testing fails')

help = 'Create a minbase tarball suitable for piuparts'
p = subparsers.add_parser('minbase-tarball',
        help=help, description=help,
        argument_default=argparse.SUPPRESS,
        parents=(base,),
        )
add_worker_options(p)
p.add_argument('--debootstrap-script',
        help='debootstrap script to run '
        '[default: {}]'.format(args.debootstrap_script))
p.add_argument('--suite',
        help='Release suite [default: {}]'.format(args.default_suite))
p.add_argument('--architecture', '--arch',
        help='dpkg architecture [default: {}]'.format(args.architecture))

help = 'Create LXC tarballs'
p = subparsers.add_parser('lxc-tarballs',
        help=help, description=help,
        argument_default=argparse.SUPPRESS,
        parents=(base,),
        )
add_worker_options(p, context='lxc', context_implicit=True)
p.add_argument('--suite',
        help='Release suite [default: {}]'.format(args.default_suite))
p.add_argument('--architecture', '--arch',
        help='dpkg architecture [default: {}]'.format(args.architecture))

help = 'Build a Debian package with sbuild'
p = subparsers.add_parser('sbuild',
        help=help, description=help,
        argument_default=argparse.SUPPRESS,
        conflict_handler='resolve',
        parents=(base,),
        )
add_worker_options(p, context='sbuild', context_implicit=True)
p.add_argument('_buildables', metavar='CHANGES_OR_DSC_OR_DIR',
        help='sourceful .changes or .dsc or source directory', nargs='*',
        default=[])
p.add_argument('--suite', '--distribution', '-d',
        help='Distribution release suite [default: auto-detect from input]')
p.add_argument('--output-builds', '--build-area',
        help='Leave output here [default: parent directory]')
p.add_argument('--versions-since', '-v', '--since-version',
        dest='_versions_since', default=None,
        help='Populate .changes file with versions since this')
p.add_argument('--parallel', '-J', type=int, dest='parallel',
        help='Suggest a parallel build')
p.add_argument('--force-parallel', '-j', type=int, dest='force_parallel',
        help='Force a parallel build (or with -j1, a serial build)')
p.add_argument('--extra-repository', action='append', default=[],
        dest='_extra_repository',
        help='Add an apt source')
p.add_argument('--indep', '-i', action='store_true', dest='_indep',
        default=False,
        help='Build architecture-independent packages (default: build all)')
p.add_argument('--source-only', action='store_true', dest='_source_only',
        default=False, help='Only build a source package')
p.add_argument('--rebuild-source', action='store_true', dest='_rebuild_source',
        default=False, help='Rebuild a supplied .dsc file')
p.add_argument('--architecture', '--arch', '-a', action='append', dest='_archs',
        default=[],
        help='Build architecture-dependent packages for this architecture '
             '(default: architectures installed on host machine, or '
             'host machine architecture if not installed)')
p.add_argument('--together', dest='sbuild_together', action='store_true',
        help='Build architecture-independent packages along with first '
             'architecture')
p.add_argument('--apart', dest='sbuild_together', action='store_false',
        help='Build architecture-independent packages separately')
p.add_argument('--reprepro-dir', dest='_reprepro_dir', default=None,
        help='Inject built packages into this reprepro repository')
p.add_argument('--reprepro-suite', dest='_reprepro_suite', default=None,
        help='Inject built packages into this reprepro suite (default: same '
            'as package)')
p.add_argument('-u',
        dest='_u_ignored', choices=['c', 's'],
        help='Ignored for compatibility with dgit: vectis never signs '
            'changes files')
p.add_argument('--unsigned-changes', '--unsigned-source',
        dest='_u_ignored', action='store_const', const=None,
        help='Ignored for compatibility with dgit: vectis never signs '
            'changes files')
p.add_argument('--tar-ignore', '-I', nargs='?', metavar='PATTERN',
        dest='dpkg_source_tar_ignore', action='append', const=...,
        help='Build with --dpkg-source-opt=--tar-ignore[=PATTERN]')
p.add_argument('--diff-ignore', '-i', nargs='?', metavar='PATTERN',
        dest='dpkg_source_diff_ignore', const=...,
        help='Build with --dpkg-source-opt=--diff-ignore[=PATTERN]')
p.add_argument('--extend-diff-ignore', metavar='PATTERN',
        dest='dpkg_source_extend_diff_ignore', action='append',
        help='Build with --dpkg-source-opt=--extend-diff-ignore=PATTERN')
p.add_argument('--autopkgtest', action='store_true',
        help='Run autopkgtest after building')
p.add_argument('--no-autopkgtest', dest='autopkgtest', action='store_const',
        const=(),
        help='Do not run autopkgtest after building')
p.add_argument('--build-profiles', '-P', dest='_build_profiles',
        default=None, metavar='PROFILE[,PROFILE...]',
        help='Use comma-separated build profiles')
p.add_argument('--add-build-profile', dest='_add_build_profile',
        action='append', default=[], metavar='PROFILE',
        help='Use individually specified build profile')
p.add_argument('--add-deb-build-option', dest='_add_deb_build_option',
        action='append', default=[], metavar='OPTION[=VALUE]',
        help='Set something in DEB_BUILD_OPTIONS')

def main():
    logging.basicConfig()
    logging.getLogger().setLevel(logging.INFO)

    parser.parse_args(namespace=args)

    try:
        importlib.import_module('vectis.commands.' +
                args._subcommand.replace('-', '_')).run(args)
    except KeyboardInterrupt:
        raise SystemExit(130)
    except subprocess.CalledProcessError as e:
        logger.error('%s', e)
        raise SystemExit(1)
    except Error as e:
        logger.error('%s', e)
        raise SystemExit(1)
