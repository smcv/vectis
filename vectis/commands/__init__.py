# Copyright © 2015-2017 Simon McVittie
# Copyright © 2017 Collabora Ltd.
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import argparse
import importlib
import logging
import os
import subprocess
import sys
from contextlib import suppress

from vectis.config import (Config)
from vectis.error import (Error)

logger = logging.getLogger(__name__)


class _AutopkgtestAction(argparse.Action):

    def __call__(self, parser, namespace, value, option_string=None):
        if value is True:
            with suppress(AttributeError):
                delattr(namespace, self.dest)
            return

        items = list(value.split(','))
        setattr(namespace, self.dest, items)


class _AssignList(argparse.Action):

    def __call__(self, parser, namespace, value, option_string=None):
        items = [value]
        setattr(namespace, self.dest, items)


class AssignCommaSeparated(argparse.Action):

    def __call__(self, parser, namespace, value, option_string=None):
        items = list(value.split(','))
        setattr(namespace, self.dest, items)


class _AppendForceList(argparse.Action):

    def __call__(self, parser, namespace, value, option_string=None):
        items = list(getattr(namespace, self.dest, []))
        items.append(value)
        setattr(namespace, self.dest, items)


class AppendCommaSeparated(argparse.Action):

    def __call__(self, parser, namespace, value, option_string=None):
        items = list(getattr(namespace, self.dest, []))
        items.extend(value.split(','))
        setattr(namespace, self.dest, items)


class _MirrorAction(argparse.Action):

    def __call__(self, parser, namespace, value, option_string=None):
        items = dict(getattr(namespace, self.dest, {}))

        if '=' in value:
            pre, post = value.split('=', 1)
            items[pre] = post
        else:
            items[None] = value

        setattr(namespace, self.dest, items)


class _DirectAction(argparse.Action):

    def __call__(self, parser, namespace, value, option_string=None):
        items = dict(getattr(namespace, self.dest, {}))
        items[value] = value
        setattr(namespace, self.dest, items)


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

    p.add_argument(
        '--{}worker'.format(arg_prefix),
        dest=dest_prefix + 'worker',
        help='Virtual machine to use to create it '
             '[default: {}]'.format(getattr(args, dest_prefix + 'worker')),
    )

    p.add_argument(
        '--{}worker-architecture'.format(arg_prefix),
        dest=dest_prefix + 'worker_architecture',
        help='Virtual machine architecture to use [default: {}]'.format(
            getattr(args, dest_prefix + 'worker_architecture')),
    )

    p.add_argument(
        '--{}worker-vendor'.format(arg_prefix),
        dest=dest_prefix + 'worker_vendor',
        help='Virtual machine vendor to use [default: {}]'.format(
            getattr(args, dest_prefix + 'worker_vendor')),
    )

    p.add_argument(
        '--{}worker-suite'.format(arg_prefix),
        dest=dest_prefix + 'worker_suite',
        help='Virtual machine suite to use [default: {}]'.format(
            getattr(args, dest_prefix + 'worker_suite')),
    )

def add_output_options(p):
    p.add_argument(
        '--output-parent',
        help='Leave output in subdirectories of this directory [default: ..]',
    )
    p.add_argument(
        '--output-dir',
        help='Leave output in this directory, which must be empty or not exist '
             '[default: create a new directory in OUTPUT_PARENT]',
    )

args = Config()

base = argparse.ArgumentParser(
    argument_default=argparse.SUPPRESS, add_help=False)
base.add_argument(
    '--storage',
    help='Directory for VM images and schroot tarballs [default: {}]'.format(
        args.storage),
)
base.add_argument(
    '--vendor',
    help='OS distribution or isolated environment to work with '
         '[default: {}]'.format(args.vendor),
)
base.add_argument(
    '--archive',
    help='OS distribution to look for on mirrors [default: {}]'.format(
        args.vendor),
)
base.add_argument(
    '--mirror', dest='mirrors', action=_MirrorAction,
    help='Use MIRROR for URI, for vendors/suites whose archive is ARCHIVE, '
         'or for suites not otherwise matched',
)
base.add_argument(
    '--direct', dest='mirrors', action=_DirectAction,
    help='Download the given URI or ARCHIVE from its '
         'canonical URI',
)
base.add_argument(
    '--qemu-ram-size',
    help='Use this much RAM for qemu virtual machines (e.g. 512M, 1G, 4G)',
)

