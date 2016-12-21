# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import glob
import logging
import os
import shutil
import subprocess
import textwrap
from collections import OrderedDict
from tempfile import TemporaryDirectory

from debian.changelog import (
        Changelog,
        )
from debian.deb822 import (
        Changes,
        Deb822,
        Dsc,
        )
from debian.debian_support import (
        Version,
        )

from vectis.virt import Machine
from vectis.util import AtomicWriter

logger = logging.getLogger(__name__)

class Buildable:
    def __init__(self, path):
        self.path = path

        self.arch_wildcards = set()
        self.archs = []
        self.binary_packages = []
        self.changes_produced = {}
        self.dirname = None
        self.dsc = None
        self.dsc_name = None
        self.indep = False
        self.logs = {}
        self.merged_changes = OrderedDict()
        self.nominal_suite = None
        self.product_prefix = None
        self.source_package = None
        self.sourceful_changes_name = None
        self.suite = None
        self.together_with = None
        self.version = None

        if os.path.isdir(self.path):
            changelog = os.path.join(self.path, 'debian', 'changelog')
            changelog = Changelog(open(changelog))
            self.source_package = changelog.get_package()
            self.nominal_suite = changelog.distributions
            self.version = Version(changelog.version)
            control = os.path.join(self.path, 'debian', 'control')

            if len(changelog.distributions.split()) != 1:
                raise SystemExit('Cannot build for multiple distributions at '
                        'once')

            for paragraph in Deb822.iter_paragraphs(open(control)):
                self.arch_wildcards |= set(
                        paragraph.get('architecture', '').split())
                binary = paragraph.get('package')

                if binary is not None:
                    self.binary_packages.append(binary)

        elif self.path.endswith('.changes'):
            self.dirname = os.path.dirname(self.path)
            self.sourceful_changes_name = self.path
            sourceful_changes = Changes(open(self.path))
            assert 'source' in sourceful_changes['architecture']

            self.nominal_suite = sourceful_changes['distribution']

            for f in sourceful_changes['files']:
                if f['name'].endswith('.dsc'):
                    self.dsc_name = os.path.join(self.dirname, f['name'])

            assert self.dsc_name is not None
            self.dsc = Dsc(open(self.dsc_name))

        elif self.path.endswith('.dsc'):
            self.dirname = os.path.dirname(self.path)
            self.dsc_name = self.path
            self.dsc = Dsc(open(self.dsc_name))

        else:
            raise ValueError('buildable must be .changes, .dsc or '
                    'directory, not {!r}'.format(self.path))

        if self.dsc is not None:
            self.source_package = self.dsc['source']
            self.version = Version(self.dsc['version'])
            self.arch_wildcards = set(self.dsc['architecture'].split())
            self.binary_packages = [p.strip()
                    for p in self.dsc['binary'].split(',')]

        version_no_epoch = Version(self.version)
        version_no_epoch.epoch = None
        self.product_prefix = '{}_{}'.format(self.source_package,
                version_no_epoch)

    def copy_source_to(self, machine):
        if self.dsc is not None:
            machine.copy_to_guest(self.dsc_name,
                    '{}/{}'.format(machine.scratch,
                        os.path.basename(self.dsc_name)))

            for f in self.dsc['files']:
                machine.copy_to_guest(os.path.join(self.dirname, f['name']),
                        '{}/{}'.format(machine.scratch, f['name']))
        else:
            machine.copy_to_guest(os.path.join(self.path, ''),
                    '{}/{}_source/'.format(machine.scratch,
                        self.product_prefix))
            machine.check_call(['chown', '-R', 'sbuild:sbuild',
                    '{}/{}_source/'.format(machine.scratch,
                        self.product_prefix)])
            if self.version.debian_revision is not None:
                orig_pattern = glob.escape(os.path.join(self.path, '..',
                        '{}_{}.orig.tar.'.format(self.source_package,
                            self.version.upstream_version))) + '*'
                logger.info('Looking for original tarballs: {}'.format(
                        orig_pattern))
                for orig in glob.glob(orig_pattern):
                    logger.info('Copying original tarball: {}'.format(orig))
                    machine.copy_to_guest(orig,
                            '{}/{}'.format(machine.scratch, os.path.basename(orig)))

    def select_archs(self, machine_arch, archs, indep, source_only, together,
            rebuild_source):
        builds_i386 = False
        builds_natively = False

        for wildcard in self.arch_wildcards:
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
            if rebuild_source or self.dsc is None:
                self.archs.append('source')
            return
        elif archs or indep:
            # the user is always right
            logger.info('Using architectures from command-line')
            self.archs = archs[:]
        else:
            logger.info('Choosing architectures to build')
            indep = ('all' in self.arch_wildcards)
            self.archs = []

            if builds_natively:
                self.archs.append(machine_arch)

            for line in subprocess.check_output([
                    'sh', '-c', '"$@" || :',
                    'sh', # argv[0]
                    'dpkg-query', '-W', r'--showformat=${binary:Package}\n',
                    ] + [p.strip() for p in self.binary_packages],
                    universal_newlines=True).splitlines():
                if ':' in line:
                    arch = line.split(':')[-1]
                    if arch not in self.archs:
                        logger.info('Building on %s because %s is installed',
                                arch, line)
                        self.archs.append(arch)

            if (machine_arch == 'amd64' and builds_i386 and
                    not builds_natively and 'i386' not in self.archs):
                self.archs.append('i386')

        if 'all' not in self.arch_wildcards:
            indep = False

        if indep:
            if together and self.archs:
                if machine_arch in self.archs:
                    self.together_with = machine_arch
                else:
                    self.together_with = self.archs[0]
            else:
                self.archs.insert(0, 'all')

        if self.dsc_name is None or rebuild_source:
            self.archs.insert(0, 'source')

        logger.info('Selected architectures: %r', self.archs)

        if indep and self.together_with is not None:
            logger.info('Architecture-independent packages will be built '
                        'alongside %s', self.together_with)

    def select_suite(self, suite):
        self.suite = self.nominal_suite

        if suite is not None:
            self.suite = suite

            if self.nominal_suite is None:
                self.nominal_suite = suite

        if self.suite is None:
            raise ValueError('Must specify --suite when building from '
                    '{!r}'.format(self.path))

    def __str__(self):
        return self.path

