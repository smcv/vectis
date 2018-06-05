# Copyright © 2017 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)


try:
    import typing
except ImportError:
    pass
else:
    from typing import (
        Iterable,
        Optional,
        Set,
    )
    typing      # silence pyflakes
    Iterable
    Optional
    Set


class AptSource:

    def __init__(
            self,
            other=None,                 # type: Optional[AptSource]
            *,
            components=None,            # type: Optional[Iterable[str]]
            suite=None,                 # type: Optional[str]
            trusted=None,               # type: Optional[bool]
            type=None,                  # type: Optional[str]
            uri=None,                   # type: Optional[str]
    ):
        # type: (...) -> None
        assert type in (None, 'deb', 'deb-src'), type
        assert not isinstance(components, str), components
        # TODO: If other is a str, parse it
        assert other is None or isinstance(other, AptSource)

        if components is None and other is not None:
            components = other.components

        if suite is None and other is not None:
            suite = other.suite

        if trusted is None:
            if other is None:
                trusted = False
            else:
                trusted = other.trusted

        if type is None:
            if other is None:
                type = 'deb'
            else:
                type = other.type

        if uri is None and other is not None:
            uri = other.uri

        assert isinstance(suite, str)
        assert isinstance(type, str)
        assert isinstance(uri, str)

        self.components = set(components or ())     # type: Set[str]
        self.suite = suite                          # type: str
        self.trusted = bool(trusted)                # type: bool
        self.type = type                            # type: str
        self.uri = uri                              # type: str

    def __str__(self):
        # type: () -> str
        options = []
        option_str = ''

        if self.trusted:
            options.append('trusted=yes')

        if options:
            option_str = '[' + ' '.join(options) + '] '

        return '{} {}{} {} {}'.format(
            self.type,
            option_str,
            self.uri,
            self.suite,
            ' '.join(self.components),
        )

    def get_piuparts_mirror_option(self):
        # type: () -> str
        options = []
        option_str = ''

        if self.trusted:
            options.append('trusted=yes')

        if options:
            option_str = '[' + ' '.join(options) + '] '

        return '{}{} {}'.format(
            option_str,
            self.uri,
            ' '.join(self.components),
        )
