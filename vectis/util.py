# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import contextlib
import logging
import os

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def AtomicWriter(fn, *a, **k):
    try:
        with open(fn + '.tmp', 'x', *a, **k) as f:
            yield f
    except:
        try:
            os.unlink(fn + '.tmp')
        except Exception as e:
            logger.warning('Could not unlink "%s.tmp": %s', fn, e)
        raise
    else:
        os.rename(fn + '.tmp', fn)