class Build:
    def __init__(self, buildable, arch, machine, machine_arch):
        self.buildable = buildable
        self.arch = arch
        self.machine = machine
        self.machine_arch = machine_arch

    def build(self, base, args, tmp, tarballs_copied):
        logger.info('Building architecture: %s', self.arch)

        if self.arch in ('all', 'source'):
            logger.info('(on %s)', self.machine_arch)
            use_arch = self.machine_arch
        else:
            use_arch = self.arch

        sbuild_tarball = (
                'sbuild-{platform}-{base}-{arch}.tar.gz'.format(
                    arch=use_arch,
                    platform=args.platform,
                    base=base,
                    ))

        if sbuild_tarball not in tarballs_copied:
            self.machine.copy_to_guest(os.path.join(args.storage,
                        sbuild_tarball),
                    '{}/{}'.format(self.machine.scratch, sbuild_tarball))
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
                scratch=self.machine.scratch))
        self.machine.copy_to_guest(os.path.join(tmp, 'sbuild.conf'),
                '/etc/schroot/chroot.d/vectis')

        argv = [
                self.machine.command_wrapper,
                '--chdir',
                self.machine.scratch,
                '--',
                'runuser',
                '-u', 'sbuild',
                '--',
                'sbuild',
                '-c', 'vectis',
                '-d', self.buildable.nominal_suite,
                '--no-run-lintian',
        ]

        if args._versions_since:
            argv.append('--debbuildopt=-v{}'.format(
                args._versions_since))

        if self.buildable.suite.endswith('-backports'):
            argv.append('--extra-repository')
            argv.append('deb {} {} {}'.format(
                args.mirror,
                self.buildable.suite,
                ' '.join(args.components)))
            argv.append('--build-dep-resolver=aptitude')

        for x in args._extra_repository:
            argv.append('--extra-repository')
            argv.append(x)

        if self.buildable.suite == 'experimental':
            argv.append('--build-dep-resolver=aspcud')
            argv.append('--aspcud-criteria=-removed,-changed,'
                    '-new,'
                    '-count(solution,APT-Release:=/experimental/)')

        if args.sbuild_force_parallel > 1:
            argv.append('--debbuildopt=-j{}'.format(
                args.sbuild_force_parallel))
        elif (args.parallel != 1 and
                not self.buildable.suite.startswith(('jessie', 'wheezy'))):
            if args.parallel:
                argv.append('--debbuildopt=-J{}'.format(
                    args.parallel))
            else:
                argv.append('--debbuildopt=-Jauto')

        argv.append('--dpkg-source-opt=-i')
        argv.append('--dpkg-source-opt=-I')

        if self.arch == 'all':
            logger.info('Architecture: all')
            argv.append('-A')
            argv.append('--no-arch-any')
        elif self.arch == self.buildable.together_with:
            logger.info('Architecture: %s + all', self.arch)
            argv.append('-A')
            argv.append('--arch')
            argv.append(self.arch)
        elif self.arch == 'source':
            logger.info('Source-only')
            argv.append('--no-arch-any')
            argv.append('--source')
        else:
            logger.info('Architecture: %s only', self.arch)
            argv.append('--arch')
            argv.append(self.arch)

        if self.buildable.dsc_name is None:
            # build a source package as a side-effect of the first build
            # (in practice this will be the 'source' build)
            argv.append('--dpkg-source-opt=-i')
            argv.append('--dpkg-source-opt=-I')
            argv.append('--no-clean-source')
            argv.append('--source')
            argv.append('{}/{}_source'.format(self.machine.scratch,
                self.buildable.product_prefix))
        else:
            argv.append('{}/{}'.format(self.machine.scratch,
                os.path.basename(self.buildable.dsc_name)))

        logger.info('Running %r', argv)
        self.machine.check_call(argv)

        product = '{}/{}_{}.changes'.format(self.machine.scratch,
            self.buildable.product_prefix,
            self.arch)
        logger.info('Copying %s back to host...', product)
        copied_back = os.path.join(args.output_builds,
                '{}_{}.changes'.format(self.buildable.product_prefix,
                    self.arch))
        self.machine.copy_to_host(product, copied_back)
        self.buildable.changes_produced[self.arch] = copied_back

        changes_out = Changes(open(copied_back))

        if self.buildable.dsc_name is None or self.arch == 'source':
            # We built a source package as a side-effect of the first
            # build, but we couldn't use --source-only-changes with a
            # jessie chroot.
            self.buildable.sourceful_changes_name = copied_back

            for f in changes_out['files']:
                if f['name'].endswith('.dsc'):
                    # expect to find exactly one .dsc file
                    assert self.buildable.dsc_name is None
                    self.buildable.dsc_name = os.path.join(args.output_builds,
                            f['name'])

            assert self.buildable.dsc_name is not None
            self.machine.check_call(['rm', '-fr',
                    '{}/{}_source/'.format(self.machine.scratch,
                        self.buildable.product_prefix)])

        # Note that we mix use_arch and arch here: an Architecture: all
        # build produces foo_1.2_amd64.build, which we rename
        product = '{}/{}_{}.build'.format(self.machine.scratch,
            self.buildable.product_prefix,
            use_arch)
        product = self.machine.check_output(['readlink', '-f', product],
                universal_newlines=True).rstrip('\n')
        logger.info('Copying %s back to host as %s_%s.build...',
                product, self.buildable.product_prefix, self.arch)
        copied_back = os.path.join(args.output_builds,
                '{}_{}.build'.format(self.buildable.product_prefix,
                    self.arch))
        self.machine.copy_to_host(product, copied_back)
        self.buildable.logs[self.arch] = copied_back

        for f in changes_out['files']:
            assert '/' not in f['name']
            assert not f['name'].startswith('.')

            logger.info('Additionally copying %s back to host...',
                    f['name'])
            product = '{}/{}'.format(self.machine.scratch, f['name'])
            copied_back = os.path.join(args.output_builds, f['name'])
            self.machine.copy_to_host(product, copied_back)

