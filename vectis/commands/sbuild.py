# Copyright © 2016-2017 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging
import os
import shutil
import subprocess
from contextlib import suppress

from vectis.autopkgtest import (
    run_autopkgtest,
)
from vectis.config import (
    Suite,
)
from vectis.debuild import (
    Build,
    Buildable,
)
from vectis.error import (
    ArgumentError,
)
from vectis.piuparts import (
    Binary,
    run_piuparts,
)
from vectis.util import (
    AtomicWriter,
)
from vectis.worker import (
    VirtWorker,
)

logger = logging.getLogger(__name__)


def _sbuild(
        buildables,
        *,
        archs,
        components,
        indep,
        mirrors,
        profiles,
        build_source,
        sbuild_options=(),
        source_only,
        storage,
        vendor,
        worker,
        deb_build_options=(),
        dpkg_buildpackage_options=(),
        dpkg_source_options=(),
        extra_repositories=(),
        indep_together=False,
        source_together=False):

    logger.info('Installing sbuild')
    worker.check_call([
        'env',
        'DEBIAN_FRONTEND=noninteractive',
        'apt-get',
        '-y',
        '-t', worker.suite.apt_suite,
        '--no-install-recommends',
        'install',

        'python3',
        'sbuild',
        'schroot',
    ])
    # Be like the real Debian build infrastructure: give sbuild a
    # nonexistent home directory.
    worker.check_call([
        'usermod',
        '-d', '/nonexistent',
        'sbuild',
    ])

    for buildable in buildables:
        logger.info('Processing: %s', buildable)

        buildable.copy_source_to(worker)

        def new_build(
                arch,
                output_dir=buildable.output_dir):
            return Build(
                buildable, arch, worker,
                components=components,
                deb_build_options=deb_build_options,
                dpkg_buildpackage_options=dpkg_buildpackage_options,
                dpkg_source_options=dpkg_source_options,
                extra_repositories=extra_repositories,
                mirrors=mirrors,
                output_dir=output_dir,
                profiles=profiles,
                storage=storage,
            )

        if buildable.source_from_archive:
            # We need to get some information from the .dsc, which we do by
            # building one and (usually) throwing it away.
            # TODO: With jessie's sbuild, this doesn't work for
            # sources that only build Architecture: all binaries.
            # TODO: This won't work if the sbuild_options are a binNMU.
            if build_source:
                logger.info('Rebuilding source as requested')
                new_build('source').sbuild(sbuild_options=sbuild_options)
            else:
                logger.info(
                    'Rebuilding and discarding source to discover supported '
                    'architectures')
                new_build(
                    'source',
                    output_dir=None,
                ).sbuild(sbuild_options=sbuild_options)

        buildable.select_archs(
            worker_arch=worker.dpkg_architecture,
            archs=archs,
            indep=indep,
            indep_together=indep_together,
            build_source=build_source,
            source_only=source_only,
            source_together=source_together,
        )

        logger.info('Builds required: %r', list(buildable.archs))

        for arch in buildable.archs:
            new_build(arch).sbuild(sbuild_options=sbuild_options)

        if buildable.sourceful_changes_name:
            base = '{}_source.changes'.format(buildable.product_prefix)
            c = os.path.join(buildable.output_dir, base)
            c = os.path.abspath(c)
            if 'source' not in buildable.changes_produced:
                with AtomicWriter(c) as writer:
                    subprocess.check_call([
                        'mergechanges',
                        '--source',
                        buildable.sourceful_changes_name,
                        buildable.sourceful_changes_name,
                    ], stdout=writer)

            buildable.merged_changes['source'] = c

        if ('all' in buildable.changes_produced and
                'source' in buildable.merged_changes):
            base = '{}_source+all.changes'.format(buildable.product_prefix)
            c = os.path.join(buildable.output_dir, base)
            c = os.path.abspath(c)
            buildable.merged_changes['source+all'] = c
            with AtomicWriter(c) as writer:
                subprocess.check_call([
                    'mergechanges',
                    buildable.changes_produced['all'],
                    buildable.merged_changes['source'],
                ], stdout=writer)

        binary_group = 'binary'

        binary_changes = []
        for k, v in buildable.changes_produced.items():
            if k != 'source':
                binary_changes.append(v)

                if v == buildable.sourceful_changes_name:
                    binary_group = 'source+binary'

        base = '{}_{}.changes'.format(buildable.product_prefix, binary_group)
        c = os.path.join(buildable.output_dir, base)
        c = os.path.abspath(c)

        if len(binary_changes) > 1:
            with AtomicWriter(c) as writer:
                subprocess.check_call(
                    ['mergechanges'] + binary_changes, stdout=writer)
            buildable.merged_changes[binary_group] = c
        elif len(binary_changes) == 1:
            shutil.copy(binary_changes[0], c)
            buildable.merged_changes[binary_group] = c
        # else it was source-only: no binary changes

        if ('source' in buildable.merged_changes and
                'binary' in buildable.merged_changes):
            base = '{}_source+binary.changes'.format(buildable.product_prefix)
            c = os.path.join(buildable.output_dir, base)
            c = os.path.abspath(c)
            buildable.merged_changes['source+binary'] = c

            with AtomicWriter(c) as writer:
                subprocess.check_call([
                    'mergechanges',
                    buildable.merged_changes['source'],
                    buildable.merged_changes['binary'],
                ], stdout=writer)

        for ident, linkable in (
                list(buildable.merged_changes.items()) +
                list(buildable.changes_produced.items())):
            base = os.path.basename(linkable)

            for l in buildable.link_builds:
                symlink = os.path.join(l, base)

                with suppress(FileNotFoundError):
                    os.unlink(symlink)

                os.symlink(linkable, symlink)


