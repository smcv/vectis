# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging
import os
import shlex
import textwrap
import uuid
from contextlib import (
        ExitStack,
        )
from tempfile import (
        TemporaryDirectory,
        )

from debian.deb822 import (
        Changes,
        Dsc,
        )

from vectis.lxc import (
        set_up_lxc_net,
        )
from vectis.worker import (
        ContainerWorker,
        FileProvider,
        HostWorker,
        VirtWorker,
        )
from vectis.util import (
        AtomicWriter,
        )

logger = logging.getLogger(__name__)

class AutopkgtestWorker(ContainerWorker, FileProvider):
    def __init__(self,
            components=(),
            extra_repositories=(),
            mirror=None,
            suite=None,
            virt=(),
            worker=None):
        super().__init__()

        if worker is None:
            worker = self.stack.enter_context(HostWorker())

        self.__cached_copies = {}
        self.argv = ['autopkgtest', '--apt-upgrade']
        self.components = components
        self.extra_repositories = extra_repositories
        self.mirror = mirror
        self.sources_list = None
        self.suite = suite
        self.virt = virt
        self.worker = worker

    def install_apt_key(self, apt_key):
        to = '/etc/apt/trusted.gpg.d/{}-{}'.format(
                uuid.uuid4(), os.path.basename(apt_key))
        self.argv.append('--copy={}:{}'.format(
            self.worker.make_file_available(apt_key), to))

    def set_up_apt(self):
        tmp = TemporaryDirectory(prefix='vectis-worker-')
        tmp = self.stack.enter_context(tmp)
        self.sources_list = os.path.join(tmp, 'sources.list')

        with AtomicWriter(self.sources_list) as writer:
            self.write_sources_list(writer)

        sources_list = self.worker.make_file_available(self.sources_list)
        self.argv.append('--copy={}:{}'.format(sources_list,
            '/etc/apt/sources.list'))

    def call_autopkgtest(self,
            *,
            binaries,
            built_binaries,
            source_dsc=None,
            source_package=None):
        argv = self.argv[:]

        if not built_binaries:
            argv.append('-B')

        for b in binaries:
            if b.endswith('.changes'):
                argv.append(self.worker.make_changes_file_available(b))
            else:
                argv.append(self.worker.make_file_available(b))

        if source_dsc is not None:
            argv.append(self.worker.make_dsc_file_available(source_dsc))
        elif source_package is not None:
            argv.append(source_package)
        else:
            logger.warning('Nothing to test')
            return False

        argv.append('--')
        argv.extend(self.virt)
        status = self.worker.call(argv)
        if status == 0:
            logger.info('autopkgtests passed')
            return True
        elif status == 2:
            logger.info('autopkgtests passed or skipped')
            return True
        elif status == 8:
            logger.info('No autopkgtests found in this package')
            return True
        elif status == 12:
            logger.warning('Failed to install test dependencies')
            return False
        elif status == 16:
            logger.warning('Failed to set up testbed for autopkgtest')
            return False
        else:
            logger.error('autopkgtests failed')
            return False

    def new_directory(self, prefix=''):
        # assume /tmp is initially empty and uuid4() won't collide
        d = '/tmp/{}{}'.format(prefix, uuid.uuid4())
        self.argv.append('--setup-commands=mkdir {}'.format(shlex.quote(d)))
        return d

    def make_file_available(self, filename, cache=False):
        if cache:
            in_guest = self.__cached_copies.get(filename)
            if in_guest is not None:
                return in_guest

        unique = str(uuid.uuid4())
        filename = self.worker.make_file_available(filename, cache=cache)

        in_autopkgtest = '/tmp/{}/{}'.format(unique,
                os.path.basename(filename))
        self.argv.append('--copy={}:{}'.format(filename, in_autopkgtest))

        if cache:
            self.__cached_copies[filename] = in_autopkgtest

        return in_autopkgtest

    def make_dsc_file_available(self, filename):
        d = os.path.dirname(filename)

        with open(filename) as reader:
            dsc = Dsc(reader)

        to = self.new_directory()
        self.argv.append('--copy={}:{}'.format(filename,
                '{}/{}'.format(to, os.path.basename(filename))))

        for f in dsc['files']:
            self.argv.append('--copy={}:{}'.format(
                    os.path.join(d, f['name']),
                    '{}/{}'.format(to, f['name'])))

        return '{}/{}'.format(to, os.path.basename(filename))

    def make_changes_file_available(self, filename):
        d = os.path.dirname(filename)

        with open(filename) as reader:
            changes = Changes(reader)

        to = self.new_directory()
        self.argv.append('--copy={}:{}'.format(filename,
                '{}/{}'.format(to, os.path.basename(filename))))

        for f in changes['files']:
            self.argv.append('--copy={}:{}'.format(
                    os.path.join(d, f['name']),
                    '{}/{}'.format(to, f['name'])))

        return '{}/{}'.format(to, os.path.basename(filename))

    def _open(self):
        super()._open()
        self.set_up_apt()

