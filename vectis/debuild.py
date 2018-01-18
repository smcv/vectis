# Copyright © 2016-2017 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import glob
import logging
import os
import subprocess
import time
from collections import (
    OrderedDict,
)
from contextlib import suppress
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

from vectis.config import (
    Suite,
)
from vectis.error import (
    ArgumentError,
    CannotHappen,
)
from vectis.worker import (
    SchrootWorker,
)

logger = logging.getLogger(__name__)


class Buildable:

    def __init__(
            self,
            buildable,
            *,
            binary_version_suffix='',
            link_builds=(),
            orig_dirs=('..',),
            output_dir=None,
            output_parent,
            vendor):
        self.buildable = buildable

        self._product_prefix = None
        self._source_version = None
        self._binary_version = None
        self.arch_wildcards = set()
        self.archs = []
        self.autopkgtest_failures = []
        self.binary_packages = []
        self.binary_version_suffix = binary_version_suffix
        self.changes_produced = {}
        self.dirname = None
        self.dsc = None
        self.dsc_name = None
        self.indep = False
        self.indep_together_with = None
        self.link_builds = link_builds
        self.logs = {}
        self.merged_changes = OrderedDict()
        self.nominal_suite = None
        self.orig_dirs = orig_dirs
        self.output_dir = output_dir
        self.piuparts_failures = []
        self.source_from_archive = False
        self.source_package = None
        self.source_together_with = None
        self.sourceful_changes_name = None
        self.suite = None
        self.vendor = vendor

        if os.path.exists(self.buildable):
            if os.path.isdir(self.buildable):
                changelog = os.path.join(self.buildable, 'debian', 'changelog')
                changelog = Changelog(open(changelog))
                self.source_package = changelog.get_package()
                self.nominal_suite = changelog.distributions
                self._source_version = Version(changelog.version)
                control = os.path.join(self.buildable, 'debian', 'control')

                if len(changelog.distributions.split()) != 1:
                    raise ArgumentError(
                        'Cannot build for multiple distributions at once')

                for paragraph in Deb822.iter_paragraphs(open(control)):
                    self.arch_wildcards |= set(
                        paragraph.get('architecture', '').split())
                    binary = paragraph.get('package')

                    if binary is not None:
                        self.binary_packages.append(binary)

            elif self.buildable.endswith('.changes'):
                self.dirname = os.path.dirname(self.buildable) or os.curdir
                self.sourceful_changes_name = self.buildable
                sourceful_changes = Changes(open(self.buildable))
                if 'source' not in sourceful_changes['architecture'].split():
                    raise ArgumentError(
                        'Changes file {!r} must be sourceful'.format(
                            self.buildable))

                self.nominal_suite = sourceful_changes['distribution']

                for f in sourceful_changes['files']:
                    if f['name'].endswith('.dsc'):
                        if self.dsc_name is not None:
                            raise ArgumentError(
                                'Changes file {!r} contained more than one '
                                '.dsc file'.format(self.buildable))

                        self.dsc_name = os.path.join(self.dirname, f['name'])

                if self.dsc_name is None:
                    raise ArgumentError(
                        'Changes file {!r} did not contain a .dsc file'.format(
                            self.buildable))

                self.dsc = Dsc(open(self.dsc_name))

            elif self.buildable.endswith('.dsc'):
                self.dirname = os.path.dirname(self.buildable) or os.curdir
                self.dsc_name = self.buildable
                self.dsc = Dsc(open(self.dsc_name))

            else:
                raise ArgumentError(
                    'buildable must be .changes, .dsc or directory, not '
                    '{!r}'.format(self.buildable))
        else:
            self.source_from_archive = True

            if '_' in self.buildable:
                source, version = self.buildable.split('_', 1)
            else:
                source = self.buildable
                version = None

            self.source_package = source
            if version is not None:
                self._source_version = Version(version)

        if self.dsc is not None:
            self.source_package = self.dsc['source']
            self._source_version = Version(self.dsc['version'])
            self.arch_wildcards = set(self.dsc['architecture'].split())
            self.binary_packages = [p.strip()
                                    for p in self.dsc['binary'].split(',')]

        if self._source_version is not None:
            self._binary_version = Version(
                str(self._source_version) + self.binary_version_suffix)

        timestamp = time.strftime('%Y%m%dt%H%M%S', time.gmtime())

        if self.output_dir is None:
            if self._binary_version is None:
                dirname = '{}_{}'.format(self.source_package, timestamp)
            else:
                dirname = '{}_{}_{}'.format(
                    self.source_package,
                    self._binary_version,
                    timestamp)

            self.output_dir = os.path.join(output_parent, dirname)

            # For convenience, create a symbolic link for the latest build of
            # each source package: hello_latest -> hello_2.10-1_20170319t102623
            unversioned_symlink = os.path.join(
                output_parent, self.source_package + '_latest')

            with suppress(FileNotFoundError):
                os.unlink(unversioned_symlink)

            os.symlink(dirname, unversioned_symlink)

            # If we know the version, also create a symbolic link for the
            # latest build of each source/version pair:
            # hello_2.10-1 -> hello_2.10-1_20170319t102623
            if self._binary_version is not None:
                versioned_symlink = os.path.join(
                    output_parent,
                    '{}_{}'.format(self.source_package, self._binary_version))

                with suppress(FileNotFoundError):
                    os.unlink(versioned_symlink)

                os.symlink(dirname, versioned_symlink)

        # It's OK if the output directory exists but is empty.
        with suppress(FileNotFoundError):
            os.rmdir(self.output_dir)

        # Otherwise, if someone already created this, we'll just crash out.
        os.mkdir(self.output_dir)

        if self.dsc is not None:
            abs_file = os.path.abspath(self.dsc_name)
            abs_dir, base = os.path.split(abs_file)
            os.symlink(abs_file, os.path.join(self.output_dir, base))

            for l in self.link_builds:
                symlink = os.path.join(l, base)

                with suppress(FileNotFoundError):
                    os.unlink(symlink)

                os.symlink(abs_file, symlink)

            for f in self.dsc['files']:
                abs_file = os.path.join(abs_dir, f['name'])
                os.symlink(
                    abs_file,
                    os.path.join(self.output_dir, f['name']))

                for l in self.link_builds:
                    symlink = os.path.join(l, f['name'])

                    with suppress(FileNotFoundError):
                        os.unlink(symlink)

                    os.symlink(abs_file, symlink)

    @property
    def product_prefix(self):
        if self._product_prefix is None:
            version_no_epoch = Version(self.binary_version)
            version_no_epoch.epoch = None
            self._product_prefix = '{}_{}'.format(
                self.source_package, version_no_epoch)

        return self._product_prefix

    @property
    def binary_version(self):
        return self._binary_version

    @property
    def source_version(self):
        return self._source_version

    @source_version.setter
    def source_version(self, v):
        self._source_version = v
        self._product_prefix = None
        self._binary_version = Version(
            str(self._source_version) + self.binary_version_suffix)

    def copy_source_to(self, worker):
        worker.check_call([
            'mkdir', '-p', '-m755', '{}/in'.format(worker.scratch)])

        if self.dsc_name is not None:
            assert self.dsc is not None

            worker.copy_to_guest(
                self.dsc_name,
                '{}/in/{}'.format(
                    worker.scratch,
                    os.path.basename(self.dsc_name)))

            for f in self.dsc['files']:
                worker.copy_to_guest(
                    os.path.join(self.dirname, f['name']),
                    '{}/in/{}'.format(worker.scratch, f['name']))
        elif not self.source_from_archive:
            worker.copy_to_guest(
                os.path.join(self.buildable, ''),
                '{}/in/{}_source/'.format(
                    worker.scratch,
                    self.product_prefix))
            worker.check_call([
                'chown', '-R', 'sbuild:sbuild',
                '{}/in/'.format(worker.scratch)])
            if self._source_version.debian_revision is not None:
                worker.check_call([
                    'install', '-d', '-m755', '-osbuild', '-gsbuild',
                    '{}/out'.format(worker.scratch)])

                origs_copied = set()

                for orig_dir in self.orig_dirs:
                    orig_glob_prefix = glob.escape(
                        os.path.join(
                            self.buildable, orig_dir,
                            '{}_{}'.format(
                                self.source_package,
                                self._source_version.upstream_version)))

                    for orig_pattern in (
                            orig_glob_prefix + '.orig.tar.*',
                            orig_glob_prefix + '.orig-*.tar.*'):
                        logger.info(
                            'Looking for original tarballs: %s', orig_pattern)

                        for orig in glob.glob(orig_pattern):
                            base = os.path.basename(orig)

                            if base in origs_copied:
                                logger.info(
                                    'Already copied %s; ignoring %s', base,
                                    orig)
                                continue

                            origs_copied.add(base)
                            logger.info('Copying original tarball: %s', orig)
                            worker.copy_to_guest(
                                orig, '{}/in/{}'.format(
                                    worker.scratch, base))
                            worker.check_call([
                                'ln', '-s',
                                '{}/in/{}'.format(worker.scratch, base),
                                '{}/out/{}'.format(worker.scratch, base),
                            ])

    def select_archs(
            self,
            *,
            worker_arch,
            archs,
            indep,
            indep_together,
            build_source,
            source_only,
            source_together):
        builds_i386 = False
        builds_natively = False
        need_source = (
            build_source or (
                build_source is None and
                self.dsc_name is None and
                not self.source_from_archive)
        )

        if source_only:
            if need_source:
                self.archs = ['source']
            else:
                logger.warning('Nothing to do')
                self.archs = []

            return

        for wildcard in self.arch_wildcards:
            if subprocess.call(
                    ['dpkg-architecture', '-a' + worker_arch, '--is', wildcard]
            ) == 0:
                logger.info('Package builds natively on %s', worker_arch)
                builds_natively = True

            if subprocess.call(
                    ['dpkg-architecture', '-ai386', '--is', wildcard]
            ) == 0:
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

            for line in subprocess.check_output(
                    [
                        'sh', '-c', '"$@" || :',
                        'sh',  # argv[0]
                        'dpkg-query', '-W', r'--showformat=${binary:Package}\n',
                    ] + list(self.binary_packages),
                    universal_newlines=True).splitlines():
                if ':' in line:
                    arch = line.split(':')[-1]
                    if arch not in self.archs:
                        logger.info(
                            'Building on %s because %s is installed',
                            arch, line)
                        self.archs.append(arch)

            if (worker_arch == 'amd64' and builds_i386 and
                    not builds_natively and 'i386' not in self.archs):
                self.archs.append('i386')

        if 'all' not in self.arch_wildcards:
            indep = False

        if indep:
            if indep_together and self.archs:
                if worker_arch in self.archs:
                    self.indep_together_with = worker_arch
                else:
                    self.indep_together_with = self.archs[0]
            else:
                self.archs.append('all')

        if need_source:
            if source_together and self.archs:
                self.source_together_with = self.archs[0]
            else:
                self.archs[:0] = ['source']

        logger.info('Selected architectures: %r', self.archs)

        if need_source and self.source_together_with is not None:
            logger.info(
                'Clean source package will be built alongside %s',
                self.source_together_with)

        if indep and self.indep_together_with is not None:
            logger.info(
                'Architecture-independent packages will be built alongside %s',
                self.indep_together_with)

    def select_suite(self, factory, override):
        suite_name = override

        if suite_name is None:
            suite_name = self.nominal_suite

        if suite_name is None:
            raise ArgumentError(
                'Must specify --suite when building from {!r}'.format(
                    self.buildable))

        if isinstance(suite_name, Suite):
            self.suite = suite_name
        else:
            if suite_name == 'UNRELEASED':
                logger.info(
                    'Replacing UNRELEASED with %s', self.vendor.default_suite)
                suite_name = self.vendor.default_suite

            if suite_name.endswith('-UNRELEASED'):
                suite_name = suite_name[:-len('-UNRELEASED')]
                logger.info(
                    'Replacing %s-UNRELEASED with %s', suite_name, suite_name)

            self.suite = factory.get_suite(self.vendor, suite_name)

        if self.nominal_suite is None:
            self.nominal_suite = str(self.suite)

    def __str__(self):
        return self.buildable

    def get_debs(self, architecture):
        ret = set()

        for k, v in self.merged_changes.items():
            changes = Changes(open(v))

            for f in changes['files']:
                if (f['name'].endswith('_{}.deb'.format(architecture)) or
                        f['name'].endswith('_all.deb')):
                    assert '/' not in f['name']
                    ret.add(
                        os.path.join(
                            os.path.dirname(v) or os.curdir,
                            f['name'],
                        ),
                    )

        return sorted(ret)

    def check_build_product(self, base):
        """
        Check whether base is a safe filename to copy back to the host.
        If we don't trust the build system, we don't want to create symbolic
        links with arbitrary names under its control.
        """

        if os.path.basename(base) != base:
            raise ArgumentError('Contains a path separator')

        if base.startswith('.'):
            raise ArgumentError('Is a hidden file')

        if base.endswith(('.deb', '.udeb')):
            return

        if not base.startswith(self.source_package + '_'):
            raise ArgumentError('Unexpected prefix')

        if base.endswith(('.changes', '.dsc', '.buildinfo', '.diff.gz')):
            return

        if base.startswith(self.source_package + '_') and '.tar.' in base:
            return

        raise ArgumentError('Unexpected filename')