def _autopkgtest(
        buildables,
        default_architecture,
        *,
        components,
        lxc_24bit_subnet,
        lxc_worker,
        lxd_worker,
        mirrors,
        modes,
        qemu_ram_size,
        schroot_worker,
        storage,
        vendor,
        worker,
        extra_repositories=()):
    for buildable in buildables:
        source_dsc = None
        source_package = None

        if buildable.dsc_name is not None:
            source_dsc = buildable.dsc_name
            logger.info('Testing source changes file %s', source_dsc)
        elif buildable.source_from_archive:
            source_package = buildable.source_package
            logger.info('Testing source package %s', source_package)
        else:
            logger.warning(
                'Unable to run autopkgtest on %s', buildable.buildable)
            continue

        if buildable.dsc is not None and 'testsuite' not in buildable.dsc:
            logger.info('No autopkgtests available')
            continue

        test_architectures = []

        for arch in buildable.archs:
            if arch != 'all' and arch != 'source':
                test_architectures.append(arch)

        if 'all' in buildable.archs and not test_architectures:
            test_architectures.append(default_architecture)

        logger.info('Testing on architectures: %r', test_architectures)

        for architecture in test_architectures:
            buildable.autopkgtest_failures.extend(
                run_autopkgtest(
                    architecture=architecture,
                    binaries=buildable.get_debs(architecture),
                    components=components,
                    extra_repositories=extra_repositories,
                    lxc_24bit_subnet=lxc_24bit_subnet,
                    lxc_worker=lxc_worker,
                    lxd_worker=lxd_worker,
                    mirrors=mirrors,
                    modes=modes,
                    output_logs=buildable.output_dir,
                    qemu_ram_size=qemu_ram_size,
                    schroot_worker=schroot_worker,
                    source_dsc=source_dsc,
                    source_package=source_package,
                    storage=storage,
                    suite=buildable.suite,
                    vendor=vendor,
                    worker=worker,
                ),
            )


def _piuparts(
        buildables,
        default_architecture,
        *,
        components,
        mirrors,
        storage,
        tarballs,
        vendor,
        worker,
        extra_repositories=()):
    for buildable in buildables:
        test_architectures = []

        for arch in buildable.archs:
            if arch != 'all' and arch != 'source':
                test_architectures.append(arch)

        if 'all' in buildable.archs and not test_architectures:
            test_architectures.append(default_architecture)

        logger.info('Running piuparts on architectures: %r', test_architectures)

        for architecture in test_architectures:
            buildable.piuparts_failures.extend(
                run_piuparts(
                    architecture=architecture,
                    binaries=(Binary(b, deb=b)
                        for b in buildable.get_debs(architecture)),
                    components=components,
                    extra_repositories=extra_repositories,
                    mirrors=mirrors,
                    output_logs=buildable.output_dir,
                    storage=storage,
                    suite=buildable.suite,
                    tarballs=tarballs,
                    vendor=vendor,
                    worker=worker,
                ),
            )


