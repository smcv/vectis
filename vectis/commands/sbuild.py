# Copyright © 2016-2017 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging
import os
import subprocess

from vectis.config import (
    Suite,
)
from vectis.debuild import (
    BuildGroup,
)
from vectis.error import (
    ArgumentError,
)

logger = logging.getLogger(__name__)


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

    group = BuildGroup(
        binary_version_suffix=args._append_to_version,
        buildables=(args._buildables or '.'),
        components=args.components,
        deb_build_options=deb_build_options,
        dpkg_buildpackage_options=db_options,
        dpkg_source_options=ds_options,
        extra_repositories=args._extra_repository,
        link_builds=args.link_builds,
        orig_dirs=args.orig_dirs,
        output_dir=args.output_dir,
        output_parent=args.output_parent,
        mirrors=args.get_mirrors(),
        profiles=profiles,
        sbuild_options=args._sbuild_options,
        storage=args.storage,
        suite=args.suite,
        vendor=args.vendor,
    )

    group.select_suites(args)

    for b in group.buildables:
        for suite in (b.suite, args.sbuild_worker_suite):
            assert isinstance(suite, Suite)

            for ancestor in suite.hierarchy:
                mirror = group.mirrors.lookup_suite(ancestor)
                if mirror is None:
                    raise ArgumentError(
                        'No mirror configured for {}'.format(ancestor))

    sbuild_worker = group.get_worker(
        args.sbuild_worker,
        args.sbuild_worker_suite,
    )
    group.sbuild(
        sbuild_worker,
        archs=args._archs,
        build_source=args._build_source,
        indep=args._indep,
        indep_together=args.sbuild_indep_together,
        source_only=args._source_only,
        source_together=args.sbuild_source_together,
    )

    misc_worker = group.get_worker(args.worker, args.worker_suite)

    piuparts_worker = group.get_worker(
        args.piuparts_worker,
        args.piuparts_worker_suite,
    )

    lxc_worker = group.get_worker(
        args.lxc_worker,
        args.lxc_worker_suite,
    )

    lxd_worker = group.get_worker(
        args.lxd_worker,
        args.lxd_worker_suite,
    )

    interrupted = False

    try:
        group.autopkgtest(
            default_architecture=sbuild_worker.dpkg_architecture,
            lxc_24bit_subnet=args.lxc_24bit_subnet,
            lxc_worker=lxc_worker,
            lxd_worker=lxd_worker,
            modes=args.autopkgtest,
            qemu_ram_size=args.qemu_ram_size,
            schroot_worker=sbuild_worker,
            worker=misc_worker,
        )
    except KeyboardInterrupt:
        interrupted = True

    if args.piuparts_tarballs and not interrupted:
        try:
            group.piuparts(
                default_architecture=sbuild_worker.dpkg_architecture,
                tarballs=args.piuparts_tarballs,
                worker=piuparts_worker,
            )
        except KeyboardInterrupt:
            interrupted = True

    _summarize(group.buildables)

    if not interrupted:
        try:
            _lintian(group.buildables)
        except KeyboardInterrupt:
            logger.warning('lintian interrupted')
            interrupted = True

    if args._reprepro_dir and not interrupted:
        _publish(group.buildables, args._reprepro_dir, args._reprepro_suite)

    # We print these separately, right at the end, so that if you built more
    # than one thing, the last screenful of information is the really
    # important bit for testing/signing/upload
    for buildable in group.buildables:
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

    for buildable in group.buildables:
        logger.info(
            'Output directory for %s: %s',
            buildable,
            buildable.output_dir,
        )