def _run(args, machine, tmp):
    machine_arch = machine.check_output(['dpkg', '--print-architecture'],
            universal_newlines=True).strip()
    tarballs_copied = set()
    buildables = []

    for a in (args._buildables or ['.']):
        buildables.append(Buildable(a))

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

    for buildable in buildables:
        logger.info('Processing: %s', buildable)

        buildable.copy_source_to(machine)

        buildable.select_archs(machine_arch, args._archs, args._indep,
                args._source_only, args.sbuild_together, args._rebuild_source)

        buildable.select_suite(args.suite)

        base = buildable.suite

        base = base.replace('-backports', '')
        base = base.replace('-security', '')

        if base in args.platform.aliases:
            base = args.platform.aliases[base]
        elif base in ('unstable', 'experimental', 'UNRELEASED'):
            base = args.platform.unstable_suite

        for arch in buildable.archs:
            build = Build(buildable, arch, machine, machine_arch)
            build.build(base, args, tmp, tarballs_copied)

        if buildable.sourceful_changes_name:
            c = os.path.join(args.output_builds,
                    '{}_source.changes'.format(buildable.product_prefix))
            if 'source' not in buildable.changes_produced:
                with AtomicWriter(c) as writer:
                    subprocess.check_call([
                            'mergechanges',
                            '--source',
                            buildable.sourceful_changes_name,
                            buildable.sourceful_changes_name,
                        ],
                        stdout=writer)

            buildable.merged_changes['source'] = c

        if ('all' in buildable.changes_produced and
                'source' in buildable.merged_changes):
            c = os.path.join(args.output_builds,
                    '{}_source+all.changes'.format(buildable.product_prefix))
            buildable.merged_changes['source+all'] = c
            with AtomicWriter(c) as writer:
                subprocess.check_call([
                    'mergechanges',
                    buildable.changes_produced['all'],
                    buildable.merged_changes['source'],
                    ], stdout=writer)

        c = os.path.join(args.output_builds,
                '{}_binary.changes'.format(buildable.product_prefix))

        binary_changes = []
        for k, v in buildable.changes_produced.items():
            if k != 'source':
                binary_changes.append(v)

        if len(binary_changes) > 1:
            with AtomicWriter(c) as writer:
                subprocess.check_call(['mergechanges'] + binary_changes,
                    stdout=writer)
            buildable.merged_changes['binary'] = c
        elif len(binary_changes) == 1:
            shutil.copy(binary_changes[0], c)
            buildable.merged_changes['binary'] = c
        # else it was source-only: no binary changes

        if ('source' in buildable.merged_changes and
                'binary' in buildable.merged_changes):
            c = os.path.join(args.output_builds,
                    '{}_source+binary.changes'.format(buildable.product_prefix))
            buildable.merged_changes['source+binary'] = c

            with AtomicWriter(c) as writer:
                subprocess.check_call([
                        'mergechanges',
                        buildable.merged_changes['source'],
                        buildable.merged_changes['binary'],
                    ],
                    stdout=writer)

    for buildable in buildables:
        logger.info('Built changes files from %s:\n\t%s',
                buildable,
                '\n\t'.join(sorted(buildable.changes_produced.values())),
                )

        logger.info('Build logs from %s:\n\t%s',
                buildable,
                '\n\t'.join(sorted(buildable.logs.values())),
                )

        # Run lintian near the end for better visibility
        for x in 'source+binary', 'binary', 'source':
            if x in buildable.merged_changes:
                subprocess.call(['lintian', '-I', '-i',
                    buildable.merged_changes[x]])

                reprepro_suite = args._reprepro_suite

                if reprepro_suite is None:
                    reprepro_suite = buildable.suite

                if args._reprepro_dir:
                    subprocess.call(['reprepro', '-b', args._reprepro_dir,
                        'removesrc', reprepro_suite, buildable.source_package])
                    subprocess.call(['reprepro', '--ignore=wrongdistribution',
                        '--ignore=missingfile',
                        '-b', args._reprepro_dir, 'include', reprepro_suite,
                        os.path.join(args.output_builds,
                            buildable.merged_changes[x])])

                break

    # We print these separately, right at the end, so that if you built more
    # than one thing, the last screenful of information is the really
    # important bit for testing/signing/upload
    for buildable in buildables:
        logger.info('Merged changes files from %s:\n\t%s',
                buildable,
                '\n\t'.join(buildable.merged_changes.values()),
                )

def run(args):
    with Machine(args.builder) as machine:
        with TemporaryDirectory() as tmp:
            _run(args, machine, tmp)