parser = argparse.ArgumentParser(
    description='Do Debian-related things in a virtual machine.',
    argument_default=argparse.SUPPRESS,
    parents=(base,),
)
subparsers = parser.add_subparsers(metavar='COMMAND', dest='_subcommand')

help = ('Create an autopkgtest virtual machine without using an existing '
        'virtual machine (must be run as root)')
p = subparsers.add_parser(
    'bootstrap',
    help=help, description=help,
    argument_default=argparse.SUPPRESS,
    parents=(base,),
)
p.add_argument(
    '--size', dest='qemu_image_size',
    help='Size of image [default: {}]'.format(args.qemu_image_size),
)
p.add_argument(
    '--qemu-image', dest='write_qemu_image',
    help='Virtual machine image to create [default: {}]'.format(
        args.write_qemu_image),
)
p.add_argument(
    '--suite',
    help='Release suite [default: {}]'.format(args.default_suite),
)
p.add_argument('--architecture', '--arch',
               help='dpkg architecture [default: {}]'.format(args.architecture))
p.add_argument('--keep', action='store_true', default=False, dest='_keep',
               help='Keep the new image even if testing fails')
p.add_argument(
    '--uri', dest='_uri', default=None,
    help='apt URI, e.g. http://mirror/debian [default: auto]',
)

help = 'Create an autopkgtest virtual machine'
p = subparsers.add_parser(
    'new',
    help=help, description=help,
    argument_default=argparse.SUPPRESS,
    parents=(base,),
)
p.add_argument(
    '--size', dest='qemu_image_size',
    help='Size of image [default: {}]'.format(args.qemu_image_size),
)
p.add_argument(
    '--qemu-image', dest='write_qemu_image',
    help='Virtual machine image to create [default: {}]'.format(
        args.write_qemu_image),
)
add_worker_options(p, context='vmdebootstrap', context_implicit=True)
p.add_argument(
    '--suite',
    help='Release suite [default: {}]'.format(args.default_suite),
)
p.add_argument(
    '--architecture', '--arch',
    help='dpkg architecture [default: {}]'.format(args.architecture),
)
p.add_argument(
    '--keep', action='store_true', default=False, dest='_keep',
    help='Keep the new image even if testing fails',
)
p.add_argument(
    '--uri', dest='_uri', default=None,
    help='apt URI, e.g. http://mirror/debian [default: auto]',
)

help = ('Run a script or command, which may write output to ./out/ or '
        'equivalently $VECTIS_OUT or $AUTOPKGTEST_ARTIFACTS, and may '
        'use ./tmp/ or equivalently $VECTIS_TMP or $AUTOPKGTEST_TMP '
        'as a temporary workspace')
p = subparsers.add_parser(
    'run',
    help=help, description=help,
    argument_default=argparse.SUPPRESS,
    conflict_handler='resolve',
    parents=(base,),
)
add_output_options(p)
p.add_argument(
    '--apt-update', dest='_apt_update', default=False,
    help='Update apt lists [default: do not update]',
)
p.add_argument(
    '--in', '--input', dest='_input', default=None,
    help='Input directory or file to be copied to ./in/ and made available '
         'in the environment as $VECTIS_IN',
)
p.add_argument(
    '--chdir', dest='_chdir', metavar='PATH', default='.',
    help="Change directory to '.', 'in', 'out', 'tmp' or an absolute path "
    "before running the script or command [default: .]",
)
p.add_argument(
    '--qemu-image',
    help='Virtual machine image to use [default: {}]'.format(args.qemu_image),
)
p.add_argument(
    '-c', '--shell-command', dest='_shell_command',
    default=None,
    help='Run this shell command',
)
p.add_argument(
    '_argv', metavar='ARGV', nargs='*', default=[],
    help='Argument vector',
)
p.add_argument(
    '--suite',
    help='Release suite [default: {}]'.format(args.default_suite),
)

