# Copyright © 2016-2017 Simon McVittie
# Copyright © 2017 Collabora Ltd.
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging
import os
import shutil
import subprocess
import textwrap
import uuid
import urllib.parse
from abc import abstractmethod, ABCMeta
from contextlib import ExitStack
from tempfile import TemporaryDirectory

from debian.deb822 import (
    Changes,
    Dsc,
)
from debian.debian_support import (
    Version,
)

from vectis.apt import (
    AptSource,
)
from vectis.error import (
    Error,
)
from vectis.util import (
    AtomicWriter,
)

_WRAPPER = os.path.join(os.path.dirname(__file__), 'vectis-command-wrapper')

logger = logging.getLogger(__name__)


class WorkerError(Error):
    pass


class BaseWorker(metaclass=ABCMeta):

    def __init__(self, *, mirrors=None):
        super().__init__()
        self.__open = 0
        self.stack = ExitStack()

    def assert_open(self):
        assert self.__open

    def __enter__(self):
        self.__open += 1

        if self.__open == 1:
            self._open()

        return self

    def _open(self):
        pass

    def __exit__(self, et, ev, tb):
        self.__open -= 1
        if self.__open:
            return False
        else:
            return self.stack.__exit__(et, ev, tb)


class ContainerWorker(BaseWorker, metaclass=ABCMeta):

    def __init__(self, *, mirrors, suite):
        super().__init__()
        self.components = ()
        self.extra_repositories = ()
        self.mirrors = mirrors
        self.suite = suite

    @abstractmethod
    def install_apt_key(self, apt_key):
        raise NotImplementedError

    def install_apt_keys(self):
        assert self.suite is not None

        for ancestor in self.suite.hierarchy:
            if ancestor.apt_key is not None:
                self.install_apt_key(ancestor.apt_key)

    @abstractmethod
    def set_up_apt(self):
        raise NotImplementedError

    def write_sources_list(self, writer):
        assert self.mirrors is not None
        assert self.suite is not None

        for ancestor in self.suite.hierarchy:
            if self.components:
                filtered_components = (
                    set(self.components) & set(ancestor.all_components))
            else:
                filtered_components = ancestor.components

            uri = self.mirrors.lookup_suite(ancestor)

            for type in ('deb', 'deb-src'):
                source = AptSource(
                    components=filtered_components,
                    suite=ancestor.apt_suite,
                    type=type,
                    trusted=ancestor.apt_trusted,
                    uri=uri,
                )
                logger.info('%r: %s => %s', self, ancestor, source)
                writer.write('{}\n'.format(source))

        for line in self.extra_repositories:
            writer.write('{}\n'.format(line))


class FileProvider(BaseWorker, metaclass=ABCMeta):

    @abstractmethod
    def make_file_available(
            self,
            filename,
            *,
            cache=False,
            in_dir=None,
            owner=None):
        raise NotImplementedError

    @abstractmethod
    def new_directory(self, prefix='', tmpdir=None):
        raise NotImplementedError

    @abstractmethod
    def make_changes_file_available(self, filename, owner=None):
        raise NotImplementedError

    @abstractmethod
    def make_dsc_file_available(self, filename, owner=None):
        raise NotImplementedError


class InteractiveWorker(BaseWorker, metaclass=ABCMeta):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dpkg_architecture = None

    def call(self, argv, **kwargs):
        raise NotImplementedError

    def check_call(self, argv, **kwargs):
        raise NotImplementedError

    def check_output(self, argv, **kwargs):
        raise NotImplementedError

    def dpkg_version(self, package):
        v = self.check_output(
            ['dpkg-query', '-W', '-f${Version}', package],
            universal_newlines=True).rstrip('\n')
        return Version(v)

    @property
    def dpkg_architecture(self):
        if self.__dpkg_architecture is None:
            self.__dpkg_architecture = self.check_output(
                ['dpkg', '--print-architecture'],
                universal_newlines=True).strip()

        return self.__dpkg_architecture


