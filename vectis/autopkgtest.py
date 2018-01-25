# Copyright © 2016-2017 Simon McVittie
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
)
from vectis.util import (
    AtomicWriter,
)

logger = logging.getLogger(__name__)

_1M = 1024 * 1024


class AutopkgtestWorker(ContainerWorker, FileProvider):

    def __init__(
            self,
            mirrors,
            suite,
            components=(),
            extra_repositories=(),
            virt=(),
            worker=None):
        super().__init__(mirrors=mirrors, suite=suite)

        if worker is None:
            worker = self.stack.enter_context(HostWorker())

        self.__cached_copies = {}
        self.argv = ['autopkgtest', '--apt-upgrade']
        self.components = components
        self.extra_repositories = extra_repositories
        self.sources_list = None
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
        self.argv.append(
            '--copy={}:{}'.format(sources_list, '/etc/apt/sources.list'))
        self.install_apt_keys()

    def call_autopkgtest(
            self,
            *,
            binaries,
            built_binaries,
            output_dir=None,
            run_as=None,
            source_dsc=None,
            source_package=None):
        argv = self.argv[:]

        if not built_binaries:
            argv.append('-B')

        if output_dir is not None:
            argv.append('-o')
            argv.append(output_dir)

        for b in binaries:
            if b.endswith('.changes'):
                d, f = self.worker.make_changes_file_available(b, owner=run_as)
                argv.append('{}/{}'.format(d, f))
            else:
                argv.append(self.worker.make_file_available(
                    b, owner=run_as))

        if source_dsc is not None:
            d, f = self.worker.make_dsc_file_available(source_dsc, owner=run_as)
            argv.append('{}/{}'.format(d, f))
        elif source_package is not None:
            argv.append(source_package)
        else:
            logger.warning('Nothing to test')
            return False

        argv.append('--')
        argv.extend(self.virt)

        if run_as is not None:
            argv = ['runuser', '-u', run_as, '--'] + argv

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

    def new_directory(self, prefix='', tmpdir=None):
        if tmpdir is None:
            tmpdir = '/tmp'

        # assume /tmp is initially empty and uuid4() won't collide
        d = '{}/{}{}'.format(tmpdir, prefix, uuid.uuid4())
        self.argv.append('--setup-commands=mkdir {}'.format(shlex.quote(d)))
        return d

    def make_file_available(
            self,
            filename,
            *,
            cache=False,
            in_dir=None,
            owner=None):
        if cache:
            in_guest = self.__cached_copies.get(filename)
            if in_guest is not None:
                return in_guest

        if in_dir is None:
            in_dir = '/tmp'

        unique = str(uuid.uuid4())
        filename = self.worker.make_file_available(filename, cache=cache)

        in_autopkgtest = '{}/{}/{}'.format(
            in_dir, unique, os.path.basename(filename))
        self.argv.append('--copy={}:{}'.format(filename, in_autopkgtest))

        if cache:
            self.__cached_copies[filename] = in_autopkgtest

        return in_autopkgtest

    def make_dsc_file_available(self, filename, owner=None):
        d = os.path.dirname(filename) or os.curdir

        with open(filename) as reader:
            dsc = Dsc(reader)

        to = self.new_directory()
        self.argv.append('--copy={}:{}'.format(
            filename, '{}/{}'.format(to, os.path.basename(filename))))

        for f in dsc['files']:
            self.argv.append(
                '--copy={}:{}'.format(
                    os.path.join(d, f['name']),
                    '{}/{}'.format(to, f['name'])))

        return to, os.path.basename(filename)

    def make_changes_file_available(self, filename, owner=None):
        d = os.path.dirname(filename) or os.curdir

        with open(filename) as reader:
            changes = Changes(reader)

        to = self.new_directory()
        self.argv.append('--copy={}:{}'.format(
            filename, '{}/{}'.format(to, os.path.basename(filename))))

        for f in changes['files']:
            self.argv.append('--copy={}:{}'.format(
                os.path.join(d, f['name']),
                '{}/{}'.format(to, f['name'])))

        return to, os.path.basename(filename)

    def _open(self):
        super()._open()
        self.set_up_apt()