def _summarize(buildables):
    for buildable in buildables:
        logger.info(
            'Built changes files from %s:\n\t%s',
            buildable,
            '\n\t'.join(sorted(buildable.changes_produced.values())),
        )

        logger.info(
            'Build logs from %s:\n\t%s',
            buildable,
            '\n\t'.join(sorted(buildable.logs.values())),
        )


def _lintian(buildables):
    for buildable in buildables:
        # Run lintian near the end for better visibility
        for x in 'source+binary', 'binary', 'source':
            if x in buildable.merged_changes:
                subprocess.call(
                    ['lintian', '-I', '-i', buildable.merged_changes[x]])

                break


def _publish(
        buildables,
        reprepro_dir,
        default_reprepro_suite=None):
    for buildable in buildables:
        for x in 'source+binary', 'binary', 'source':
            if x in buildable.merged_changes:
                reprepro_suite = default_reprepro_suite

                if reprepro_suite is None:
                    reprepro_suite = buildable.nominal_suite

                subprocess.call([
                    'reprepro', '-b', reprepro_dir,
                    'removesrc', str(reprepro_suite),
                    buildable.source_package,
                ])
                subprocess.call([
                    'reprepro', '--ignore=wrongdistribution',
                    '--ignore=missingfile',
                    '-b', reprepro_dir, 'include',
                    str(reprepro_suite),
                    os.path.join(
                        buildable.output_dir,
                        buildable.merged_changes[x]),
                ])
                break


