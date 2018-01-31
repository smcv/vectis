# Copyright © 2017 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)


class AptSource:

    def __init__(
            self,
            other=None,
            *,
            components=None,
            suite=None,
            trusted=None,
            type=None,
            uri=None):
        assert type in (None, 'deb', 'deb-src'), type
        assert not isinstance(components, str), components
        # TODO: If other is a str, parse it
        assert other is None or isinstance(other, AptSource)

        if components is None:
            components = other.components

        if suite is None:
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

        if uri is None:
            uri = other.uri

        assert isinstance(suite, str)
        assert isinstance(type, str)
        assert isinstance(uri, str)

        self.components = set(components)
        self.suite = suite
        self.trusted = bool(trusted)
        self.type = type
        self.uri = uri

    def __str__(self):
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
        options = []
        option_str = ''

        if self.trusted:
            options.append('trusted=yes')

        if options:
            option_str = '[' + ' '.join(options) + '] '

        return '{}{} {} {}'.format(
            option_str,
            self.uri,
            ' '.join(self.components),
        )
