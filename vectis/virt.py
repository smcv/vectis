# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging
import os
import shutil
import subprocess
import urllib.parse
from contextlib import ExitStack

_WRAPPER = os.path.join(os.path.dirname(__file__), 'vectis-command-wrapper')

logger = logging.getLogger(__name__)

class Machine:
    def __init__(self, builder):
        self.__command_wrapper_enabled = False
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
            raise ValueError('virtualization provider %r not found' %
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
            raise ValueError('response to startup was %r' % line)

        self.virt_process.stdin.write('capabilities\n')
        self.virt_process.stdin.flush()
        line = self.virt_process.stdout.readline().split()

        if line[0] != 'ok':
            raise ValueError('response to capabilities was %r' % line)

        for word in line[1:]:
            self.capabilities.add(word)
            if word.startswith('suggested-normal-user='):
                self.user = word[len('suggested-normal-user='):]

        assert 'root-on-testbed' in self.capabilities, line
        assert ('isolation-machine' in self.capabilities or
                'isolation-container' in self.capabilities), line

        self.virt_process.stdin.write('open\n')
        self.virt_process.stdin.flush()
        line = self.virt_process.stdout.readline()
        assert line.startswith('ok ')
        self.scratch = line[3:].rstrip('\n')

        self.virt_process.stdin.write('print-execute-command\n')
        self.virt_process.stdin.flush()
        line = self.virt_process.stdout.readline().split()
        assert line[0] == 'ok'

        argv = line[1].split(',')

        self.call_argv = list(map(urllib.parse.unquote, argv))
        assert self.call_argv

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

    def copy_to_guest(self, host_path, guest_path):
        self.virt_process.stdin.write('copydown {} {}\n'.format(
            urllib.parse.quote(host_path),
            urllib.parse.quote(guest_path),
            ))
        self.virt_process.stdin.flush()
        line = self.virt_process.stdout.readline()
        assert line == 'ok\n'

    def copy_to_host(self, guest_path, host_path):
        self.virt_process.stdin.write('copyup {} {}\n'.format(
            urllib.parse.quote(guest_path),
            urllib.parse.quote(host_path),
            ))
        self.virt_process.stdin.flush()
        line = self.virt_process.stdout.readline()
        assert line == 'ok\n'

    def open_shell(self):
        self.virt_process.stdin.write('shell\n')
        self.virt_process.stdin.flush()
        line = self.virt_process.stdout.readline()
        if line != 'ok\n':
            logger.warning('Unable to open a shell in guest')

    def __exit__(self, et, ev, tb):
        return self.stack.__exit__(et, ev, tb)
