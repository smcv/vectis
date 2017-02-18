# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging
import os
import shutil
import subprocess
import textwrap
import urllib.parse
from contextlib import ExitStack
from tempfile import TemporaryDirectory

from debian.debian_support import (
        Version,
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

class Worker:
    def __init__(self, argv):
        self.__cached_copies = {}
        self.__command_wrapper_enabled = False
        self.__dpkg_architecture = None
        self.call_argv = None
        self.capabilities = set()
        self.command_wrapper = None
        self.argv = argv
        self.stack = ExitStack()
        self.user = 'user'
        self.virt_process = None

    def __enter__(self):
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
            raise WorkerError('Virtual machine {!r} failed to report '
                'capabilities: {}'.format(line.strip()))

        for word in line.split()[1:]:
            self.capabilities.add(word)
            if word.startswith('suggested-normal-user='):
                self.user = word[len('suggested-normal-user='):]

        if 'root-on-testbed' not in self.capabilities:
            raise WorkerError('Virtual machine {!r} does not have '
                    'root-on-testbed capability: {}'.format(argv, line.strip()))

        if ('isolation-machine' not in self.capabilities and
                'isolation-container' not in self.capabilities):
            raise WorkerError('Virtual machine {!r} does not have '
                    'sufficient isolation: {}'.format(argv, line.strip()))

        self.virt_process.stdin.write('open\n')
        self.virt_process.stdin.flush()
        line = self.virt_process.stdout.readline()
        if not line.startswith('ok '):
            raise WorkerError('Failed to open virtual machine session {!r}: '
                    '{}'.format(argv, line))
        self.scratch = line[3:].rstrip('\n')

        self.virt_process.stdin.write('print-execute-command\n')
        self.virt_process.stdin.flush()
        line = self.virt_process.stdout.readline()
        if not line.startswith('ok '):
            raise WorkerError('Failed to get virtual machine {!r} command '
                    'wrapper: {}'.format(argv, line.strip()))

        wrapper_argv = line.rstrip('\n').split(None, 1)[1].split(',')
        self.call_argv = list(map(urllib.parse.unquote, wrapper_argv))
        if not self.call_argv:
            raise WorkerError('Virtual machine {!r} command wrapper did not '
                    'provide any arguments: {}'.format(argv, line.strip()))

        wrapper = '{}/vectis-command-wrapper'.format(self.scratch)
        self.copy_to_guest(_WRAPPER, wrapper)
        self.check_call(['chmod', '+x', wrapper])
        self.command_wrapper = wrapper

        return self

    def call(self, argv, **kwargs):
        logger.info('%r', argv)
        return subprocess.call(self.call_argv + list(argv), **kwargs)

    def check_call(self, argv, **kwargs):
        logger.info('%r', argv)
        subprocess.check_call(self.call_argv + list(argv), **kwargs)

    def check_output(self, argv, **kwargs):
        logger.info('%r', argv)
        return subprocess.check_output(self.call_argv + list(argv), **kwargs)

    def dpkg_version(self, package):
        v = self.check_output(['dpkg-query', '-W', '-f${Version}', package],
                universal_newlines=True).rstrip('\n')
        return Version(v)

    def copy_to_guest(self, host_path, guest_path, *, cache=False):
        assert host_path is not None
        assert guest_path is not None
        logger.info('Copying host:{} to guest:{}'.format(
            host_path, guest_path))

        if cache and self.__cached_copies.get(host_path) == guest_path:
            return

        if not os.path.exists(host_path):
            raise WorkerError('Cannot copy host:{!r} to guest: it does '
                    'not exist'.format(host_path))

        self.virt_process.stdin.write('copydown {} {}\n'.format(
            urllib.parse.quote(host_path),
            urllib.parse.quote(guest_path),
            ))
        self.virt_process.stdin.flush()
        line = self.virt_process.stdout.readline()

        if line != 'ok\n':
            raise WorkerError('Failed to copy host:{!r} to guest:{!r}: '
                    '{}'.format(host_path, guest_path, line.strip()))

        if cache:
            self.__cached_copies[host_path] = guest_path

    def copy_to_host(self, guest_path, host_path):
        if self.call(['test', '-e', guest_path]) != 0:
            raise WorkerError('Cannot copy guest:{!r} to host: it does '
                    'not exist'.format(guest_path))

        logger.info('Copying guest:{} to host:{}'.format(
            guest_path, host_path))

        self.virt_process.stdin.write('copyup {} {}\n'.format(
            urllib.parse.quote(guest_path),
            urllib.parse.quote(host_path),
            ))
        self.virt_process.stdin.flush()
        line = self.virt_process.stdout.readline()
        if line != 'ok\n':
            raise WorkerError('Failed to copy guest:{!r} to host:{!r}: '
                    '{}'.format(guest_path, host_path, line.strip()))

    def open_shell(self):
        self.virt_process.stdin.write('shell\n')
        self.virt_process.stdin.flush()
        line = self.virt_process.stdout.readline()
        if line != 'ok\n':
            logger.warning('Unable to open a shell in guest: %s', line.strip())

    @property
    def dpkg_architecture(self):
        if self.__dpkg_architecture is None:
            self.__dpkg_architecture = self.check_output(['dpkg',
                '--print-architecture'], universal_newlines=True).strip()

        return self.__dpkg_architecture

    def __exit__(self, et, ev, tb):
        return self.stack.__exit__(et, ev, tb)

    def set_up_apt(self, suite, components=()):
        with TemporaryDirectory(prefix='vectis-worker-') as tmp:
            with AtomicWriter(os.path.join(tmp, 'sources.list')) as writer:
                for ancestor in suite.hierarchy:
                    if components:
                        filtered_components = (set(components) &
                                set(ancestor.all_components))
                    else:
                        filtered_components = ancestor.components

                    writer.write(textwrap.dedent('''
                    deb {mirror} {suite} {components}
                    deb-src {mirror} {suite} {components}
                    ''').format(
                        components=' '.join(filtered_components),
                        mirror=ancestor.mirror,
                        suite=ancestor.apt_suite,
                    ))

                    if ancestor.apt_key is not None:
                        self.copy_to_guest(ancestor.apt_key,
                            '/etc/apt/trusted.gpg.d/' +
                            os.path.basename(ancestor.apt_key))

            self.copy_to_guest(os.path.join(tmp, 'sources.list'),
                    '/etc/apt/sources.list')
            self.check_call([
                'env', 'DEBIAN_FRONTEND=noninteractive',
                'apt-get', '-y', 'update',
                ])
