# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: MIT
# (see vectis/__init__.py)

import logging
import os
import shutil
import subprocess
import textwrap
from collections import OrderedDict
from tempfile import TemporaryDirectory

from debian.deb822 import (
        Changes,
        Dsc,
        )

from vectis.virt import Machine
from vectis.util import AtomicWriter

logger = logging.getLogger(__name__)

def _run(args, machine, tmp):
    machine_arch = machine.check_output(['dpkg', '--print-architecture'],
            universal_newlines=True).strip()

    tarballs_copied = set()

    if not args._buildables:
        args._buildables = ['.']

    logger.info('Installing sbuild')
    machine.check_call(['apt-get', '-y', 'update'])
    machine.check_call([
        'apt-get',
        '-y',
        '--no-install-recommends',
        'install',

        'python3',
        'sbuild',
        ])

    # { 'foo_1.2.dsc': { 'amd64': '../build-area/foo_1.2_amd64.changes' } }
    changes_produced = {}
    logs = {}
    merged_changes = {}

    for buildable in args._buildables:
        logger.info('Processing: %s', buildable)

        changes_produced[buildable] = {}
        logs[buildable] = {}
        merged_changes[buildable] = OrderedDict()

        suite = args.default_suite

        archs = args._archs
        indep = args._indep
        source_only = False # FIXME
        dsc_name = None
        dsc = None

        if os.path.isdir(buildable):
            raise AssertionError('Building from a source directory '
                    'not implemented yet')

        elif buildable.endswith('.changes'):
            d = os.path.dirname(buildable)
            sourceful_changes_name = buildable
            sourceful_changes = Changes(open(buildable))
            assert 'source' in sourceful_changes['architecture']

            nominal_suite = sourceful_changes['distribution']

            for f in sourceful_changes['files']:
                if f['name'].endswith('.dsc'):
                    dsc_name = os.path.join(d, f['name'])

            assert dsc_name is not None
            dsc = Dsc(open(dsc_name))

        elif buildable.endswith('.dsc'):
            dsc_name = buildable
            dsc = Dsc(open(dsc_name))
            d = os.path.dirname(dsc_name)

            nominal_suite = None

            sourceful_changes = None
            sourceful_changes_name = None

        else:
            raise SystemExit('buildable must be .changes, .dsc or '
                    'directory')

        if dsc is not None:
            source_package = dsc['source']
            version_no_epoch = dsc['version'].split(':', 1)[-1]
            arch_wildcards = set(dsc['architecture'].split())
            binary_packages = [p.strip() for p in dsc['binary'].split(',')]

            machine.copy_to_guest(dsc_name,
                    '{}/{}'.format(machine.scratch,
                        os.path.basename(dsc_name)))

            for f in dsc['files']:
                machine.copy_to_guest(os.path.join(d, f['name']),
                        '{}/{}'.format(machine.scratch, f['name']))

        product_prefix = '{}_{}'.format(source_package,
                version_no_epoch)

        builds_i386 = False
        builds_natively = False

        for wildcard in arch_wildcards:
            if subprocess.call(['dpkg-architecture',
                    '-a' + machine_arch, '--is', wildcard]) == 0:
                logger.info('Package builds natively on %s', machine_arch)
                builds_natively = True

            if subprocess.call(['dpkg-architecture',
                    '-ai386', '--is', wildcard]) == 0:
                logger.info('Package builds on i386')
                builds_i386 = True

        if source_only:
            logger.info('Selected source-only build')
        elif archs or indep:
            # the user is always right
            logger.info('Using architectures from command-line')
        else:
            logger.info('Choosing architectures to build')
            indep = ('all' in arch_wildcards)
            archs = []

            if builds_natively:
                archs.append(machine_arch)

            for line in subprocess.check_output([
                    'sh', '-c', '"$@" || :',
                    'sh', # argv[0]
                    'dpkg-query', '-W', r'--showformat=${binary:Package}\n',
                    ] + [p.strip() for p in binary_packages],
                    universal_newlines=True).splitlines():
                if ':' in line:
                    arch = line.split(':')[-1]
                    if arch not in archs:
                        logger.info('Building on %s because %s is installed',
                                arch, line)
                        archs.append(arch)

            if (machine_arch == 'amd64' and builds_i386 and
                    not builds_natively and 'i386' not in archs):
                archs.append('i386')

        if 'all' not in arch_wildcards:
            indep = False

        together_with = None

        if indep:
            if args.sbuild_together and archs:
                if machine_arch in archs:
                    together_with = machine_arch
                else:
                    together_with = archs[0]
            else:
                archs.insert(0, 'all')

        if not source_only:
            logger.info('Selected architectures: %r', archs)
            logger.info('Selected architecture-independent: %r', indep)

        if indep and together_with is not None:
            logger.info('Architecture-independent packages will be built '
                        'alongside %s', together_with)

        suite = nominal_suite

        if args.suite is not None:
            suite = args.suite

            if nominal_suite is None:
                nominal_suite = args.suite

        if suite is None:
            raise AssertionError('Must specify --suite when building '
                    'from a .dsc file')

        base = suite

        if base == 'UNRELEASED':
            base = args.platform.unstable_suite

        base = base.replace('-backports', '')
        base = base.replace('-security', '')

        for arch in archs:
            logger.info('Building architecture: %s', arch)

            if arch == 'all':
                logger.info('(on %s)', machine_arch)
                use_arch = machine_arch
            else:
                use_arch = arch

            sbuild_tarball = (
                    'sbuild-{platform}-{base}-{arch}.tar.gz'.format(
                        arch=use_arch,
                        platform=args.platform,
                        base=base,
                        ))

            if sbuild_tarball not in tarballs_copied:
                machine.copy_to_guest(os.path.join(args.storage,
                            sbuild_tarball),
                        '{}/{}'.format(machine.scratch, sbuild_tarball))
                tarballs_copied.add(sbuild_tarball)

            with AtomicWriter(os.path.join(tmp, 'sbuild.conf')) as writer:
                writer.write(textwrap.dedent('''
                [vectis]
                type=file
                description=An autobuilder
                file={scratch}/sbuild-{platform}-{base}-{arch}.tar.gz
                groups=root,sbuild
                root-groups=root,sbuild
                profile=sbuild
                ''').format(
                    base=base,
                    platform=args.platform,
                    arch=use_arch,
                    scratch=machine.scratch))
            machine.copy_to_guest(os.path.join(tmp, 'sbuild.conf'),
                    '/etc/schroot/chroot.d/vectis')

            argv = [
                    machine.command_wrapper,
                    '--chdir',
                    machine.scratch,
                    '--',
                    'runuser',
                    '-u', 'sbuild',
                    '--',
                    'sbuild',
                    '-c', 'vectis',
                    '-d', nominal_suite,
                    '--no-run-lintian',
            ]

            if suite.endswith('-backports'):
                argv.append('--extra-repository')
                argv.append('deb {} {} {}'.format(
                    argv.mirror,
                    suite,
                    ' '.join(argv.components)))
                argv.append('--build-dep-resolver=aptitude')

            for x in args._extra_repository:
                argv.append('--extra-repository')
                argv.append(x)

            if suite == 'experimental':
                argv.append('--build-dep-resolver=aspcud')
                argv.append('--aspcud-criteria=-removed,-changed,'
                        '-new,'
                        '-count(solution,APT-Release:=/experimental/)')

            if (args.sbuild_parallel > 1 and
                    not suite.startswith(('jessie', 'wheezy'))):
                argv.append('--debbuildopt=-J{}'.format(
                    args.sbuild_parallel))

            if args.sbuild_force_parallel > 1:
                argv.append('--debbuildopt=-j{}'.format(
                    args.sbuild_force_parallel))

            if arch == 'all':
                logger.info('Architecture: all')
                argv.append('-A')
                argv.append('--no-arch-any')
            elif arch == together_with:
                logger.info('Architecture: %s + all', arch)
                argv.append('-A')
                argv.append('--arch')
                argv.append(arch)
            else:
                logger.info('Architecture: %s only', arch)
                argv.append('--arch')
                argv.append(arch)

            argv.append('{}/{}'.format(machine.scratch,
                os.path.basename(dsc_name)))

            logger.info('Running %r', argv)
            machine.check_call(argv)

            product = '{}/{}_{}.changes'.format(machine.scratch,
                product_prefix,
                arch)
            logger.info('Copying %s back to host...', product)
            copied_back = os.path.join(args.output_builds,
                    '{}_{}.changes'.format(product_prefix, arch))
            machine.copy_to_host(product, copied_back)
            changes_produced[buildable][arch] = copied_back

            changes_out = Changes(open(copied_back))

            # Note that we mix use_arch and arch here: an Architecture: all
            # build produces foo_1.2_amd64.build, which we rename
            product = '{}/{}_{}.build'.format(machine.scratch,
                product_prefix,
                use_arch)
            product = machine.check_output(['readlink', '-f', product],
                    universal_newlines=True).rstrip('\n')
            logger.info('Copying %s back to host as %s_%s.build...',
                    product, product_prefix, arch)
            copied_back = os.path.join(args.output_builds,
                    '{}_{}.build'.format(product_prefix, arch))
            machine.copy_to_host(product, copied_back)
            logs[buildable][arch] = copied_back

            for f in changes_out['files']:
                assert '/' not in f['name']
                assert not f['name'].startswith('.')

                logger.info('Additionally copying %s back to host...',
                        f['name'])
                product = '{}/{}'.format(machine.scratch, f['name'])
                copied_back = os.path.join(args.output_builds, f['name'])
                machine.copy_to_host(product, copied_back)

        if indep and together_with is None and sourceful_changes_name:
            c = os.path.join(args.output_builds,
                    '{}_source+all.changes'.format(product_prefix))
            merged_changes[buildable]['source+all'] = c
            with AtomicWriter(c) as writer:
                subprocess.check_call([
                    'mergechanges',
                    changes_produced[buildable]['all'],
                    sourceful_changes_name,
                    ], stdout=writer)

        if changes_produced[buildable]:
            c = os.path.join(args.output_builds,
                    '{}_multi.changes'.format(product_prefix))
            merged_changes[buildable]['multi'] = c
            if len(changes_produced[buildable]) > 1:
                with AtomicWriter(c) as writer:
                    subprocess.check_call(['mergechanges'] +
                        list(changes_produced[buildable].values()),
                        stdout=writer)
            else:
                shutil.copy(next(iter(changes_produced[buildable].values())),
                        c)

        if not source_only and sourceful_changes_name is not None:
            c = os.path.join(args.output_builds,
                    '{}_source+multi.changes'.format(product_prefix))
            merged_changes[buildable]['source+multi'] = c

            with AtomicWriter(c) as writer:
                subprocess.check_call([
                        'mergechanges',
                        os.path.join(args.output_builds,
                                '{}_multi.changes'.format(product_prefix)),
                        sourceful_changes_name,
                    ],
                    stdout=writer)

        if sourceful_changes_name:
            c = os.path.join(args.output_builds,
                    '{}_source.changes'.format(product_prefix))
            with AtomicWriter(c) as writer:
                subprocess.check_call([
                        'mergechanges',
                        '--source',
                        sourceful_changes_name,
                        sourceful_changes_name,
                    ],
                    stdout=writer)

            merged_changes[buildable]['source'] = c

    for buildable in args._buildables:
        logger.info('Built changes files from %s:\n\t%s',
                buildable,
                '\n\t'.join(sorted(changes_produced[buildable].values())),
                )

        logger.info('Build logs from %s:\n\t%s',
                buildable,
                '\n\t'.join(sorted(logs[buildable].values())),
                )

        # Run lintian near the end for better visibility
        for x in 'source+multi', 'multi', 'source':
            if x in merged_changes[buildable]:
                subprocess.call(['lintian', '-I', '-i',
                    merged_changes[buildable][x]])
                break

    # We print these separately, right at the end, so that if you built more
    # than one thing, the last screenful of information is the really
    # important bit for testing/signing/upload
    for buildable in args._buildables:
        logger.info('Merged changes files from %s:\n\t%s',
                buildable,
                '\n\t'.join(merged_changes[buildable].values()),
                )

def run(args):
    with Machine(args.builder) as machine:
        with TemporaryDirectory() as tmp:
            _run(args, machine, tmp)
