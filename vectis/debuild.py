# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import glob
import logging
import os
import subprocess
import textwrap
import time
from collections import (
        OrderedDict,
        )
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

from vectis.error import (
        ArgumentError,
        CannotHappen,
        )
from vectis.util import (
        AtomicWriter,
        )

logger = logging.getLogger(__name__)

class Buildable:
    def __init__(self, buildable, *, vendor):
        self.buildable = buildable

        self._product_prefix = None
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
        self.source_from_archive = False
        self.source_package = None
        self.sourceful_changes_name = None
        self.suite = None
        self.together_with = None
        self.vendor = vendor
        self._version = None

        if os.path.exists(self.buildable):
            if os.path.isdir(self.buildable):
                changelog = os.path.join(self.buildable, 'debian', 'changelog')
                changelog = Changelog(open(changelog))
                self.source_package = changelog.get_package()
                self.nominal_suite = changelog.distributions
                self._version = Version(changelog.version)
                control = os.path.join(self.buildable, 'debian', 'control')

                if len(changelog.distributions.split()) != 1:
                    raise ArgumentError('Cannot build for multiple '
                            'distributions at once')

                for paragraph in Deb822.iter_paragraphs(open(control)):
                    self.arch_wildcards |= set(
                            paragraph.get('architecture', '').split())
                    binary = paragraph.get('package')

                if binary is not None:
                    self.binary_packages.append(binary)

            elif self.buildable.endswith('.changes'):
                self.dirname = os.path.dirname(self.buildable)
                self.sourceful_changes_name = self.buildable
                sourceful_changes = Changes(open(self.buildable))
                if 'source' not in sourceful_changes['architecture']:
                    raise ArgumentError('Changes file {!r} must be '
                            'sourceful'.format(self.buildable))

                self.nominal_suite = sourceful_changes['distribution']

                for f in sourceful_changes['files']:
                    if f['name'].endswith('.dsc'):
                        if self.dsc_name is not None:
                            raise ArgumentError('Changes file {!r} contained '
                                    'more than one .dsc '
                                    'file'.format(self.buildable))

                        self.dsc_name = os.path.join(self.dirname, f['name'])

                if self.dsc_name is None:
                    raise ArgumentError('Changes file {!r} did not contain a '
                            '.dsc file'.format(self.buildable))

                self.dsc = Dsc(open(self.dsc_name))

            elif self.buildable.endswith('.dsc'):
                self.dirname = os.path.dirname(self.buildable)
                self.dsc_name = self.buildable
                self.dsc = Dsc(open(self.dsc_name))

            else:
                raise ArgumentError('buildable must be .changes, .dsc or '
                        'directory, not {!r}'.format(self.buildable))
        else:
            self.source_from_archive = True

            if '_' in self.buildable:
                source, version = self.buildable.split('_', 1)
            else:
                source = self.buildable
                version = None

            self.source_package = source
            if version is not None:
                self._version = Version(version)

        if self.dsc is not None:
            self.source_package = self.dsc['source']
            self._version = Version(self.dsc['version'])
            self.arch_wildcards = set(self.dsc['architecture'].split())
            self.binary_packages = [p.strip()
                    for p in self.dsc['binary'].split(',')]

    @property
    def product_prefix(self):
        if self._product_prefix is None:
            version_no_epoch = Version(self.version)
            version_no_epoch.epoch = None
            self._product_prefix = '{}_{}'.format(self.source_package,
                    version_no_epoch)

        return self._product_prefix

    @property
    def version(self):
        return self._version

    @version.setter
    def version(self, v):
        self._version = v
        self._product_prefix = None

    def copy_source_to(self, worker):
        worker.check_call(['mkdir', '-p', '-m755',
            '{}/in'.format(worker.scratch)])

        if self.dsc_name is not None:
            assert self.dsc is not None

            worker.copy_to_guest(self.dsc_name,
                    '{}/in/{}'.format(worker.scratch,
                        os.path.basename(self.dsc_name)))

            for f in self.dsc['files']:
                worker.copy_to_guest(os.path.join(self.dirname, f['name']),
                        '{}/in/{}'.format(worker.scratch, f['name']))
        elif not self.source_from_archive:
            worker.copy_to_guest(os.path.join(self.buildable, ''),
                    '{}/in/{}_source/'.format(worker.scratch,
                        self.product_prefix))
            worker.check_call(['chown', '-R', 'sbuild:sbuild',
                    '{}/in/'.format(worker.scratch)])
            if self._version.debian_revision is not None:
                worker.check_call(['install', '-d', '-m755',
                    '-osbuild', '-gsbuild',
                    '{}/out'.format(worker.scratch)])

                orig_pattern = glob.escape(os.path.join(self.buildable, '..',
                        '{}_{}.orig.tar.'.format(self.source_package,
                            self._version.upstream_version))) + '*'
                logger.info('Looking for original tarballs: {}'.format(
                        orig_pattern))

                for orig in glob.glob(orig_pattern):
                    logger.info('Copying original tarball: {}'.format(orig))
                    worker.copy_to_guest(orig,
                            '{}/in/{}'.format(worker.scratch,
                                os.path.basename(orig)))
                    worker.check_call(['ln', '-s',
                            '{}/in/{}'.format(worker.scratch,
                                os.path.basename(orig)),
                            '{}/out/{}'.format(worker.scratch,
                                os.path.basename(orig))])

    def select_archs(self, worker_arch, archs, indep, together):
        builds_i386 = False
        builds_natively = False

        for wildcard in self.arch_wildcards:
            if subprocess.call(['dpkg-architecture',
                    '-a' + worker_arch, '--is', wildcard]) == 0:
                logger.info('Package builds natively on %s', worker_arch)
                builds_natively = True

            if subprocess.call(['dpkg-architecture',
                    '-ai386', '--is', wildcard]) == 0:
                logger.info('Package builds on i386')
                builds_i386 = True

        if archs or indep:
            # the user is always right
            logger.info('Using architectures from command-line')
            self.archs = archs[:]
        else:
            logger.info('Choosing architectures to build')
            indep = ('all' in self.arch_wildcards)
            self.archs = []

            if builds_natively:
                self.archs.append(worker_arch)

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

            if (worker_arch == 'amd64' and builds_i386 and
                    not builds_natively and 'i386' not in self.archs):
                self.archs.append('i386')

        if 'all' not in self.arch_wildcards:
            indep = False

        if indep:
            if together and self.archs:
                if worker_arch in self.archs:
                    self.together_with = worker_arch
                else:
                    self.together_with = self.archs[0]
            else:
                self.archs.insert(0, 'all')

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
            raise ArgumentError('Must specify --suite when building from '
                    '{!r}'.format(self.buildable))

    def __str__(self):
        return self.buildable