class HostWorker(InteractiveWorker, FileProvider):

    def __init__(self):
        super().__init__()

    def call(self, argv, **kwargs):
        logger.info('%r: %r', self, argv)
        return subprocess.call(argv, **kwargs)

    def check_call(self, argv, **kwargs):
        logger.info('%r: %r', self, argv)
        subprocess.check_call(argv, **kwargs)

    def check_output(self, argv, **kwargs):
        logger.info('%r: %r', self, argv)
        return subprocess.check_output(argv, **kwargs)

    def make_file_available(
            self,
            filename,
            *,
            cache=False,
            in_dir=None,
            owner=None):
        return filename

    def new_directory(self, prefix='', tmpdir=None):
        if not prefix:
            prefix = 'vectis-'

        return self.stack.enter_context(
            self, TemporaryDirectory(prefix=prefix))

    def make_dsc_file_available(self, filename, owner=None):
        return (
            os.path.dirname(filename) or os.curdir,
            os.path.basename(filename),
        )

    def make_changes_file_available(self, filename, owner=None):
        return (
            os.path.dirname(filename) or os.curdir,
            os.path.basename(filename),
        )


class SchrootWorker(ContainerWorker, InteractiveWorker):

    def __init__(
            self,
            *,
            architecture,
            mirrors,
            suite,
            worker,
            chroot=None,
            components=(),
            extra_repositories=(),
            storage=None,
            tarball=None):
        super().__init__(mirrors=mirrors, suite=suite)

        if chroot is None:
            chroot = '{}-{}-{}'.format(suite.vendor, suite, architecture)

        if tarball is None:
            assert storage is not None

            tarball = os.path.join(
                storage, architecture, str(suite.hierarchy[-1].vendor),
                str(suite.hierarchy[-1]), 'sbuild.tar.gz')

        self.chroot = chroot
        self.components = components
        self.__dpkg_architecture = architecture
        self.extra_repositories = extra_repositories
        self.tarball = tarball
        self.worker = worker

        # We currently assume that copy_to_guest() works, and that we can
        # write in /etc/schroot/
        assert isinstance(self.worker, VirtWorker)

    @property
    def dpkg_architecture(self):
        if self.__dpkg_architecture is not None:
            return self.__dpkg_architecture
        else:
            return super().dpkg_architecture

    def _open(self):
        super()._open()
        self.set_up_apt()

    def set_up_apt(self):
        tarball_in_guest = self.worker.make_file_available(
            self.tarball, cache=True)

        tmp = TemporaryDirectory(prefix='vectis-worker-')
        tmp = self.stack.enter_context(tmp)
        sources_list = os.path.join(tmp, 'sources.list')

        with AtomicWriter(sources_list) as writer:
            self.write_sources_list(writer)
        self.worker.check_call(['mkdir', '-p', '/etc/schroot/sources.list.d'])
        self.worker.copy_to_guest(
            sources_list,
            '/etc/schroot/sources.list.d/{}'.format(self.chroot))

        with AtomicWriter(os.path.join(tmp, 'sbuild.conf')) as writer:
            writer.write(textwrap.dedent('''
            [{chroot}]
            type=file
            description=An autobuilder
            file={tarball_in_guest}
            groups=root,sbuild
            root-groups=root,sbuild
            profile=sbuild
            ''').format(
                chroot=self.chroot,
                tarball_in_guest=tarball_in_guest))
        self.worker.copy_to_guest(
            os.path.join(tmp, 'sbuild.conf'),
            '/etc/schroot/chroot.d/{}'.format(self.chroot))

        with AtomicWriter(os.path.join(tmp, '60vectis-sources')) as writer:
            writer.write(textwrap.dedent('''\
            #!/bin/sh
            set -e
            set -u
            if [ $1 = setup-start ] || [ $1 = setup-recover ]; then
                echo "$0: Setting up ${CHROOT_ALIAS}" >&2

                if [ -f /etc/schroot/sources.list.d/${CHROOT_ALIAS} ]; then
                    echo "$0: Copying" \
                        "/etc/schroot/sources.list.d/${CHROOT_ALIAS}" \
                        "into ${CHROOT_PATH}" >&2
                    cp /etc/schroot/sources.list.d/${CHROOT_ALIAS} \
                        ${CHROOT_PATH}/etc/apt/sources.list
                fi
                if [ -d /etc/schroot/apt-keys.d/${CHROOT_ALIAS} ]; then
                    echo "$0: Copying" \
                        "/etc/schroot/apt-keys.d/${CHROOT_ALIAS}/" \
                        "into ${CHROOT_PATH}" >&2
                    cp /etc/schroot/apt-keys.d/${CHROOT_ALIAS}/* \
                        ${CHROOT_PATH}/etc/apt/trusted.gpg.d/
                fi
            fi
            '''))
        self.worker.copy_to_guest(
            os.path.join(tmp, '60vectis-sources'),
            '/etc/schroot/setup.d/60vectis-sources')
        self.worker.check_call(
            ['chmod', '0755', '/etc/schroot/setup.d/60vectis-sources'])
        self.install_apt_keys()

    def install_apt_key(self, apt_key):
        self.worker.check_call(
            ['mkdir', '-p', '/etc/schroot/apt-keys.d/{}'.format(self.chroot)])
        self.worker.copy_to_guest(
            apt_key, '/etc/schroot/apt-keys.d/{}/{}-{}'.format(
                self.chroot, uuid.uuid4(), os.path.basename(apt_key)))

    def call(self, argv, **kwargs):
        return self.worker.call([
            'schroot', '-c', self.chroot,
            '--',
        ] + list(argv), **kwargs)

    def check_call(self, argv, **kwargs):
        return self.worker.check_call([
            'schroot', '-c', self.chroot,
            '--',
        ] + list(argv), **kwargs)

    def check_output(self, argv, **kwargs):
        return self.worker.check_output([
            'schroot', '-c', self.chroot,
            '--',
        ] + list(argv), **kwargs)