def run_autopkgtest(*,
        components,
        worker_argv,
        worker_suite,
        modes,
        storage,
        suite,
        vendor,
        architecture=None,
        binaries=(),
        built_binaries=None,
        extra_repositories=(),
        lxc_24bit_subnet=None,
        lxc_worker=None,
        lxc_worker_suite=None,
        mirror=None,
        source_dsc=None,
        source_package=None):
    failures = []

    if lxc_worker is None:
        lxc_worker = worker_argv

    if lxc_worker_suite is None:
        lxc_worker_suite = worker_suite

    logger.info('Testing in modes: %r', modes)

    for test in modes:
        logger.info('Testing in mode: %s', test)
        with ExitStack() as stack:
            worker = None

            if test == 'qemu':
                image = os.path.join(
                    storage,
                    architecture,
                    str(vendor),
                    str(suite.hierarchy[-1]),
                    'autopkgtest.qcow2')

                if not image or not os.path.exists(image):
                    logger.info('Required image %s does not exist', image)
                    continue

                virt = ['qemu', image]

            elif test == 'schroot':
                tarball = os.path.join(
                        storage,
                        architecture,
                        str(vendor),
                        str(suite.hierarchy[-1]),
                        'minbase.tar.gz')

                if not os.path.exists(tarball):
                    logger.info('Required tarball %s does not exist',
                                tarball)
                    continue

                worker = stack.enter_context(
                    VirtWorker(
                        worker_argv,
                        suite=worker_suite,
                        ))

                worker.check_call([
                    'env',
                    'DEBIAN_FRONTEND=noninteractive',
                    'apt-get',
                    '-y',
                    '-t', worker_suite.apt_suite,
                    'install',

                    'autopkgtest',
                    'python3',
                    'schroot',
                    ])

                with TemporaryDirectory(prefix='vectis-sbuild-') as tmp:
                    with AtomicWriter(os.path.join(tmp, 'sbuild.conf')) as writer:
                        writer.write(textwrap.dedent('''
                        [autopkgtest]
                        type=file
                        description=Test
                        file={tarball}
                        groups=root,sbuild
                        root-groups=root,sbuild
                        profile=default
                        ''').format(
                            tarball=worker.make_file_available(tarball,
                                cache=True)))
                    worker.copy_to_guest(os.path.join(tmp, 'sbuild.conf'),
                            '/etc/schroot/chroot.d/autopkgtest')

                virt = ['schroot', 'autopkgtest']

            elif test == 'lxc':
                container = '{}-{}-{}'.format(
                        vendor,
                        suite.hierarchy[-1],
                        architecture,
                        )
                rootfs = os.path.join(
                        storage,
                        architecture,
                        str(vendor),
                        str(suite.hierarchy[-1]),
                        'lxc-rootfs.tar.gz')
                meta = os.path.join(
                        storage,
                        architecture,
                        str(vendor),
                        str(suite.hierarchy[-1]),
                        'lxc-meta.tar.gz')

                if not os.path.exists(rootfs) or not os.path.exists(meta):
                    logger.info('Required tarball %s or %s does not exist',
                                rootfs, meta)
                    continue

                worker = stack.enter_context(
                    VirtWorker(
                        lxc_worker,
                        suite=lxc_worker_suite,
                        ))

                worker.check_call([
                    'env',
                    'DEBIAN_FRONTEND=noninteractive',
                    'apt-get',
                    '-y',
                    '-t', lxc_worker_suite.apt_suite,
                    'install',

                    'autopkgtest',
                    'lxc',
                    'python3',
                    ])
                set_up_lxc_net(worker, lxc_24bit_subnet)
                worker.check_call(['mkdir', '-p',
                    '/var/lib/lxc/vectis-new/rootfs'])
                with open(rootfs, 'rb') as reader:
                    worker.check_call(['tar', '-x', '-z',
                        '-C', '/var/lib/lxc/vectis-new/rootfs',
                        '-f', '-'], stdin=reader)
                with open(meta, 'rb') as reader:
                    worker.check_call(['tar', '-x', '-z',
                        '-C', '/var/lib/lxc/vectis-new',
                        '-f', '-'], stdin=reader)
                worker.check_call(['mv', '/var/lib/lxc/vectis-new',
                    '/var/lib/lxc/{}'.format(container)])

                virt = ['lxc', container]

            else:
                logger.warning('Unknown autopkgtest setup: {}'.format(test))
                continue

            if worker is None:
                worker = stack.enter_context(HostWorker())

            autopkgtest = stack.enter_context(
                AutopkgtestWorker(
                    components=components,
                    extra_repositories=extra_repositories,
                    mirror=mirror,
                    suite=suite,
                    worker=worker,
                    virt=virt,
                    ))

            if not autopkgtest.call_autopkgtest(
                    binaries=binaries,
                    built_binaries=built_binaries,
                    source_dsc=source_dsc,
                    source_package=source_package,
                    ):
                failures.append(test)

    return failures