class Build:
    def __init__(self, buildable, arch, worker, *,
            dpkg_buildpackage_options,
            dpkg_source_options,
            output_builds,
            storage,
            suite,
            components=(),
            extra_repositories=()):
        self.arch = arch
        self.buildable = buildable
        self.components = components
        self.dpkg_buildpackage_options = dpkg_buildpackage_options
        self.dpkg_source_options = dpkg_source_options
        self.extra_repositories = extra_repositories
        self.worker = worker
        self.output_builds = output_builds
        self.storage = storage
        self.suite = suite

    def sbuild(self):
        self.worker.check_call(['install', '-d', '-m755',
            '-osbuild', '-gsbuild',
            '{}/out'.format(self.worker.scratch)])

        logger.info('Building architecture: %s', self.arch)

        if self.arch in ('all', 'source'):
            logger.info('(on %s)', self.worker.dpkg_architecture)
            use_arch = self.worker.dpkg_architecture
        else:
            use_arch = self.arch

        hierarchy = self.suite.hierarchy

        sbuild_tarball = (
                'sbuild-{vendor}-{base}-{arch}.tar.gz'.format(
                    arch=use_arch,
                    vendor=self.buildable.vendor,
                    base=hierarchy[-1],
                    ))

        self.worker.copy_to_guest(os.path.join(self.storage,
                    sbuild_tarball),
                '{}/in/{}'.format(self.worker.scratch, sbuild_tarball),
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
                    scratch=self.worker.scratch))
            self.worker.copy_to_guest(os.path.join(tmp, 'sbuild.conf'),
                    '/etc/schroot/chroot.d/{}'.format(chroot))

        argv = [
                self.worker.command_wrapper,
                '--chdir',
                '{}/out'.format(self.worker.scratch),
                '--',
                'runuser',
                '-u', 'sbuild',
                '--',
                'sbuild',
                '-c', chroot,
                '-d', str(self.buildable.nominal_suite),
                '--no-run-lintian',
        ]

        for x in self.dpkg_buildpackage_options:
            argv.append('--debbuildopt=' + x)

        for x in self.dpkg_source_options:
            argv.append('--dpkg-source-opt=' + x)

        for child in hierarchy[:-1]:
            argv.append('--extra-repository')
            argv.append('deb {} {} {}'.format(
                child.mirror,
                child.apt_suite,
                ' '.join(set(self.components or child.components) &
                    child.all_components)))

            if child.sbuild_resolver:
                argv.extend(child.sbuild_resolver)

        for x in self.extra_repositories:
            argv.append('--extra-repository')
            argv.append(x)

        if self.arch == 'all':
            logger.info('Architecture: all')
            argv.append('-A')

            # Backwards compatibility goo for Debian jessie buildd backport
            if self.worker.call(['sh', '-c',
                    'dpkg --compare-versions ' +
                    '"$(dpkg-query -W -f\'${Version}\' sbuild)"' +
                    ' lt 0.69.0']) == 0:
                argv.append('--arch-all-only')
            else:
                argv.append('--no-arch-any')
        elif self.arch == self.buildable.together_with:
            logger.info('Architecture: %s + all', self.arch)
            argv.append('-A')
            argv.append('--arch')
            argv.append(self.arch)
        elif self.arch == 'source':
            logger.info('Source-only')

            # Backwards compatibility goo for Debian jessie buildd backport
            if self.worker.call(['sh', '-c',
                    'dpkg --compare-versions ' +
                    '"$(dpkg-query -W -f\'${Version}\' sbuild)"' +
                    ' lt 0.69.0']) == 0:
                # If we only build 'all', and we don't build 'all',
                # then logically we build nothing (except source).
                argv.append('--arch-all-only')
                argv.append('--no-arch-all')
                # Urgh. This sbuild expects to find foo_1_amd64.changes
                # even for a source-only build (because it doesn't really
                # support source-only builds), so we have to cheat.
                # sbuild splits the command on spaces so we need to have
                # a one-liner that doesn't contain embedded whitespace.
                # Luckily, Perl can be written as line-noise.
                argv.append('--finished-build-commands=perl -e ' +
                        '$arch=qx(dpkg\\x20--print-architecture);' +
                        'chomp($arch);' +
                        'chdir(shift);' +
                        'foreach(glob("../*_source.changes")){' +
                             '$orig=$_;' +
                             's/_source\\.changes$/_${arch}.changes/;' +
                             'print("Renaming\\x20$orig\\x20to\\x20$_\\n");' +
                             'rename($orig,$_)||die("$!");' +
                        '}' +
                        ' %p')
            else:
                argv.append('--no-arch-any')

            argv.append('--source')
        else:
            logger.info('Architecture: %s only', self.arch)
            argv.append('--arch')
            argv.append(self.arch)

        if self.buildable.dsc_name is not None:
            if 'source' in self.buildable.changes_produced:
                argv.append('{}/out/{}'.format(self.worker.scratch,
                    os.path.basename(self.buildable.dsc_name)))
            else:
                argv.append('{}/in/{}'.format(self.worker.scratch,
                    os.path.basename(self.buildable.dsc_name)))
        elif self.buildable.source_from_archive:
            argv.append(self.buildable.buildable)
        else:
            # build a source package as a side-effect of the first build
            # (in practice this will be the 'source' build)
            argv.append('--no-clean-source')
            argv.append('--source')
            argv.append('{}/in/{}_source'.format(self.worker.scratch,
                self.buildable.product_prefix))

        logger.info('Running %r', argv)
        try:
            self.worker.check_call(argv)
        finally:
            # Note that we mix use_arch and arch here: an Architecture: all
            # build produces foo_1.2_amd64.build, which we rename.
            # We also check for foo_amd64.build because
            # that's what comes out if we do "vectis sbuild --suite=sid hello".
            for prefix in (self.buildable.source_package,
                    self.buildable.product_prefix):
                product = '{}/out/{}_{}.build'.format(self.worker.scratch,
                        prefix, use_arch)
                product = self.worker.check_output(['readlink', '-f', product],
                        universal_newlines=True).rstrip('\n')

                if (self.worker.call(['test', '-e', product]) == 0 and
                        self.output_builds is not None):
                    logger.info('Copying %s back to host as %s_%s.build...',
                            product, self.buildable.product_prefix, self.arch)
                    copied_back = os.path.join(self.output_builds,
                            '{}_{}_{}.build'.format(self.buildable.product_prefix,
                                self.arch,
                                time.strftime('%Y%m%dt%H%M%S', time.gmtime())))
                    self.worker.copy_to_host(product, copied_back)
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
                        self.worker.check_call(['sh', '-c',
                            'cd "$1"; ls -l *.build || :',
                            'sh', # argv[0]
                            self.worker.scratch]))

        if self.arch == 'source' and self.buildable.source_from_archive:
            dscs = self.worker.check_output(['sh', '-c',
                'exec ls "$1"/out/*.dsc',
                'sh', # argv[0]
                self.worker.scratch], universal_newlines=True)

            dscs = dscs.splitlines()
            if len(dscs) != 1:
                raise CannotHappen('sbuild --source produced more than one '
                        '.dsc file from {!r}'.format(self.buildable))

            product = dscs[0]

            with TemporaryDirectory() as tmp:
                copied_back = os.path.join(tmp,
                        '{}.dsc'.format(self.buildable.buildable))
                self.worker.copy_to_host(product, copied_back)

                self.buildable.dsc = Dsc(open(copied_back))
                self.buildable.source_package = self.buildable.dsc['source']
                self.buildable.version = Version(self.buildable.dsc['version'])
                self.buildable.arch_wildcards = set(
                        self.buildable.dsc['architecture'].split())
                self.buildable.binary_packages = [p.strip()
                        for p in self.buildable.dsc['binary'].split(',')]

        if self.output_builds is None:
            return

        for product_arch in (self.arch, self.worker.dpkg_architecture):
            product = '{}/out/{}_{}.changes'.format(self.worker.scratch,
                self.buildable.product_prefix,
                product_arch)
            if self.worker.call(['test', '-e', product]) == 0:
                break
        else:
            raise CannotHappen('sbuild produced no .changes file from '
                    '{!r}'.format(self.buildable))

        logger.info('Copying %s back to host...', product)
        copied_back = os.path.join(self.output_builds,
                '{}_{}.changes'.format(self.buildable.product_prefix,
                    self.arch))
        self.worker.copy_to_host(product, copied_back)
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
            self.worker.check_call(['rm', '-fr',
                    '{}/in/{}_source/'.format(self.worker.scratch,
                        self.buildable.product_prefix)])

        for f in changes_out['files']:
            assert '/' not in f['name']
            assert not f['name'].startswith('.')

            logger.info('Additionally copying %s back to host...',
                    f['name'])
            product = '{}/out/{}'.format(self.worker.scratch, f['name'])
            copied_back = os.path.join(self.output_builds, f['name'])
            self.worker.copy_to_host(product, copied_back)
