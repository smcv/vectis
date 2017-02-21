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
            source_changes=None,
            source_package=None):
        argv = self.argv[:]

        for b in binaries:
            if b.endswith('.changes'):
                argv.append(self.worker.make_changes_file_available(b))
            else:
                argv.append(self.worker.make_file_available(b))

        if source_changes is not None:
            argv.append(self.worker.make_changes_file_available(source_changes))
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

    def make_file_available(self, filename, unique=None, ext=None,
            cache=False):
        if cache:
            in_guest = self.__cached_copies.get(filename)
            if in_guest is not None:
                return in_guest

        if unique is None:
            unique = str(uuid.uuid4())

        if ext is None:
            basename, ext = os.path.splitext(filename)

            if basename.endswith('.tar'):
                ext = '.tar' + ext

        filename = self.worker.make_file_available(filename,
                unique, ext, cache=cache)
        in_autopkgtest = '/tmp/{}{}'.format(unique, ext)
        self.argv.append('--copy={}:{}'.format(filename, in_autopkgtest))

        if cache:
            self.__cached_copies[filename] = in_autopkgtest

        return in_autopkgtest

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

def run_autopkgtest(args, *,
        suite,
        vendor,
        architecture=None,
        binaries=(),
        extra_repositories=(),
        source_changes=None,
        source_package=None):
    all_ok = True

    logger.info('Testing in modes: %r', args.autopkgtest)

    for test in args.autopkgtest:
        logger.info('Testing in mode: %s', test)
        with ExitStack() as stack:
            worker = None

            if test == 'qemu':
                image = os.path.join(
                    args.storage,
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
                        args.storage,
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
                        args.worker.split(),
                        suite=args.worker_suite,
                        ))

                worker.check_call([
                    'env',
                    'DEBIAN_FRONTEND=noninteractive',
                    'apt-get',
                    '-y',
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
                        args.storage,
                        architecture,
                        str(vendor),
                        str(suite.hierarchy[-1]),
                        'lxc-rootfs.tar.gz')
                meta = os.path.join(
                        args.storage,
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
                        args.lxc_worker.split(),
                        suite=args.lxc_worker_suite,
                        ))

                worker.check_call([
                    'env',
                    'DEBIAN_FRONTEND=noninteractive',
                    'apt-get',
                    '-y',
                    'install',

                    'autopkgtest',
                    'lxc',
                    'python3',
                    ])
                set_up_lxc_net(worker, args.lxc_24bit_subnet)
                worker.check_call(['mkdir', '-p',
                    '/var/lib/lxc/vectis-new/rootfs'])
                worker.copy_to_guest(
                    os.path.join(args.storage, rootfs),
                    '{}/rootfs.tar.gz'.format(worker.scratch))
                worker.check_call(['tar', '-x', '-z',
                    '-C', '/var/lib/lxc/vectis-new/rootfs',
                    '-f', '{}/rootfs.tar.gz'.format(worker.scratch)])
                worker.check_call(['rm', '-f',
                    '{}/rootfs.tar.gz'.format(worker.scratch)])
                worker.copy_to_guest(
                    os.path.join(args.storage, meta),
                    '{}/meta.tar.gz'.format(worker.scratch))
                worker.check_call(['tar', '-x', '-z',
                    '-C', '/var/lib/lxc/vectis-new',
                    '-f', '{}/meta.tar.gz'.format(worker.scratch)])
                worker.check_call(['rm', '-f',
                    '{}/meta.tar.gz'.format(worker.scratch)])
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
                    components=args.components,
                    extra_repositories=extra_repositories,
                    mirror=args.mirror,
                    suite=suite,
                    worker=worker,
                    virt=virt,
                    ))

            if not autopkgtest.call_autopkgtest(
                    binaries=binaries,
                    source_changes=source_changes,
                    source_package=source_package,
                    ):
                all_ok = False

    return all_ok
