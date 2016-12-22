# Copyright © 2015-2016 Simon McVittie
# SPDX-License-Identifier: MIT
# (see vectis/__init__.py)

import argparse
import importlib
import logging

from vectis.config import (Config)

logging.basicConfig()
logging.getLogger().setLevel(logging.INFO)

args = Config()

base = argparse.ArgumentParser(argument_default=argparse.SUPPRESS,
        add_help=False)
base.add_argument('--storage',
        help='Directory for VM images and schroot tarballs '
        '[default: {}]'.format(args.storage))
base.add_argument('--platform',
        help='OS distribution or isolated environment to work with '
        '[default: {}]'.format(args.platform))
base.add_argument('--archive',
        help='OS distribution to look for on mirrors '
        '[default: {}]'.format(args.platform))
base.add_argument('--mirror',
        help='Mirror [default: {}]'.format(args.mirror))

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
p.add_argument('--size',
        help='Size of image [default: {}]'.format(args.size))
p.add_argument('--bootstrap-mirror',
        help='Mirror to use for initial setup '
        '[default: {}]'.format(args.bootstrap_mirror))
p.add_argument('--qemu-image',
        help='Virtual machine image to create '
        '[default: {}]'.format(args.qemu_image))
p.add_argument('--suite',
        help='Release suite [default: {}]'.format(args.default_suite))
p.add_argument('--architecture', '--arch',
        help='dpkg architecture [default: {}]'.format(args.architecture))

help = 'Create an autopkgtest virtual machine'
p = subparsers.add_parser('new',
        help=help, description=help,
        argument_default=argparse.SUPPRESS,
        parents=(base,),
        )
p.add_argument('--size',
        help='Size of image [default: {}]'.format(args.size))
p.add_argument('--qemu-image',
        help='Virtual machine image to create '
        '[default: {}]'.format(args.qemu_image))
p.add_argument('--builder',
        help='Virtual machine to use to create it '
        '[default: {}]'.format(args.builder))
p.add_argument('--suite',
        help='Release suite [default: {}]'.format(args.default_suite))
p.add_argument('--architecture', '--arch',
        help='dpkg architecture [default: {}]'.format(args.architecture))

help = 'Create a schroot tarball with sbuild-createchroot'
p = subparsers.add_parser('sbuild-tarball',
        help=help, description=help,
        argument_default=argparse.SUPPRESS,
        parents=(base,),
        )
p.add_argument('--builder',
        help='Virtual machine to use '
        '[default: {}]'.format(args.builder))
p.add_argument('--debootstrap-script',
        help='debootstrap script to run '
        '[default: {}]'.format(args.debootstrap_script))
p.add_argument('--suite',
        help='Release suite [default: {}]'.format(args.default_suite))
p.add_argument('--architecture', '--arch',
        help='dpkg architecture [default: {}]'.format(args.architecture))
p.add_argument('--test-package', dest='_test_package',
        help='An architecture-dependent test package to build as a smoke-test',
        default='sed')

help = 'Build a Debian package with sbuild'
p = subparsers.add_parser('sbuild',
        help=help, description=help,
        argument_default=argparse.SUPPRESS,
        conflict_handler='resolve',
        parents=(base,),
        )
p.add_argument('--builder',
        help='Virtual machine image to use '
        '[default: {}]'.format(args.builder))
p.add_argument('_buildables', metavar='CHANGES_OR_DSC_OR_DIR',
        help='sourceful .changes or .dsc or source directory', nargs='*',
        default=[])
p.add_argument('--suite', '--distribution', '-d',
        help='Distribution release suite [default: auto-detect from input]')
p.add_argument('--output-builds', '--build-area',
        help='Leave output here [default: parent directory]')
p.add_argument('--versions-since', dest='_versions_since', default=None,
        help='Populate .changes file with versions since this')
p.add_argument('--parallel', '-J', type=int, dest='parallel',
        help='Suggest a parallel build')
p.add_argument('--force-parallel', '-j', type=int, dest='sbuild_force_parallel',
        help='Force a parallel build')
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

parser.parse_args(namespace=args)

importlib.import_module('vectis.commands.' +
        args._subcommand.replace('-', '_')).run(args)
