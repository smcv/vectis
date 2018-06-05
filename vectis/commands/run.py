# Copyright © 2016-2017 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging
import os
import subprocess
import time
from contextlib import suppress

from vectis.error import ArgumentError
from vectis.worker import (
    VirtWorker,
)

logger = logging.getLogger(__name__)

_1M = 1024 * 1024


def run(args):
    if args.suite is None:
        if args.default_suite is not None:
            args.suite = args.default_suite
        else:
            raise ArgumentError('--suite must be specified')

    apt_update = args._apt_update
    argv = args._argv
    chdir = args._chdir
    mirrors = args.get_mirrors()
    input_ = args._input
    output_dir = args.output_dir
    output_parent = args.output_parent
    qemu_image = args.qemu_image
    qemu_ram_size = args.qemu_ram_size
    shell_command = args._shell_command
    storage = args.storage
    suite = args.suite
    timestamp = time.strftime('%Y%m%dt%H%M%S', time.gmtime())

    if output_dir is None:
        output_dir = os.path.join(
            output_parent, 'vectis-run_{}'.format(timestamp))

        with suppress(FileNotFoundError):
            os.rmdir(output_dir)

        os.mkdir(output_dir)

    if shell_command is None and not argv:
        raise ArgumentError(
            'Usage: vectis run -- PROGRAM [$1 [$2...]] or vectis run '
            '-c "shell one-liner" [$0 [$1 [$2...]]]')

    for suite in (suite,):
        for ancestor in suite.hierarchy:
            mirror = mirrors.lookup_suite(ancestor)
            if mirror is None:
                raise ArgumentError(
                    'No mirror configured for {}'.format(ancestor))
    virt = ['qemu']

    if qemu_ram_size is not None:
        virt.append('--ram-size={}'.format(qemu_ram_size // _1M))

    virt.append(qemu_image)

    with VirtWorker(
            virt,
            apt_update=apt_update,
            mirrors=mirrors,
            storage=storage,
            suite=suite,
    ) as worker:
        worker_input = worker.scratch + '/in'
        temp = worker.scratch + '/tmp'
        artifacts = worker.scratch + '/out'
        worker.check_call(['mkdir', artifacts, worker_input, temp])

        if chdir == 'in':
            chdir = worker_input
        elif chdir == 'out':
            chdir = artifacts
        elif chdir == 'tmp':
            chdir = temp
        elif chdir[0] != '/' and chdir != '.':
            raise ArgumentError(
                "Argument to --chdir must be 'in', 'out', 'tmp', "
                "'.' or absolute")

        wrapper = [
            'sh',
            '-c',
            'cd "$1" && shift && exec "$@"',
            'sh',
            chdir,
            'env',
            'AUTOPKGTEST_ARTIFACTS={}'.format(artifacts),
            'ADT_ARTIFACTS={}'.format(artifacts),
            'VECTIS_OUT={}'.format(artifacts),
            'VECTIS_TMP={}'.format(temp),
            'AUTOPKGTEST_TMP={}'.format(temp),
            'ADTTMP={}'.format(temp),
        ]

        if input_ is not None:
            if os.path.isdir(input_):
                worker.copy_to_guest(
                    os.path.join(input_, ''), worker_input + '/')
            else:
                worker_input = worker_input + '/' + os.path.basename(input_)
                worker.copy_to_guest(input_, worker_input)

            wrapper.append('VECTIS_IN={}'.format(worker_input))

        try:
            if shell_command is not None:
                worker.check_call(wrapper + ['sh', '-c', shell_command] + argv)
            else:
                worker.check_call(wrapper + argv)
        finally:
            if worker.call(
                    ['rmdir', artifacts], stderr=subprocess.DEVNULL) == 0:
                logger.info('Command produced no artifacts')
                os.rmdir(output_dir)
            else:
                worker.copy_to_host(
                    artifacts + '/', os.path.join(output_dir, ''))
                logger.info(
                    'Artifacts produced by command are in %s', output_dir)
