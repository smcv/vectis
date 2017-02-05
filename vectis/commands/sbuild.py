# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging
import os
import shutil
import subprocess
import textwrap
import time
from tempfile import TemporaryDirectory

from debian.deb822 import (
        Changes,
        Dsc,
        )
from debian.debian_support import (
        Version,
        )

from vectis.debuild import (
        Buildable,
        )
from vectis.error import (
        CannotHappen,
        )
from vectis.virt import Machine
from vectis.util import AtomicWriter

logger = logging.getLogger(__name__)

class Build:
    def __init__(self, buildable, arch, machine,
            *, output_builds):
        self.buildable = buildable
        self.arch = arch
        self.machine = machine
        self.output_builds = output_builds

    def build(self, suite, args):
        self.machine.check_call(['install', '-d', '-m755',
            '-osbuild', '-gsbuild',
            '{}/out'.format(self.machine.scratch)])

        logger.info('Building architecture: %s', self.arch)

        if self.arch in ('all', 'source'):
            logger.info('(on %s)', self.machine.dpkg_architecture)
            use_arch = self.machine.dpkg_architecture
        else:
            use_arch = self.arch

        hierarchy = suite.hierarchy

        sbuild_tarball = (
                'sbuild-{vendor}-{base}-{arch}.tar.gz'.format(
                    arch=use_arch,
                    vendor=args.vendor,
                    base=hierarchy[-1],
                    ))

        self.machine.copy_to_guest(os.path.join(args.storage,
                    sbuild_tarball),
                '{}/in/{}'.format(self.machine.scratch, sbuild_tarball),
                cache=True)

        chroot = '{base}-{arch}-sbuild'.format(base=hierarchy[-1],
                arch=use_arch)


        with TemporaryDirectory() as tmp:
            with AtomicWriter(os.path.join(tmp, 'sbuild.conf')) as writer:
                writer.write(textwrap.dedent('''
                [{chroot}]
                type=file
                description=An autobuilder
                file={scratch}/in/{sbuild_tarball}
                groups=root,sbuild
                root-groups=root,sbuild
                profile=sbuild
                ''').format(
                    chroot=chroot,
                    sbuild_tarball=sbuild_tarball,
                    scratch=self.machine.scratch))
            self.machine.copy_to_guest(os.path.join(tmp, 'sbuild.conf'),
                    '/etc/schroot/chroot.d/{}'.format(chroot))

        argv = [
                self.machine.command_wrapper,
                '--chdir',
                '{}/out'.format(self.machine.scratch),
                '--',
                'runuser',
                '-u', 'sbuild',
                '--',
                'sbuild',
                '-c', chroot,
                '-d', self.buildable.nominal_suite,
                '--no-run-lintian',
        ]

        if args._versions_since:
            argv.append('--debbuildopt=-v{}'.format(
                args._versions_since))

        for child in hierarchy[:-1]:
            argv.append('--extra-repository')
            argv.append('deb {} {} {}'.format(
                child.mirror,
                child.apt_suite,
                ' '.join(args.components)))

            if child.sbuild_resolver:
                argv.extend(child.sbuild_resolver)

        for x in args._extra_repository:
            argv.append('--extra-repository')
            argv.append(x)

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

        if args.dpkg_source_diff_ignore is ...:
            argv.append('--dpkg-source-opt=-i')
        elif args.dpkg_source_diff_ignore is not None:
            argv.append('--dpkg-source-opt=-i{}'.format(
                args.dpkg_source_diff_ignore))

        for pattern in args.dpkg_source_tar_ignore:
            if pattern is ...:
                argv.append('--dpkg-source-opt=-I')
            else:
                argv.append('--dpkg-source-opt=-I{}'.format(pattern))

        for pattern in args.dpkg_source_extend_diff_ignore:
            argv.append('--dpkg-source-opt=--extend-diff-ignore={}'.format(
                pattern))

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

        if self.buildable.dsc_name is not None:
            if 'source' in self.buildable.changes_produced:
                argv.append('{}/out/{}'.format(self.machine.scratch,
                    os.path.basename(self.buildable.dsc_name)))
            else:
                argv.append('{}/in/{}'.format(self.machine.scratch,
                    os.path.basename(self.buildable.dsc_name)))
        elif self.buildable.source_from_archive:
            argv.append(self.buildable.buildable)
        else:
            # build a source package as a side-effect of the first build
            # (in practice this will be the 'source' build)
            argv.append('--no-clean-source')
            argv.append('--source')
            argv.append('{}/in/{}_source'.format(self.machine.scratch,
                self.buildable.product_prefix))

        logger.info('Running %r', argv)
        try:
            self.machine.check_call(argv)
        finally:
            # Note that we mix use_arch and arch here: an Architecture: all
            # build produces foo_1.2_amd64.build, which we rename.
            # We also check for foo_amd64.build because
            # that's what comes out if we do "vectis sbuild --suite=sid hello".
            for prefix in (self.buildable.source_package,
                    self.buildable.product_prefix):
                product = '{}/out/{}_{}.build'.format(self.machine.scratch,
                        prefix, use_arch)
                product = self.machine.check_output(['readlink', '-f', product],
                        universal_newlines=True).rstrip('\n')

                if (self.machine.call(['test', '-e', product]) == 0 and
                        self.output_builds is not None):
                    logger.info('Copying %s back to host as %s_%s.build...',
                            product, self.buildable.product_prefix, self.arch)
                    copied_back = os.path.join(self.output_builds,
                            '{}_{}_{}.build'.format(self.buildable.product_prefix,
                                self.arch,
                                time.strftime('%Y%m%dt%H%M%S', time.gmtime())))
                    self.machine.copy_to_host(product, copied_back)
                    self.buildable.logs[self.arch] = copied_back

                    symlink = os.path.join(self.output_builds,
                            '{}_{}.build'.format(self.buildable.product_prefix,
                                self.arch))
                    try:
                        os.remove(symlink)
                    except FileNotFoundError:
                        pass

                    os.symlink(os.path.abspath(copied_back), symlink)
                    break
            else:
                logger.warning('Did not find build log at %s', product)
                logger.warning('Possible build logs:\n%s',
                        self.machine.check_call(['sh', '-c',
                            'cd "$1"; ls -l *.build || :',
                            'sh', # argv[0]
                            self.machine.scratch]))

        if self.arch == 'source' and self.buildable.source_from_archive:
            dscs = self.machine.check_output(['sh', '-c',
                'exec ls "$1"/*.dsc',
                'sh', # argv[0]
                self.machine.scratch], universal_newlines=True)

            dscs = dscs.splitlines()
            if len(dscs) != 1:
                raise CannotHappen('sbuild --source produced more than one '
                        '.dsc file from {!r}'.format(self.buildable))

            product = dscs[0]

            with TemporaryDirectory() as tmp:
                copied_back = os.path.join(tmp,
                        '{}.dsc'.format(self.buildable.buildable))
                self.machine.copy_to_host(product, copied_back)

                self.buildable.dsc = Dsc(open(copied_back))
                self.buildable.source_package = self.buildable.dsc['source']
                self.buildable.version = Version(self.buildable.dsc['version'])
                self.buildable.arch_wildcards = set(
                        self.buildable.dsc['architecture'].split())
                self.buildable.binary_packages = [p.strip()
                        for p in self.buildable.dsc['binary'].split(',')]

        if self.output_builds is None:
            return

        product = '{}/out/{}_{}.changes'.format(self.machine.scratch,
            self.buildable.product_prefix,
            self.arch)

        logger.info('Copying %s back to host...', product)
        copied_back = os.path.join(self.output_builds,
                '{}_{}.changes'.format(self.buildable.product_prefix,
                    self.arch))
        self.machine.copy_to_host(product, copied_back)
        self.buildable.changes_produced[self.arch] = copied_back

        changes_out = Changes(open(copied_back))

        if self.arch == 'source':
            self.buildable.dsc_name = None
            self.buildable.sourceful_changes_name = copied_back

            for f in changes_out['files']:
                if f['name'].endswith('.dsc'):
                    # expect to find exactly one .dsc file
                    assert self.buildable.dsc_name is None
                    self.buildable.dsc_name = os.path.join(self.output_builds,
                            f['name'])

            assert self.buildable.dsc_name is not None
            # Save some space
            self.machine.check_call(['rm', '-fr',
                    '{}/in/{}_source/'.format(self.machine.scratch,
                        self.buildable.product_prefix)])

        for f in changes_out['files']:
            assert '/' not in f['name']
            assert not f['name'].startswith('.')

            logger.info('Additionally copying %s back to host...',
                    f['name'])
            product = '{}/out/{}'.format(self.machine.scratch, f['name'])
            copied_back = os.path.join(self.output_builds, f['name'])
            self.machine.copy_to_host(product, copied_back)

def _run(args, machine):
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
        'schroot',
        ])

    for buildable in buildables:
        logger.info('Processing: %s', buildable)

        buildable.copy_source_to(machine)

        buildable.select_suite(args.suite)

        if buildable.suite == 'UNRELEASED':
            suite = args.vendor.get_suite(args.vendor.unstable_suite)
        else:
            suite = args.vendor.get_suite(buildable.suite)

        if args._rebuild_source or buildable.dsc is None:
            build = Build(buildable, 'source', machine,
                    output_builds=args.output_builds)
            build.build(suite, args)
        elif buildable.source_from_archive:
            # We need to get some information from the .dsc, which we do by
            # building one and throwing it away.
            build = Build(buildable, 'source', machine, output_builds=None)
            build.build(suite, args)

        if not args._source_only:
            buildable.select_archs(machine.dpkg_architecture, args._archs,
                    args._indep, args.sbuild_together)

            for arch in buildable.archs:
                build = Build(buildable, arch, machine,
                        output_builds=args.output_builds)
                build.build(suite, args)

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
                    reprepro_suite = buildable.nominal_suite

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
        _run(args, machine)
