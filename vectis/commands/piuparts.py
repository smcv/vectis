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

logger = logging.getLogger(__name__)


def _piuparts(
        things,
        *,
        architecture,
        mirror,
        storage,
        suite,
        vendor,
        worker_argv,
        worker_suite,
        extra_repositories=()):
    binaries = []

    for thing in things:
        if os.path.exists(thing):
            if thing.endswith('.changes'):
                with open(thing) as reader:
                    c = Changes(reader)

                    for f in c['files']:
                        n = os.path.join(os.path.dirname(thing), f['name'])

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
        mirror=mirror,
        storage=storage,
        suite=suite,
        vendor=vendor,
        worker_argv=worker_argv,
        worker_suite=worker_suite,
    )


def run(args):
    if args.suite is None:
        if args.default_suite is not None:
            args.suite = args.default_suite
        else:
            raise ArgumentError('--suite must be specified')

    failures = _piuparts(
        args._things,
        architecture=args.architecture,
        extra_repositories=args._extra_repository,
        mirror=args.mirror,
        storage=args.storage,
        suite=args.suite,
        vendor=args.vendor,
        worker_argv=args.worker,
        worker_suite=args.worker_suite,
    )

    for failure in sorted(failures):
        logger.error('%s failed testing', failure)
