# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

class Error(RuntimeError):
    pass

class ArgumentError(Error):
    pass

class CannotHappen(Error):
    pass