help = 'Create a schroot tarball with sbuild-createchroot'
p = subparsers.add_parser(
    'sbuild-tarball',
    help=help, description=help,
    argument_default=argparse.SUPPRESS,
    parents=(base,),
)
add_worker_options(p)
p.add_argument(
    '--debootstrap-script',
    help='debootstrap script to run [default: {}]'.format(
        args.debootstrap_script),
)
p.add_argument(
    '--suite',
    help='Release suite [default: {}]'.format(args.default_suite),
)
p.add_argument(
    '--architecture', '--arch',
    help='dpkg architecture [default: {}]'.format(args.architecture),
)
p.add_argument(
    '--test-package', dest='_test_package', default='hostname',
    help='An architecture-dependent test package to build as a smoke-test',
)
p.add_argument(
    '--keep', action='store_true', default=False, dest='_keep',
    help='Keep the new tarball even if testing fails',
)
p.add_argument(
    '--uri', dest='_uri', default=None,
    help='apt URI, e.g. http://mirror/debian [default: auto]',
)

help = 'Create a minbase tarball suitable for piuparts'
p = subparsers.add_parser(
    'minbase-tarball',
    help=help, description=help,
    argument_default=argparse.SUPPRESS,
    parents=(base,),
)
add_worker_options(p)
p.add_argument(
    '--debootstrap-script',
    help='debootstrap script to run [default: {}]'.format(
        args.debootstrap_script),
)
p.add_argument(
    '--merged-usr', '--usrmerge', dest='_merged_usr',
    default=False, action='store_true',
    help="carry out the /usr merge [default: don't]",
)
p.add_argument(
    '--uri', dest='_uri', default=None,
    help='apt URI, e.g. http://mirror/debian [default: auto]',
)
p.add_argument(
    '--suite',
    help='Release suite [default: {}]'.format(args.default_suite),
)
p.add_argument(
    '--architecture', '--arch',
    help='dpkg architecture [default: {}]'.format(args.architecture),
)

help = 'Create LXC tarballs'
p = subparsers.add_parser(
    'lxc-tarballs',
    help=help, description=help,
    argument_default=argparse.SUPPRESS,
    parents=(base,),
)
add_worker_options(p, context='lxc', context_implicit=True)
p.add_argument(
    '--suite',
    help='Release suite [default: {}]'.format(args.default_suite),
)
p.add_argument(
    '--architecture', '--arch',
    help='dpkg architecture [default: {}]'.format(args.architecture),
)
p.add_argument(
    '--uri', dest='_uri', default=None,
    help='apt URI, e.g. http://mirror/debian [default: auto]',
)
p.add_argument(
    '--security-uri', dest='_security_uri', default=None,
    help='apt URI, e.g. http://mirror/debian-security [default: auto]',
)

help = 'Build a Debian package with sbuild'
p = subparsers.add_parser(
    'sbuild',
    help=help, description=help,
    argument_default=argparse.SUPPRESS,
    conflict_handler='resolve',
    parents=(base,),
)
add_worker_options(p, context='sbuild', context_implicit=True)
p.add_argument(
    '_buildables', metavar='CHANGES_OR_DSC_OR_DIR', nargs='*', default=[],
    help='sourceful .changes or .dsc or source directory',
)
p.add_argument(
    '--suite', '--distribution', '-d',
    help='Distribution release suite [default: auto-detect from input]',
)
p.add_argument(
    '--components', action=AppendCommaSeparated,
    help='Distribution components',
)
add_output_options(p)

p.add_argument(
    '--versions-since', '-v', '--since-version',
    dest='_versions_since', default=None,
    help='Populate .changes file with versions since this',
)
p.add_argument(
    '--parallel', '-J', type=int, dest='parallel',
    help='Set desired parallelization level',
)
p.add_argument(
    '--extra-repository', action='append', default=[],
    dest='_extra_repository',
    help='Add an apt source',
)
p.add_argument(
    '--indep', '-i', action='store_true', dest='_indep', default=False,
    help='Build architecture-independent packages (default: build all)',
)
p.add_argument(
    '--binaries', action='store_false', dest='_source_only', default=False,
    help='Build binary packages [default: build binaries]',
)
p.add_argument(
    '--no-binaries', '--source-only',
    action='store_true', dest='_source_only', default=False,
    help='Do not build binary packages [default: build binaries]',
)
p.add_argument(
    '--rebuild-source', action='store_true', dest='_build_source',
    default=None,
    help='Build source package '
         '[default: only if we do not already have one]',
)
p.add_argument(
    '--no-source', action='store_false', dest='_build_source',
    help='Do not build source package '
         '[default: only if we do not already have one]',
)
p.add_argument(
    '--architecture', '--arch', '-a', action='append', dest='_archs',
    default=[],
    help='Build architecture-dependent packages for this architecture '
         '(default: architectures installed on host machine, or '
         'host machine architecture if not installed)')
