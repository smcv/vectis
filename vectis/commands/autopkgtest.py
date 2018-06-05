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
from vectis.worker import (
    VirtWorker,
)

logger = logging.getLogger(__name__)


class Source:

    def __init__(
            self,
            name,
            *,
            dsc=None):
        self.name = name

        if os.path.isdir(name):
            self.dir = name
        else:
            self.dir = None

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
        lxd_worker,
        mirrors,
        modes,
        qemu_ram_size,
        schroot_worker,
        storage,
        suite,
        vendor,
        worker,
        extra_repositories=()):
    binaries = []
    sources = []

    for thing in things:
        if os.path.exists(thing):
            if thing.endswith('.changes'):
                with open(thing) as reader:
                    c = Changes(reader)

                    for f in c['files']:
                        n = os.path.join(
                            os.path.dirname(thing) or os.curdir, f['name'])

                        if f['name'].endswith('.deb'):
                            binaries.append(n)
                        elif f['name'].endswith('.dsc'):
                            sources.append(Source(n, dsc=Dsc(open(n))))

            elif thing.endswith('.dsc'):
                sources.append(Source(thing, dsc=Dsc(open(thing))))

            elif thing.endswith('.deb'):
                binaries.append(thing)

            elif os.path.isdir(thing):
                sources.append(Source(thing))
        else:
            sources.append(Source(thing))

    failures = set()

    for source in sources:
        source_dir = None
        source_dsc = None
        source_package = None

        if source.dsc is not None:
            source_dsc = source.name
        elif source.dir is not None:
            source_dir = source.dir
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
                lxd_worker=lxd_worker,
                mirrors=mirrors,
                modes=modes,
                qemu_ram_size=qemu_ram_size,
                schroot_worker=schroot_worker,
                source_dir=source_dir,
                source_dsc=source_dsc,
                source_package=source_package,
                storage=storage,
                suite=suite,
                vendor=vendor,
                worker=worker,
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

    mirrors = args.get_mirrors()

    worker = VirtWorker(
        args.worker,
        mirrors=mirrors,
        storage=args.storage,
        suite=args.worker_suite,
    )

    if (args.lxc_worker == args.worker and
            args.lxc_worker_suite == args.worker_suite):
        lxc_worker = worker
    else:
        lxc_worker = VirtWorker(
            args.lxc_worker,
            mirrors=mirrors,
            storage=args.storage,
            suite=args.lxc_worker_suite,
        )

    if (args.lxd_worker == args.worker and
            args.lxd_worker_suite == args.worker_suite):
        lxd_worker = worker
    else:
        lxd_worker = VirtWorker(
            args.lxd_worker,
            mirrors=mirrors,
            storage=args.storage,
            suite=args.lxd_worker_suite,
        )

    failures = _autopkgtest(
        args._things,
        architecture=args.architecture,
        built_binaries=args._built_binaries,
        extra_repositories=args._extra_repository,
        lxc_24bit_subnet=args.lxc_24bit_subnet,
        lxc_worker=lxc_worker,
        lxd_worker=lxd_worker,
        worker=worker,
        mirrors=mirrors,
        modes=args.autopkgtest,
        qemu_ram_size=args.qemu_ram_size,
        # use the misc worker instead of a specific schroot worker
        schroot_worker=None,
        storage=args.storage,
        suite=args.suite,
        vendor=args.vendor,
    )

    for failure in sorted(failures):
        logger.error('%s failed testing: %s', failure, failure.failures)
