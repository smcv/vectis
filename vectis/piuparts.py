# Copyright © 2017 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging
import os
import uuid
from contextlib import (
    ExitStack,
)

from vectis.worker import (
    ContainerWorker,
    FileProvider,
    HostWorker,
    InteractiveWorker,
    VirtWorker,
)

logger = logging.getLogger(__name__)


class Binary:

    def __init__(
            self,
            name,
            *,
            deb=None):
        self.deb = deb
        self.name = name

    def __str__(self):
        return self.name


class PiupartsWorker(FileProvider, ContainerWorker):

    def __init__(
            self,
            *,
            architecture,
            mirrors,
            suite,
            tarball,
            components=(),
            extra_repositories=(),
            worker=None):
        super().__init__(mirrors=mirrors, suite=suite)

        if worker is None:
            worker = self.stack.enter_context(HostWorker())

        self.__bound = set()
        self.__cached_copies = {}
        self.apt_related_argv = []
        self.argv = [
            'piuparts',
            '--arch',
            architecture,
            '-b',
            tarball,
        ]
        self.components = components
        self.extra_repositories = extra_repositories
        self.worker = worker

        assert isinstance(self.worker, InteractiveWorker)

    def _open(self):
        super()._open()
        self.set_up_apt()

    def set_up_apt(self):
        argv = []

        for ancestor in self.suite.hierarchy:
            if self.components:
                filtered_components = (
                    set(self.components) & set(ancestor.all_components))
            else:
                filtered_components = ancestor.components

            uri = self.mirrors.lookup_suite(ancestor)

            if ancestor is self.suite.hierarchy[-1]:
                argv.append('-d')
                argv.append(ancestor.apt_suite)
                argv.append('--mirror')
                argv.append('{} {}'.format(
                    uri, ' '.join(filtered_components)))
            else:
                argv.append('--extra-repo')
                argv.append('deb {} {} {}'.format(
                    uri, ancestor.apt_suite, ' '.join(filtered_components)))

        for line in self.extra_repositories:
            argv.append('--extra-repo')
            argv.append(line)

        self.apt_related_argv = argv
        self.install_apt_keys()

    def install_apt_key(self, apt_key):
        logger.debug('TODO: piuparts does not have an option to install '
                     'apt keys')

    def call_piuparts(
            self,
            *,
            binaries,
            output_dir=None):

        packages = []

        for b in binaries:
            if b.deb is None:
                packages.append(b.name)
            else:
                packages.append(self.make_file_available(b.deb))

        argv = self.argv[:]

        for b in binaries:
            if b.deb is None:
                argv.append('--apt')
                break

        if output_dir is not None:
            argv.append('-l')
            argv.append(output_dir + '/piuparts.log')

        return (self.worker.call(argv + self.apt_related_argv + packages) == 0)

    def new_directory(self, prefix=''):
        # assume /tmp is initially empty and mktemp won't collide
        d = self.worker.new_directory()
        self.argv.append('--bindmount={}'.format(d))
        self.__bound.add(d)
        return d

    def make_file_available(
            self,
            filename,
            *,
            cache=False,
            in_dir=None,
            owner=None):
        if in_dir is None:
            in_dir = self.new_directory()

        if cache:
            in_guest = self.__cached_copies.get((filename, in_dir))
            if in_guest is not None:
                return in_guest

        unique = str(uuid.uuid4())
        in_guest = self.worker.make_file_available(
            filename, cache=cache, in_dir=in_dir)

        if in_dir not in self.__bound:
            self.argv.append('--bindmount={}/{}'.format(in_dir, unique))

        if cache:
            self.__cached_copies[(filename, in_dir)] = in_guest

        return in_guest

    def make_dsc_file_available(self, filename, owner=None):
        d, f = self.worker.make_dsc_file_available(filename)
        self.argv.append('--bindmount={}'.format(d))
        return d, f

    def make_changes_file_available(self, filename, owner=None):
        d, f = self.worker.make_changes_file_available(filename)
        self.argv.append('--bindmount={}'.format(d))
        return d, f


def run_piuparts(
        *,
        components,
        mirrors,
        storage,
        suite,
        tarballs,
        vendor,
        worker_argv,
        worker_suite,
        architecture=None,
        binaries=(),
        extra_repositories=(),
        output_logs=None,
        source_dsc=None,
        source_package=None):
    failures = []
    # We may need to iterate these more than once
    binaries = list(binaries)

    with ExitStack() as stack:
        worker = stack.enter_context(
            VirtWorker(
                worker_argv,
                mirrors=mirrors,
                storage=storage,
                suite=worker_suite,
            )
        )

        worker.check_call([
            'env',
            'DEBIAN_FRONTEND=noninteractive',
            'apt-get',
            '-y',
            '-t', worker_suite.apt_suite,
            'install',

            'piuparts',
        ])

        for basename in tarballs:
            tarball = os.path.join(
                storage,
                architecture,
                str(vendor),
                str(suite.hierarchy[-1]),
                basename)

            if not os.path.exists(tarball):
                logger.info('Required tarball %s does not exist',
                            tarball)
                continue

            piuparts = stack.enter_context(
                PiupartsWorker(
                    architecture=architecture,
                    components=components,
                    extra_repositories=extra_repositories,
                    mirrors=mirrors,
                    suite=suite,
                    tarball=worker.make_file_available(
                        tarball, cache=True),
                    worker=worker,
                )
            )

            for mode in ('install-purge',):
                if output_logs is None:
                    output_dir = None
                else:
                    output_dir = os.path.join(
                        output_logs,
                        'piuparts_{}_{}_{}'.format(
                            mode, basename, architecture))

                output_on_worker = worker.new_directory()

                if not piuparts.call_piuparts(
                        binaries=binaries,
                        output_dir=output_on_worker,
                ):
                    if output_dir is None:
                        failures.append(mode)
                    else:
                        failures.append(output_dir)

                if output_dir is not None:
                    worker.copy_to_host(
                        os.path.join(output_on_worker, ''),
                        os.path.join(output_dir, ''),
                    )

    return failures
