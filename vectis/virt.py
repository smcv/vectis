# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging
import os
import shutil
import subprocess
import urllib.parse
from contextlib import ExitStack

from vectis.error import (
        Error,
        )

_WRAPPER = os.path.join(os.path.dirname(__file__), 'vectis-command-wrapper')

logger = logging.getLogger(__name__)

class MachineError(Error):
    pass

class Machine:
    def __init__(self, builder):
        self.__cached_copies = {}
        self.__command_wrapper_enabled = False
        self.__dpkg_architecture = None
        self.call_argv = None
        self.capabilities = set()
        self.command_wrapper = None
        self.builder = builder
        self.stack = ExitStack()
        self.user = 'user'
        self.virt_process = None

    def __enter__(self):
        argv = list(map(os.path.expanduser, self.builder.split()))

        for prefix in ('autopkgtest-virt-', 'adt-virt-', ''):
            if shutil.which(prefix + argv[0]):
                argv[0] = prefix + argv[0]
                break
        else:
            raise MachineError('virtualization provider %r not found' %
                             argv[0])

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
            raise MachineError('Virtual machine {!r} failed to start: '
                    '{}'.format(argv, line.strip()))

        self.virt_process.stdin.write('capabilities\n')
        self.virt_process.stdin.flush()
        line = self.virt_process.stdout.readline()

        if not line.startswith('ok '):
            raise MachineError('Virtual machine {!r} failed to report '
                'capabilities: {}'.format(line.strip()))

        for word in line.split()[1:]:
            self.capabilities.add(word)
            if word.startswith('suggested-normal-user='):
                self.user = word[len('suggested-normal-user='):]

        if 'root-on-testbed' not in self.capabilities:
            raise MachineError('Virtual machine {!r} does not have '
                    'root-on-testbed capability: {}'.format(argv, line.strip()))

        if ('isolation-machine' not in self.capabilities and
                'isolation-container' not in self.capabilities):
            raise MachineError('Virtual machine {!r} does not have '
                    'sufficient isolation: {}'.format(argv, line.strip()))

        self.virt_process.stdin.write('open\n')
        self.virt_process.stdin.flush()
        line = self.virt_process.stdout.readline()
        if not line.startswith('ok '):
            raise MachineError('Failed to open virtual machine session {!r}: '
                    '{}'.format(argv, line))
        self.scratch = line[3:].rstrip('\n')

        self.virt_process.stdin.write('print-execute-command\n')
        self.virt_process.stdin.flush()
        line = self.virt_process.stdout.readline()
        if not line.startswith('ok '):
            raise MachineError('Failed to get virtual machine {!r} command '
                    'wrapper: {}'.format(argv, line.strip()))

        wrapper_argv = line.rstrip('\n').split(None, 1)[1].split(',')
        self.call_argv = list(map(urllib.parse.unquote, wrapper_argv))
        if not self.call_argv:
            raise MachineError('Virtual machine {!r} command wrapper did not '
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

    def copy_to_guest(self, host_path, guest_path, *, cache=False):
        assert host_path is not None
        assert guest_path is not None

        if cache and self.__cached_copies.get(host_path) == guest_path:
            return

        self.virt_process.stdin.write('copydown {} {}\n'.format(
            urllib.parse.quote(host_path),
            urllib.parse.quote(guest_path),
            ))
        self.virt_process.stdin.flush()
        line = self.virt_process.stdout.readline()

        if line != 'ok\n':
            raise MachineError('Failed to copy host:{!r} to guest:{!r}: '
                    '{}'.format(host_path, guest_path, line.strip()))

        if cache:
            self.__cached_copies[host_path] = guest_path

    def copy_to_host(self, guest_path, host_path):
        self.virt_process.stdin.write('copyup {} {}\n'.format(
            urllib.parse.quote(guest_path),
            urllib.parse.quote(host_path),
            ))
        self.virt_process.stdin.flush()
        line = self.virt_process.stdout.readline()
        if line != 'ok\n':
            raise MachineError('Failed to copy guest:{!r} to host:{!r}: '
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
