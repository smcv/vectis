# Copyright © 2017 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging
import os

from debian.deb822 import (
    Changes,
)

from vectis.error import (
    ArgumentError,
)
from vectis.piuparts import (
    Binary,
    run_piuparts,
)
from vectis.worker import (
    VirtWorker,
)

logger = logging.getLogger(__name__)


def _piuparts(
        things,
        *,
        architecture,
        mirrors,
        storage,
        suite,
        tarballs,
        vendor,
        worker,
        extra_repositories=()):
    binaries = []

    for thing in things:
        if os.path.exists(thing):
            if thing.endswith('.changes'):
                with open(thing) as reader:
                    c = Changes(reader)

                    for f in c['files']:
                        n = os.path.join(
                            os.path.dirname(thing) or os.curdir, f['name'],
                        )

                        if f['name'].endswith('.deb'):
                            binaries.append(Binary(n, deb=n))

            elif thing.endswith('.deb'):
                binaries.append(Binary(thing, deb=thing))
        else:
            binaries.append(Binary(thing))

    return run_piuparts(
        architecture=architecture,
        binaries=binaries,
        components=(),
        extra_repositories=extra_repositories,
        mirrors=mirrors,
        storage=storage,
        suite=suite,
        tarballs=tarballs,
        vendor=vendor,
        worker=worker,
    )


def run(args):
    if args.suite is None:
        if args.default_suite is not None:
            args.suite = args.default_suite
        else:
            raise ArgumentError('--suite must be specified')

    worker = VirtWorker(
        args.piuparts_worker,
        mirrors=args.get_mirrors(),
        storage=args.storage,
        suite=args.piuparts_worker_suite,
    )
    failures = _piuparts(
        args._things,
        architecture=args.architecture,
        extra_repositories=args._extra_repository,
        mirrors=args.get_mirrors(),
        storage=args.storage,
        suite=args.suite,
        tarballs=args.get_piuparts_tarballs(
            architecture=args.architecture,
            suite=args.suite,
            vendor=args.vendor,
        ),
        vendor=args.vendor,
        worker=worker,
    )

    for failure in sorted(failures):
        logger.error('%s failed testing', failure)
