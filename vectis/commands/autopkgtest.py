# Copyright © 2017 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging
import os

from debian.deb822 import (
    Changes,
    Dsc,
)

from vectis.autopkgtest import (
    run_autopkgtest,
)
from vectis.error import (
    ArgumentError,
)

logger = logging.getLogger(__name__)


class Source:

    def __init__(
            self,
            name,
            *,
            dsc=None):
        self.name = name
        self.dsc = dsc
        self.failures = []

    def __str__(self):
        return self.name


def _autopkgtest(
        things,
        *,
        architecture,
        built_binaries,
        lxc_24bit_subnet,
        lxc_worker,
        lxc_worker_suite,
        mirrors,
        modes,
        storage,
        suite,
        vendor,
        worker_argv,
        worker_suite,
        extra_repositories=()):
    binaries = []
    sources = []

    for thing in things:
        if os.path.exists(thing):
            if thing.endswith('.changes'):
                with open(thing) as reader:
                    c = Changes(reader)

                    for f in c['files']:
                        n = os.path.join(os.path.dirname(thing), f['name'])

                        if f['name'].endswith('.deb'):
                            binaries.append(n)
                        elif f['name'].endswith('.dsc'):
                            sources.append(Source(f['name'], dsc=Dsc(open(n))))

            elif thing.endswith('.dsc'):
                sources.append(Source(thing, dsc=Dsc(open(thing))))

            elif thing.endswith('.deb'):
                binaries.append(thing)
        else:
            sources.append(Source(thing))

    failures = set()

    for source in sources:
        source_dsc = None
        source_package = None

        if source.dsc is not None:
            source_dsc = source.name
        else:
            source_package = source.name

        if built_binaries is None:
            built_binaries = not binaries

        for failure in run_autopkgtest(
                architecture=architecture,
                binaries=binaries,
                built_binaries=built_binaries,
                components=(),
                extra_repositories=extra_repositories,
                lxc_24bit_subnet=lxc_24bit_subnet,
                lxc_worker=lxc_worker,
                lxc_worker_suite=lxc_worker_suite,
                mirrors=mirrors,
                modes=modes,
                source_dsc=source_dsc,
                source_package=source_package,
                storage=storage,
                suite=suite,
                vendor=vendor,
                worker_argv=worker_argv,
                worker_suite=worker_suite,
        ):
            source.failures.append(failure)
            failures.add(source)

    return failures


def run(args, really=True):
    if args.suite is None:
        if args.default_suite is not None:
            args.suite = args.default_suite
        else:
            raise ArgumentError('--suite must be specified')

    failures = _autopkgtest(
        args._things,
        architecture=args.architecture,
        built_binaries=args._built_binaries,
        extra_repositories=args._extra_repository,
        lxc_24bit_subnet=args.lxc_24bit_subnet,
        lxc_worker=args.lxc_worker,
        lxc_worker_suite=args.lxc_worker_suite,
        mirrors=args.get_mirrors(),
        modes=args.autopkgtest,
        storage=args.storage,
        suite=args.suite,
        vendor=args.vendor,
        worker_argv=args.worker,
        worker_suite=args.worker_suite,
    )

    for failure in sorted(failures):
        logger.error('%s failed testing: %s', failure, failure.failures)