def run(args):
    components = args.components
    link_builds = args.link_builds
    orig_dirs = args.orig_dirs
    output_dir = args.output_dir
    output_parent = args.output_parent
    mirrors = args.get_mirrors()
    sbuild_options = list(args._sbuild_options)
    storage = args.storage
    vendor = args.vendor

    deb_build_options = set()

    if 'DEB_BUILD_OPTIONS' in os.environ:
        for arg in os.environ['DEB_BUILD_OPTIONS'].split():
            deb_build_options.add(arg)

    for arg in args._add_deb_build_option:
        deb_build_options.add(arg)

    for arg in deb_build_options:
        if arg == 'parallel' or arg.startswith('parallel='):
            break
    else:
        deb_build_options.add('parallel={}'.format(args.parallel))

    profiles = set()

    if args._build_profiles is not None:
        for arg in args._build_profiles.split(','):
            profiles.add(arg)
    elif 'DEB_BUILD_PROFILES' in os.environ:
        for arg in os.environ['DEB_BUILD_PROFILES'].split():
            profiles.add(arg)

    for arg in args._add_build_profile:
        profiles.add(arg)

    db_options = []

    if args._versions_since:
        db_options.append('-v{}'.format(args._versions_since))

    if args._include_orig_source is not None:
        MAP = {
            'yes': 'a',
            'always': 'a',
            'force': 'a',
            'a': 'a',

            'auto': 'i',
            'maybe': 'i',
            'i': 'i',

            'no': 'd',
            'never': 'd',
            'd': 'd',
        }

        db_options.append('-s{}'.format(MAP[args._include_orig_source]))

    ds_options = []

    if args.dpkg_source_diff_ignore is ...:
        ds_options.append('-i')
    elif args.dpkg_source_diff_ignore is not None:
        ds_options.append('-i{}'.format(
            args.dpkg_source_diff_ignore))

    for pattern in args.dpkg_source_tar_ignore:
        if pattern is ...:
            ds_options.append('-I')
        else:
            ds_options.append('-I{}'.format(pattern))

    for pattern in args.dpkg_source_extend_diff_ignore:
        ds_options.append('--extend-diff-ignore={}'.format(pattern))

    buildables = []

    for a in (args._buildables or ['.']):
        buildable = Buildable(
            a,
            binary_version_suffix=args._append_to_version,
            link_builds=link_builds,
            orig_dirs=orig_dirs,
            output_dir=output_dir,
            output_parent=output_parent,
            vendor=vendor)
        buildable.select_suite(args, args.suite)
        buildables.append(buildable)

        for suite in (buildable.suite, args.sbuild_worker_suite):
            assert isinstance(suite, Suite)

            for ancestor in suite.hierarchy:
                mirror = mirrors.lookup_suite(ancestor)
                if mirror is None:
                    raise ArgumentError(
                        'No mirror configured for {}'.format(ancestor))

    sbuild_worker = VirtWorker(
        args.sbuild_worker,
        mirrors=mirrors,
        storage=storage,
        suite=args.sbuild_worker_suite,
    )

    with sbuild_worker as worker:
        default_architecture = worker.dpkg_architecture
        _sbuild(
            buildables,
            archs=args._archs,
            components=components,
            deb_build_options=deb_build_options,
            dpkg_buildpackage_options=db_options,
            dpkg_source_options=ds_options,
            extra_repositories=args._extra_repository,
            indep=args._indep,
            indep_together=args.sbuild_indep_together,
            mirrors=mirrors,
            profiles=profiles,
            build_source=args._build_source,
            sbuild_options=sbuild_options,
            source_only=args._source_only,
            storage=storage,
            source_together=args.sbuild_source_together,
            vendor=vendor,
            worker=worker,
        )

    if (args.worker == args.sbuild_worker and
            args.worker_suite == args.sbuild_worker_suite):
        misc_worker = sbuild_worker
    else:
        misc_worker = VirtWorker(
            args.worker,
            mirrors=mirrors,
            storage=storage,
            suite=args.worker_suite,
        )

    if (args.piuparts_worker == args.sbuild_worker and
            args.piuparts_worker_suite == args.sbuild_worker_suite):
        piuparts_worker = sbuild_worker
    else:
        piuparts_worker = VirtWorker(
            args.piuparts_worker,
            mirrors=mirrors,
            storage=storage,
            suite=args.piuparts_worker_suite,
        )

    if (args.lxc_worker == args.sbuild_worker and
            args.lxc_worker_suite == args.sbuild_worker_suite):
        lxc_worker = sbuild_worker
    else:
        lxc_worker = VirtWorker(
            args.lxc_worker,
            mirrors=mirrors,
            storage=storage,
            suite=args.lxc_worker_suite,
        )

    if (args.lxd_worker == args.sbuild_worker and
            args.lxd_worker_suite == args.sbuild_worker_suite):
        lxd_worker = sbuild_worker
    else:
        lxd_worker = VirtWorker(
            args.lxd_worker,
            mirrors=mirrors,
            storage=storage,
            suite=args.lxd_worker_suite,
        )

    _autopkgtest(
        buildables, default_architecture,
        components=components,
        extra_repositories=args._extra_repository,
        lxc_24bit_subnet=args.lxc_24bit_subnet,
        lxc_worker=lxc_worker,
        lxd_worker=lxd_worker,
        mirrors=mirrors,
        modes=args.autopkgtest,
        qemu_ram_size=args.qemu_ram_size,
        schroot_worker=sbuild_worker,
        storage=storage,
        vendor=vendor,
        worker=misc_worker,
    )

    if args.piuparts_tarballs:
        _piuparts(
            buildables, default_architecture,
            components=components,
            extra_repositories=args._extra_repository,
            mirrors=mirrors,
            storage=storage,
            tarballs=args.piuparts_tarballs,
            vendor=vendor,
            worker=piuparts_worker,
        )

    _summarize(buildables)
    _lintian(buildables)

    if args._reprepro_dir:
        _publish(buildables, args._reprepro_dir, args._reprepro_suite)

    # We print these separately, right at the end, so that if you built more
    # than one thing, the last screenful of information is the really
    # important bit for testing/signing/upload
    for buildable in buildables:
        logger.info(
            'Merged changes files from %s:\n\t%s',
            buildable,
            '\n\t'.join(buildable.merged_changes.values()),
        )

        if buildable.autopkgtest_failures:
            logger.error('Autopkgtest failures for %s:', buildable)
            for x in buildable.autopkgtest_failures:
                logger.error('- %s', x)

        if buildable.piuparts_failures:
            logger.error('Piuparts failures for %s:', buildable)
            for x in buildable.piuparts_failures:
                logger.error('- %s', x)

    for buildable in buildables:
        logger.info(
            'Output directory for %s: %s',
            buildable,
            buildable.output_dir,
        )
