# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import logging
import os
import textwrap
from contextlib import (
        ExitStack,
        )
from tempfile import (
        TemporaryDirectory,
        )

from vectis.worker import (
        AutopkgtestWorker,
        HostWorker,
        )
from vectis.util import (
        AtomicWriter,
        )

logger = logging.getLogger(__name__)

def run_autopkgtest(args, *,
        suite,
        vendor,
        architecture=None,
        binaries=(),
        extra_repositories=(),
        sbuild_worker=None,
        source_changes=None,
        source_package=None):
    all_ok = True

    for test in args.autopkgtest:
        with ExitStack() as stack:
            worker = None

            if test == 'qemu':
                image = args.autopkgtest_qemu_image

                if not image or not os.path.exists(image):
                    continue

                virt = ['qemu', image]

            elif test == 'schroot':
                tarball = os.path.join(
                        args.storage,
                        architecture,
                        str(vendor),
                        str(suite.hierarchy[-1]),
                        'minbase.tar.gz')

                if not tarball or not os.path.exists(tarball):
                    continue

                # FIXME: also allow testing i386 on amd64, etc.
                if sbuild_worker.dpkg_architecture == architecture:
                    worker = sbuild_worker
                else:
                    # FIXME: run new worker if needed
                    logger.warning('Worker {} cannot test {}'.format(
                        sbuild_worker, architecture))
                    continue

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
                            tarball=worker.make_file_available(tarball)))
                    worker.copy_to_guest(os.path.join(tmp, 'sbuild.conf'),
                            '/etc/schroot/chroot.d/autopkgtest')

                virt = ['schroot', 'autopkgtest']
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
                virt=virt,
                worker=worker,
                ))

        argv = ['--no-built-binaries']

        for b in binaries:
            if b.endswith('.changes'):
                argv.append(worker.make_changes_file_available(b))
            else:
                argv.append(worker.make_file_available(b))

        if source_changes is not None:
            argv.append(worker.make_changes_file_available(source_changes))
        elif source_package is not None:
            argv.append(source_package)
        else:
            logger.warning('Nothing to test')
            continue

        if not autopkgtest.call_autopkgtest(argv):
            all_ok = False

    return all_ok
