# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging
import os
import shutil
import subprocess

from vectis.debuild import (
        Build,
        Buildable,
        )
from vectis.util import (
        AtomicWriter,
        )
from vectis.worker import Worker

logger = logging.getLogger(__name__)

def get_dpkg_buildpackage_options(args, suite):
    argv = []

    if args._versions_since:
        argv.append('-v{}'.format(args._versions_since))

    force_parallel = args.force_parallel or suite.force_parallel

    if force_parallel:
        argv.append('-j{}'.format(force_parallel))
    elif args.parallel == 1:
        argv.append('-j1')
    elif args.parallel:
        argv.append('-J{}'.format(args.parallel))
    else:
        argv.append('-Jauto')

    for a in get_dpkg_source_options(args):
        argv.append('--source-option=' + a)

    return argv

def get_dpkg_source_options(args):
    argv = []

    if args.dpkg_source_diff_ignore is ...:
        argv.append('-i')
    elif args.dpkg_source_diff_ignore is not None:
        argv.append('-i{}'.format(
            args.dpkg_source_diff_ignore))

    for pattern in args.dpkg_source_tar_ignore:
        if pattern is ...:
            argv.append('-I')
        else:
            argv.append('-I{}'.format(pattern))

    for pattern in args.dpkg_source_extend_diff_ignore:
        argv.append('--extend-diff-ignore={}'.format(pattern))

    return argv

def _run(args, worker):
    buildables = []

    for a in (args._buildables or ['.']):
        buildables.append(Buildable(a, vendor=args.vendor))

    logger.info('Installing sbuild')
    worker.set_up_apt(args.worker_suite)
    worker.check_call([
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

        buildable.copy_source_to(worker)

        buildable.select_suite(args.suite)

        if buildable.suite == 'UNRELEASED':
            suite = args.vendor.get_suite(args.vendor.default_suite)
        else:
            suite = args.vendor.get_suite(buildable.suite)

        dpkg_buildpackage_options = get_dpkg_buildpackage_options(args, suite)
        dpkg_source_options = get_dpkg_source_options(args)

        def new_build(arch, output_builds=args.output_builds):
            return Build(buildable, arch, worker,
                    components=args.components,
                    extra_repositories=args._extra_repository,
                    dpkg_buildpackage_options=dpkg_buildpackage_options,
                    dpkg_source_options=dpkg_source_options,
                    output_builds=output_builds,
                    storage=args.storage,
                    suite=suite)

        if args._rebuild_source or buildable.dsc is None:
            new_build('source').sbuild()
        elif buildable.source_from_archive:
            # We need to get some information from the .dsc, which we do by
            # building one and throwing it away.
            new_build('source', output_builds=None).sbuild()

        if not args._source_only:
            buildable.select_archs(worker.dpkg_architecture, args._archs,
                    args._indep, args.sbuild_together)

            for arch in buildable.archs:
                new_build(arch).sbuild()

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
                        'removesrc', str(reprepro_suite),
                        buildable.source_package])
                    subprocess.call(['reprepro', '--ignore=wrongdistribution',
                        '--ignore=missingfile',
                        '-b', args._reprepro_dir, 'include',
                        str(reprepro_suite),
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
    with Worker(args.worker) as worker:
        _run(args, worker)