class Build:

    def __init__(
            self,
            buildable,
            arch,
            worker,
            *,
            mirrors,
            output_dir,
            profiles,
            storage,
            deb_build_options=(),
            dpkg_buildpackage_options=(),
            dpkg_source_options=(),
            environ=None,
            components=(),
            extra_repositories=()):
        self.arch = arch
        self.buildable = buildable
        self.components = components
        self.dpkg_buildpackage_options = dpkg_buildpackage_options
        self.dpkg_source_options = dpkg_source_options
        self.environ = {}
        self.extra_repositories = extra_repositories
        assert not isinstance(profiles, str), profiles
        self.mirrors = mirrors
        self.output_dir = output_dir
        self.profiles = set(profiles)
        self.storage = storage
        self.worker = worker

        if environ is not None:
            for k, v in environ.items():
                self.environ[k] = v

        self.environ['DEB_BUILD_OPTIONS'] = ' '.join(deb_build_options)

    def sbuild(self, *, sbuild_options=()):
        self.worker.check_call([
            'install', '-d', '-m755', '-osbuild', '-gsbuild',
            '{}/out'.format(self.worker.scratch)])

        logger.info('Building architecture: %s', self.arch)

        if self.arch in ('all', 'source'):
            logger.info('(on %s)', self.worker.dpkg_architecture)
            use_arch = self.worker.dpkg_architecture
        else:
            use_arch = self.arch

        with SchrootWorker(
            storage=self.storage,
            architecture=use_arch,
            chroot='{}-{}-sbuild'.format(self.buildable.suite, use_arch),
            components=self.components,
            extra_repositories=self.extra_repositories,
            mirrors=self.mirrors,
            suite=self.buildable.suite,
            worker=self.worker,
        ) as chroot:
            self._sbuild(chroot, sbuild_options)

    def _sbuild(self, chroot, sbuild_options=()):
        sbuild_version = self.worker.dpkg_version('sbuild')

        # Backwards compatibility goo for Debian jessie buildd backport:
        # it can't do "sbuild hello", only "sbuild hello_2.10-1".
        if (self.buildable.source_from_archive and
                self.buildable.source_version is None and
                sbuild_version < Version('0.69.0')):
            lines = chroot.check_output(
                [
                    'sh', '-c',
                    'apt-get update >&2 && '
                    '( apt-cache showsrc --only-source "$1" || '
                    '  apt-cache showsrc "$1" ) | '
                    'sed -ne "s/^Version: *//p"',
                    'sh',  # argv[0]
                    self.buildable.source_package,
                ],
                universal_newlines=True).strip().splitlines()
            self.buildable.source_version = sorted(map(Version, lines))[-1]
            self.buildable.buildable = '{}_{}'.format(
                self.buildable.source_package,
                self.buildable.source_version,
            )

        argv = [
            self.worker.command_wrapper,
            '--chdir',
            '{}/out'.format(self.worker.scratch),
            '--',
            'runuser',
            '-u', 'sbuild',
            '--',
            'env',
        ]

        for k, v in sorted(self.environ.items()):
            argv.append('{}={}'.format(k, v))

        argv.extend((
            'sbuild',
            '-c', chroot.chroot,
            '-d', str(self.buildable.nominal_suite),
            '--no-run-lintian',
        ))

        if self.profiles:
            argv.append('--profiles={}'.format(','.join(self.profiles)))

        for x in self.dpkg_buildpackage_options:
            argv.append('--debbuildopt=' + x)

        for child in chroot.suite.hierarchy[:-1]:
            # The schroot already has the apt sources, we just need the
            # resolver
            if child.sbuild_resolver:
                argv.extend(child.sbuild_resolver)
                break

        if self.arch == 'all':
            logger.info('Architecture: all')
            argv.append('-A')

            # Backwards compatibility goo for Debian jessie buildd backport
            if sbuild_version < Version('0.69.0'):
                argv.append('--arch-all-only')
            else:
                argv.append('--no-arch-any')
        elif self.arch == self.buildable.indep_together_with:
            logger.info('Architecture: %s + all', self.arch)
            argv.append('-A')
            argv.append('--arch')
            argv.append(self.arch)
        elif self.arch == 'source':
            logger.info('Source-only')
            argv.append('--no-arch-any')

            if sbuild_version < Version('0.69.0'):
                # Backwards compatibility for Debian jessie buildd backport,
                # and for sbuild in Ubuntu xenial.

                # sbuild < 0.69.0 expects to find foo_1_amd64.changes
                # even for a source-only build (because it doesn't really
                # support source-only builds), so we have to cheat.
                perl = (
                    "'" +
                    '$arch = qx(dpkg\\x20--print-architecture);\n' +
                    'chomp($arch);\n' +
                    'chdir(shift);\n' +
                    'foreach(glob("../*_source.changes")) {\n' +
                    '    $orig = $_;\n' +
                    '    s/_source\\.changes$/_${arch}.changes/;\n' +
                    '    print("Renaming\\x20$orig\\x20to\\x20$_\\n");\n' +
                    '    rename($orig,$_) || die("$!");\n' +
                    '}\n' +
                    "'")

                argv.append(
                    '--finished-build-commands=perl -e {} %p'.format(perl))

        else:
            logger.info('Architecture: %s only', self.arch)
            argv.append('--arch')
            argv.append(self.arch)

        if self.arch in ('source', self.buildable.source_together_with):
            # Build a clean source package as a side-effect of one
            # build.
            argv.append('--source')

            for x in self.dpkg_source_options:
                argv.append('--debbuildopt=--source-option={}'.format(x))

        if self.buildable.binary_version_suffix:
            argv.append('--append-to-version={}'.format(
                self.buildable.binary_version_suffix))

        for x in sbuild_options:
            argv.append(x)

        if self.buildable.dsc_name is not None:
            if 'source' in self.buildable.changes_produced:
                # We rebuilt the source already. Use the rebuilt version
                # for all subsequent builds.
                argv.append('{}/out/{}'.format(
                    self.worker.scratch,
                    os.path.basename(self.buildable.dsc_name)))
            else:
                # We got a .dsc from outside Vectis and are not
                # rebuilding it.
                argv.append('{}/in/{}'.format(
                    self.worker.scratch,
                    os.path.basename(self.buildable.dsc_name)))
        elif self.buildable.source_from_archive:
            argv.append(self.buildable.buildable)
        else:
            # jessie sbuild doesn't support --no-clean-source so build
            # the temporary source package ourselves.
            ds_argv = [
                self.worker.command_wrapper,
                '--chdir',
                '{}/in/{}_source'.format(
                    self.worker.scratch, self.buildable.product_prefix),
                '--',
                'dpkg-source',
            ]

            for x in self.dpkg_source_options:
                ds_argv.append(x)

            ds_argv.extend(('-b', '.'))
            self.worker.check_call(ds_argv)
            argv.append('{}/in/{}.dsc'.format(
                self.worker.scratch, self.buildable.product_prefix))

        logger.info('Running %r', argv)
        try:
            self.worker.check_call(argv)
        finally:
            # Note that we mix chroot.dpkg_architecture and arch here: an
            # Architecture: all build produces foo_1.2_amd64.build, which we
            # rename.
            # We also check for foo_amd64.build because
            # that's what comes out if we do "vectis sbuild --suite=sid hello".
            for prefix in (self.buildable.source_package,
                           self.buildable.product_prefix):
                product = '{}/out/{}_{}.build'.format(
                    self.worker.scratch, prefix, chroot.dpkg_architecture)
                product = self.worker.check_output(
                    ['readlink', '-f', product],
                    universal_newlines=True).rstrip('\n')

                if (self.worker.call(['test', '-e', product]) == 0 and
                        self.output_dir is not None):
                    logger.info('Copying %s back to host as %s_%s.build...',
                                product, self.buildable.product_prefix, self.arch)
                    copied_back = os.path.join(
                        self.output_dir,
                        '{}_{}_{}.build'.format(
                            self.buildable.product_prefix, self.arch,
                            time.strftime('%Y%m%dt%H%M%S', time.gmtime())))
                    self.worker.copy_to_host(product, copied_back)
                    self.buildable.logs[self.arch] = copied_back

                    symlink = os.path.join(
                        self.output_dir,
                        '{}_{}.build'.format(
                            self.buildable.product_prefix, self.arch))
                    try:
                        os.remove(symlink)
                    except FileNotFoundError:
                        pass

                    os.symlink(os.path.abspath(copied_back), symlink)
                    break
            else:
                logger.warning('Did not find build log at %s', product)
                logger.warning(
                    'Possible build logs:\n%s',
                    self.worker.check_call([
                        'sh', '-c',
                        'cd "$1"; ls -l *.build || :',
                        'sh',  # argv[0]
                        self.worker.scratch]))

        if self.arch == 'source' and self.buildable.source_from_archive:
            dscs = self.worker.check_output([
                'sh', '-c', 'exec ls "$1"/out/*.dsc', 'sh',  # argv[0]
                self.worker.scratch], universal_newlines=True)

            dscs = dscs.splitlines()
            if len(dscs) != 1:
                raise CannotHappen('sbuild --source produced more than one '
                                   '.dsc file from {!r}'.format(self.buildable))

            product = dscs[0]

            with TemporaryDirectory(prefix='vectis-sbuild-') as tmp:
                copied_back = os.path.join(
                    tmp, '{}.dsc'.format(self.buildable.buildable))
                self.worker.copy_to_host(product, copied_back)

                self.buildable.dsc = Dsc(open(copied_back))
                self.buildable.source_package = self.buildable.dsc['source']
                self.buildable.source_version = Version(self.buildable.dsc['version'])
                self.buildable.arch_wildcards = set(
                    self.buildable.dsc['architecture'].split())
                self.buildable.binary_packages = [
                    p.strip() for p in self.buildable.dsc['binary'].split(',')]

        if self.arch == 'source' and self.output_dir is not None:
            # Make sure the orig.tar.* are in the out directory, because
            # we will be building from the rebuilt source in future
            self.worker.check_call([
                'sh', '-c',
                'ln -nsf "$1"/in/*.orig.tar.* "$1"/out/',
                'sh',  # argv[0]
                self.worker.scratch])

        if self.output_dir is None:
            return

        product_arch = None

        for candidate in (self.arch, self.worker.dpkg_architecture):
            product = '{}/out/{}_{}.changes'.format(
                self.worker.scratch, self.buildable.product_prefix,
                candidate)
            if self.worker.call(['test', '-e', product]) == 0:
                product_arch = candidate
                break
        else:
            raise CannotHappen(
                'sbuild produced no .changes file from {!r}'.format(
                    self.buildable))

        copied_back = self.copy_back_product(
            '{}_{}.changes'.format(
                self.buildable.product_prefix,
                product_arch),
            '{}_{}.changes'.format(
                self.buildable.product_prefix,
                self.arch))

        if copied_back is not None:
            self.buildable.changes_produced[self.arch] = copied_back

            changes_out = Changes(open(copied_back))

            if 'source' in changes_out['architecture'].split():
                self.buildable.dsc_name = None
                self.buildable.sourceful_changes_name = copied_back

                for f in changes_out['files']:
                    if f['name'].endswith('.dsc'):
                        # expect to find exactly one .dsc file
                        assert self.buildable.dsc_name is None
                        self.buildable.dsc_name = os.path.join(
                            self.output_dir, f['name'])

                assert self.buildable.dsc_name is not None
                # Save some space
                self.worker.check_call(['rm', '-fr', '{}/in/{}_source/'.format(
                    self.worker.scratch,
                    self.buildable.product_prefix)])

            dsc = None

            for f in changes_out['files']:
                copied_back = self.copy_back_product(f['name'])

                if copied_back is not None and f['name'].endswith('.dsc'):
                    dsc = Dsc(open(copied_back))

            if dsc is not None:
                if self.buildable.dsc is None:
                    self.buildable.dsc = dsc

                for f in dsc['files']:
                    # The orig.tar.* might not have come back. Copy that too,
                    # if necessary.
                    self.copy_back_product(f['name'], skip_if_exists=True)

    def copy_back_product(self, base, to_base=None, *, skip_if_exists=False):
        if to_base is None:
            to_base = base

        try:
            self.buildable.check_build_product(base)
        except ArgumentError as e:
            logger.warning('Unexpected build product %r: %s', base, e)
            return None
        else:
            product = '{}/out/{}'.format(self.worker.scratch, base)
            copied_back = os.path.join(self.output_dir, to_base)
            copied_back = os.path.abspath(copied_back)

            if skip_if_exists and os.path.exists(copied_back):
                return copied_back

            if to_base != base:
                logger.info(
                    'Additionally copying %s back to host as %s...',
                    base, to_base)
            else:
                logger.info('Additionally copying %s back to host...', base)

            if not skip_if_exists:
                with suppress(FileNotFoundError):
                    os.unlink(copied_back)

            self.worker.copy_to_host(product, copied_back)

            for l in self.buildable.link_builds:
                symlink = os.path.join(l, to_base)

                with suppress(FileNotFoundError):
                    os.unlink(symlink)

                os.symlink(copied_back, symlink)

            return copied_back