p.add_argument(
    '--together', '--indep-together',
    dest='sbuild_indep_together', action='store_true',
    help='Build architecture-independent packages along with first '
         'architecture',
)
p.add_argument(
    '--apart', '--indep-apart',
    dest='sbuild_indep_together', action='store_false',
    help='Build architecture-independent packages separately',
)
p.add_argument(
    '--source-together', dest='sbuild_source_together', action='store_true',
    help='Build architecture-independent packages along with first '
         'architecture',
)
p.add_argument(
    '--source-apart', dest='sbuild_source_together', action='store_false',
    help='Build architecture-independent packages separately',
)
p.add_argument(
    '--reprepro-dir', dest='_reprepro_dir', default=None,
    help='Inject built packages into this reprepro repository',
)
p.add_argument(
    '--reprepro-suite', dest='_reprepro_suite', default=None,
    help='Inject built packages into this reprepro suite (default: same as '
         'package)',
)
p.add_argument(
    '-u', dest='_u_ignored', choices=['c', 's'],
    help='Ignored for compatibility with dgit: vectis never signs changes '
         'files',
)
p.add_argument(
    '--unsigned-changes', '--unsigned-source',
    dest='_u_ignored', action='store_const', const=None,
    help='Ignored for compatibility with dgit: vectis never signs changes '
         'files',
)
p.add_argument(
    '--tar-ignore', '-I', nargs='?', metavar='PATTERN',
    dest='dpkg_source_tar_ignore', action='append', const=...,
    help='Build with --dpkg-source-opt=--tar-ignore[=PATTERN]',
)
p.add_argument(
    '--diff-ignore', '-i', nargs='?', metavar='PATTERN',
    dest='dpkg_source_diff_ignore', const=...,
    help='Build with --dpkg-source-opt=--diff-ignore[=PATTERN]',
)
p.add_argument(
    '--extend-diff-ignore', metavar='PATTERN',
    dest='dpkg_source_extend_diff_ignore', action='append',
    help='Build with --dpkg-source-opt=--extend-diff-ignore=PATTERN',
)
p.add_argument(
    '--autopkgtest', nargs='?', metavar='MODE[,MODE]',
    action=_AutopkgtestAction, const=True,
    help='Run autopkgtest [with the given modes] [default: {}]'.format(
        ','.join(args.autopkgtest),
    ),
)
p.add_argument(
    '--no-autopkgtest', dest='autopkgtest', action='store_const',
    const=(),
    help='Do not run autopkgtest after building',
)
p.add_argument(
    '--piuparts', dest='piuparts_tarballs', nargs='?',
    metavar='TARBALL[,TARBALL]',
    action=_AutopkgtestAction, const=True,
    help='Run piuparts [with the given base tarballs] [default: {}]'.format(
        ','.join(args.piuparts_tarballs),
    ),
)
p.add_argument(
    '--no-piuparts', dest='piuparts_tarballs', action='store_const',
    const=(),
    help='Do not run piuparts after building',
)
p.add_argument(
    '--build-profiles', '-P', dest='_build_profiles',
    default=None, metavar='PROFILE[,PROFILE...]',
    help='Use comma-separated build profiles',
)
p.add_argument(
    '--add-build-profile', dest='_add_build_profile',
    action='append', default=[], metavar='PROFILE',
    help='Use individually specified build profile',
)
p.add_argument(
    '--add-deb-build-option', dest='_add_deb_build_option',
    action='append', default=[], metavar='OPTION[=VALUE]',
    help='Set something in DEB_BUILD_OPTIONS',
)
p.add_argument(
    '--include-orig-source', '-s', dest='_include_orig_source',
    choices=[
        'yes', 'force', 'always', 'a',
        'auto', 'maybe', 'i',
        'no', 'never', 'd',
    ],
    default=None,
    help='Always, maybe or never include orig.tar.* in changes file',
)
p.add_argument(
    '--force-orig-source', dest='_include_orig_source',
    action='store_const', const='yes',
    help='Equivalent to --include-orig-source=yes',
)
p.add_argument(
    '--orig-dir', dest='orig_dirs', action=_AssignList,
    default=args.orig_dirs, metavar='DIR',
    help='Replace search path for orig*.tar.* with only DIR',
)
p.add_argument(
    '--add-orig-dir', dest='orig_dirs', action=_AppendForceList,
    metavar='DIR',
    help='Add DIR to search path for orig*.tar.*',
)
p.add_argument(
    '--sbuild-option', dest='_sbuild_options', action='append',
    default=[], metavar='OPTION',
    help='Add OPTION to all sbuild command-lines',
)
p.add_argument(
    '--append-to-version', dest='_append_to_version', default='',
    metavar='SUFFIX',
    help="Add SUFFIX to built binaries' versions",
)