class VirtWorker(InteractiveWorker, ContainerWorker, FileProvider):

    def __init__(
            self,
            argv,
            *,
            mirrors,
            storage,
            suite,
            apt_update=True,
            components=(),
            extra_repositories=()):
        super().__init__(mirrors=mirrors, suite=suite)

        self.__cached_copies = {}
        self.__command_wrapper_enabled = False
        self.apt_update = apt_update
        self.argv = argv
        self.call_argv = None
        self.capabilities = set()
        self.command_wrapper = None
        self.components = components
        self.extra_repositories = extra_repositories
        self.user = 'user'
        self.virt_process = None

    def __repr__(self):
        return '<{} {}>'.format(self.__class__.__name__, self.argv)

    def _open(self):
        super()._open()
        argv = list(map(os.path.expanduser, self.argv))

        for prefix in ('autopkgtest-virt-', 'adt-virt-', ''):
            if shutil.which(prefix + argv[0]):
                argv[0] = prefix + argv[0]
                break
        else:
            raise WorkerError('virtualization provider %r not found' % argv[0])

        logger.info('Starting worker: %r', argv)
        self.virt_process = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            universal_newlines=True)
        self.stack.enter_context(self.virt_process)
        self.stack.callback(self.virt_process.terminate)
        # FIXME: timed wait for a response?
        self.stack.callback(self.virt_process.stdin.flush)
        self.stack.callback(self.virt_process.stdin.write, 'quit\n')

        line = self.virt_process.stdout.readline()

        if line != 'ok\n':
            raise WorkerError('Virtual machine {!r} failed to start: '
                              '{}'.format(argv, line.strip()))

        self.virt_process.stdin.write('capabilities\n')
        self.virt_process.stdin.flush()
        line = self.virt_process.stdout.readline()

        if not line.startswith('ok '):
            raise WorkerError(
                'Virtual machine {!r} failed to report capabilities: '
                '{}'.format(line.strip()))

        for word in line.split()[1:]:
            self.capabilities.add(word)
            if word.startswith('suggested-normal-user='):
                self.user = word[len('suggested-normal-user='):]

        if 'root-on-testbed' not in self.capabilities:
            raise WorkerError(
                'Virtual machine {!r} does not have root-on-testbed '
                'capability: {}'.format(argv, line.strip()))

        if ('isolation-machine' not in self.capabilities and
                'isolation-container' not in self.capabilities):
            raise WorkerError(
                'Virtual machine {!r} does not have sufficient isolation: '
                '{}'.format(argv, line.strip()))

        self.virt_process.stdin.write('open\n')
        self.virt_process.stdin.flush()
        line = self.virt_process.stdout.readline()
        if not line.startswith('ok '):
            raise WorkerError(
                'Failed to open virtual machine session '
                '{!r}: {}'.format(argv, line))
        self.scratch = line[3:].rstrip('\n')

        self.virt_process.stdin.write('print-execute-command\n')
        self.virt_process.stdin.flush()
        line = self.virt_process.stdout.readline()
        if not line.startswith('ok '):
            raise WorkerError(
                'Failed to get virtual machine {!r} command '
                'wrapper: {}'.format(argv, line.strip()))

        wrapper_argv = line.rstrip('\n').split(None, 1)[1].split(',')
        self.call_argv = list(map(urllib.parse.unquote, wrapper_argv))
        if not self.call_argv:
            raise WorkerError(
                'Virtual machine {!r} command wrapper did not provide any '
                'arguments: {}'.format(argv, line.strip()))

        wrapper = '{}/vectis-command-wrapper'.format(self.scratch)
        self.copy_to_guest(_WRAPPER, wrapper)
        self.check_call(['chmod', '+x', wrapper])
        self.command_wrapper = wrapper

        self.set_up_apt()

    def call(self, argv, **kwargs):
        logger.info('%r: %r', self, argv)
        return subprocess.call(self.call_argv + list(argv), **kwargs)

    def check_call(self, argv, **kwargs):
        logger.info('%r: %r', self, argv)
        subprocess.check_call(self.call_argv + list(argv), **kwargs)

    def check_output(self, argv, **kwargs):
        logger.info('%r: %r', self, argv)
        return subprocess.check_output(self.call_argv + list(argv), **kwargs)

    def copy_to_guest(self, host_path, guest_path, *, cache=False):
        assert host_path is not None
        assert guest_path is not None

        if cache and self.__cached_copies.get(host_path) == guest_path:
            logger.info(
                'host:%s is already available at guest:%s, not copying again',
                host_path, guest_path,
            )
            return

        logger.info('Copying host:%s to guest:%s', host_path, guest_path)

        if not os.path.exists(host_path):
            raise WorkerError(
                'Cannot copy host:{!r} to guest: it does not '
                'exist'.format(host_path))

        if os.path.isdir(host_path):
            suffix = '/'
        else:
            suffix = ''

        self.virt_process.stdin.write('copydown {}{} {}{}\n'.format(
            urllib.parse.quote(host_path),
            suffix,
            urllib.parse.quote(guest_path),
            suffix,
        ))
        self.virt_process.stdin.flush()
        line = self.virt_process.stdout.readline()

        if line != 'ok\n':
            raise WorkerError(
                'Failed to copy host:{!r} to guest:{!r}: {}'.format(
                    host_path, guest_path, line.strip()))

        if cache:
            self.__cached_copies[host_path] = guest_path

    def copy_to_host(self, guest_path, host_path):
        if self.call(['test', '-e', guest_path]) != 0:
            raise WorkerError(
                'Cannot copy guest:{!r} to host: it does not exist'.format(
                    guest_path))

        logger.info('Copying guest:{} to host:{}'.format(
            guest_path, host_path))

        self.virt_process.stdin.write('copyup {} {}\n'.format(
            urllib.parse.quote(guest_path),
            urllib.parse.quote(host_path),
        ))
        self.virt_process.stdin.flush()
        line = self.virt_process.stdout.readline()
        if line != 'ok\n':
            raise WorkerError(
                'Failed to copy guest:{!r} to host:{!r}: {}'.format(
                    guest_path, host_path, line.strip()))

    def open_shell(self):
        self.virt_process.stdin.write('shell\n')
        self.virt_process.stdin.flush()
        line = self.virt_process.stdout.readline()
        if line != 'ok\n':
            logger.warning('Unable to open a shell in guest: %s', line.strip())

    def set_up_apt(self):
        logger.info('Configuring apt in %r for %s', self, self.suite)

        with TemporaryDirectory(prefix='vectis-worker-') as tmp:
            sources_list = os.path.join(tmp, 'sources.list')

            with AtomicWriter(sources_list) as writer:
                self.write_sources_list(writer)

            self.copy_to_guest(sources_list, '/etc/apt/sources.list')

        self.install_apt_keys()

        if self.apt_update:
            self.check_call([
                'env', 'DEBIAN_FRONTEND=noninteractive',
                'apt-get', '-y', 'update',
            ])

    def install_apt_key(self, apt_key):
        self.copy_to_guest(
            apt_key,
            '/etc/apt/trusted.gpg.d/{}-{}'.format(
                uuid.uuid4(), os.path.basename(apt_key)))

    def make_file_available(
            self,
            filename,
            *,
            cache=False,
            in_dir=None,
            owner=None):
        if in_dir is None:
            in_dir = self.scratch

        if cache:
            in_guest = self.__cached_copies.get(filename)
            if (in_guest is not None and
                    os.path.commonpath([in_guest, in_dir]) == in_dir):
                return in_guest

        unique = str(uuid.uuid4())
        in_guest = '{}/{}/{}'.format(
            in_dir, unique, os.path.basename(filename))
        self.check_call(['mkdir', '{}/{}'.format(in_dir, unique)])
        self.copy_to_guest(filename, in_guest, cache=cache)

        if owner is not None:
            self.check_call([
                'chown', '-R', owner, '{}/{}'.format(in_dir, unique),
                in_guest,
            ])

        return in_guest

    def new_directory(self, prefix='', tmpdir=None):
        if not prefix:
            prefix = 'vectis-'

        if tmpdir is None:
            tmpdir = self.scratch

        d = self.check_output([
            'mktemp', '-d', '--tmpdir={}'.format(tmpdir),
            prefix + 'XXXXXXXXXX',
        ], universal_newlines=True).rstrip('\n')
        self.check_call(['chmod', '0755', d])
        return d

    def make_dsc_file_available(self, filename, owner=None):
        d = os.path.dirname(filename) or os.curdir

        with open(filename) as reader:
            dsc = Dsc(reader)

        to = self.new_directory()
        files = [to, '{}/{}'.format(to, os.path.basename(filename))]
        self.copy_to_guest(filename, files[-1])

        for f in dsc['files']:
            files.append('{}/{}'.format(to, f['name']))
            self.copy_to_guest(os.path.join(d, f['name']), files[-1])

        if owner is not None:
            self.check_call(['chown', owner] + files)

        return files[0], os.path.basename(filename)

    def make_changes_file_available(self, filename, owner=None):
        d = os.path.dirname(filename) or os.curdir

        with open(filename) as reader:
            changes = Changes(reader)

        to = self.new_directory()
        files = [to, '{}/{}'.format(to, os.path.basename(filename))]
        self.copy_to_guest(filename, files[-1])

        for f in changes['files']:
            files.append('{}/{}'.format(to, f['name']))
            self.copy_to_guest(os.path.join(d, f['name']), files[-1])

        if owner is not None:
            self.check_call(['chown', owner] + files)

        return files[0], os.path.basename(filename)