def run_autopkgtest(
        *,
        components,
        mirrors,
        modes,
        storage,
        suite,
        vendor,
        worker,
        architecture=None,
        binaries=(),
        built_binaries=None,
        extra_repositories=(),
        lxc_24bit_subnet=None,
        lxc_worker=None,
        output_logs=None,
        qemu_ram_size=None,
        schroot_worker=None,
        source_dsc=None,
        source_package=None):
    failures = []

    if lxc_worker is None:
        lxc_worker = worker

    if schroot_worker is None:
        schroot_worker = worker

    logger.info('Testing in modes: %r', modes)

    for test in modes:
        logger.info('Testing in mode: %s', test)
        with ExitStack() as stack:
            run_as = None
            worker = None

            if output_logs is None:
                output_dir = None
            else:
                output_dir = os.path.join(
                    output_logs,
                    'autopkgtest_{}_{}'.format(test, architecture))

            if test == 'qemu':
                test = 'qemu:autopkgtest.qcow2'

            if test.startswith('qemu:'):
                image = os.path.join(
                    storage,
                    architecture,
                    str(vendor),
                    str(suite.hierarchy[-1]),
                    test[len('qemu:'):])

                if not image or not os.path.exists(image):
                    logger.info('Required image %s does not exist', image)
                    continue

                output_on_worker = output_dir
                virt = ['qemu']

                if qemu_ram_size is not None:
                    virt.append('--ram-size={}'.format(qemu_ram_size // _1M))

                virt.append(image)

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

                worker = stack.enter_context(schroot_worker)
                worker.check_call([
                    'env',
                    'DEBIAN_FRONTEND=noninteractive',
                    'apt-get',
                    '-y',
                    '-t', worker.suite.apt_suite,
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
                        groups=root,{user}
                        root-groups=root,{user}
                        profile=default
                        ''').format(
                            tarball=worker.make_file_available(
                                tarball, cache=True),
                            user=worker.user,
                        ))
                    worker.copy_to_guest(
                        os.path.join(tmp, 'sbuild.conf'),
                            '/etc/schroot/chroot.d/autopkgtest')

                output_on_worker = worker.new_directory()
                worker.check_call(['chown', worker.user, output_on_worker])
                run_as = worker.user
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

                worker=stack.enter_context(lxc_worker)
                worker.check_call([
                    'env',
                    'DEBIAN_FRONTEND=noninteractive',
                    'apt-get',
                    '-y',
                    '-t', lxc_worker.suite.apt_suite,
                    'install',

                    'autopkgtest',
                    'lxc',
                    'python3',
                ])
                set_up_lxc_net(worker, lxc_24bit_subnet)
                worker.check_call(['mkdir', '-p',
                                   '/var/lib/lxc/vectis-new/rootfs'])
                with open(rootfs, 'rb') as reader:
                    worker.check_call([
                        'tar', '-x', '-z',
                        '-C', '/var/lib/lxc/vectis-new/rootfs',
                        '-f', '-'], stdin=reader)
                with open(meta, 'rb') as reader:
                    worker.check_call([
                        'tar', '-x', '-z',
                        '-C', '/var/lib/lxc/vectis-new',
                        '-f', '-'], stdin=reader)
                worker.check_call([
                    'mv', '/var/lib/lxc/vectis-new',
                    '/var/lib/lxc/{}'.format(container)])

                # Make sure the container has an ordinary user to run tests;
                # autopkgtest auto-detects 'nobody' which doesn't have a
                # real home directory
                worker.check_call([
                    'chroot',
                    '/var/lib/lxc/{}/rootfs'.format(container),
                    'sh', '-c',
                        'if ! getent passwd user >/dev/null; then '
                            'apt-get -y install adduser && '
                            'adduser --disabled-password --shell=/bin/sh user '
                                '</dev/null; '
                        'fi'])

                output_on_worker = worker.new_directory()
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
                    mirrors=mirrors,
                    suite=suite,
                    virt=virt,
                    worker=worker,
                ))

            if not autopkgtest.call_autopkgtest(
                    binaries=binaries,
                    built_binaries=built_binaries,
                    output_dir=output_on_worker,
                    run_as=run_as,
                    source_dsc=source_dsc,
                    source_package=source_package,
            ):
                if output_dir is None:
                    failures.append(test)
                else:
                    failures.append(output_dir)

            if output_dir is not None and output_dir != output_on_worker:
                worker.copy_to_host(
                    os.path.join(output_on_worker, ''),
                    os.path.join(output_dir, ''))

    return failures