help = 'Run autopkgtest tests'
p = subparsers.add_parser(
    'autopkgtest',
    help=help, description=help, argument_default=argparse.SUPPRESS,
    conflict_handler='resolve', parents=(base,),
)
add_worker_options(p)
add_worker_options(p, context='lxc')
p.add_argument(
    '--suite',
    help='Distribution release suite to be tested [default: auto-detect '
         'from input]',
)
p.add_argument(
    '--extra-repository', action='append', default=[], dest='_extra_repository',
    help='Add an apt source',
)
p.add_argument(
    '--built-binaries', action='store_const', const=True,
    dest='_built_binaries', default=None,
    help='Build and install given source package [default: if no other '
         'binaries given]',
)
p.add_argument(
    '--no-built-binaries', '-B', action='store_const', const=False,
    dest='_built_binaries', default=None,
    help="Don't build and install given source package [default: if no "
         'other binaries given]')
p.add_argument(
    '_things', metavar='CHANGES_OR_DSC_OR_DIR', nargs='+', default=[],
    help='Things to test (source or binary .changes, source .dsc, etc.',
)

help = 'Run piuparts tests'
p = subparsers.add_parser(
    'piuparts',
    help=help, description=help, argument_default=argparse.SUPPRESS,
    conflict_handler='resolve', parents=(base,),
)
add_worker_options(p, context='piuparts', context_implicit=True)
p.add_argument(
    '--suite', '-d',
    help='Distribution release suite to be tested [default: auto-detect '
         'from input]',
)
p.add_argument(
    '--extra-repository', action='append', default=[], dest='_extra_repository',
    help='Add an apt source',
)
p.add_argument(
    '_things', metavar='CHANGES_OR_DEB', nargs='+', default=[],
    help='Things to test (binary .changes, .deb, package name)',
)
p.add_argument(
    '--architecture', '--arch',
    help='dpkg architecture [default: {}]'.format(args.architecture),
)


def main():
    logging.getLogger().setLevel(logging.INFO)

    if sys.stderr.isatty():
        try:
            import colorlog
        except ImportError:
            pass
        else:
            formatter = colorlog.ColoredFormatter(
                '%(log_color)s%(levelname)s:%(name)s:%(reset)s %(message)s')
            handler = logging.StreamHandler()
            handler.setFormatter(formatter)
            logging.getLogger().addHandler(handler)

    # This is a no-op if we already attached a (coloured log) handler
    logging.basicConfig()

    parser.parse_args(namespace=args)

    if 'VECTIS_DEBUG_COMMAND_LINE' in os.environ:
        args.dump()
        return

    try:
        if args._subcommand is None:
            parser.print_usage()
            raise SystemExit(1)

        importlib.import_module(
            'vectis.commands.' + args._subcommand.replace('-', '_')).run(args)
    except KeyboardInterrupt:
        raise SystemExit(130)
    except subprocess.CalledProcessError as e:
        logger.error('%s', e)
        raise SystemExit(1)
    except Error as e:
        logger.error('%s', e)
        raise SystemExit(1)
