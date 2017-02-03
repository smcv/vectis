# Copyright © 2015-2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import os
import subprocess
from string import Template
from weakref import WeakValueDictionary

from vectis.error import Error

import yaml

class ConfigError(Error):
    pass

class RecursiveExpansionMap(dict):
    def __getitem__(self, k):
        v = super(RecursiveExpansionMap, self).__getitem__(k)
        return self.__expand(v)

    def __expand(self, v):
        if isinstance(v, str):
            return Template(v).substitute(self)
        elif isinstance(v, set):
            return set([self.__expand(x) for x in v])
        elif isinstance(v, list):
            return list([self.__expand(x) for x in v])
        elif isinstance(v, dict):
            ret = {}
            for k, x in v.items():
                ret[k] = self.__expand(x)
            return ret
        else:
            return v

DEFAULTS = '''
---
defaults:
    storage: "${XDG_CACHE_HOME}/vectis"
    vendor: debian
    size: 42G
    components: main
    extra_components: []
    archive: "${vendor}"
    mirror: "http://192.168.122.1:3142/${archive}"
    qemu_image: "vectis-${vendor}-${suite}-${architecture}.qcow2"
    debootstrap_script: "${suite}"
    default_suite: "${unstable_suite}"
    aliases: {}
    architecture: null
    stable_suite: null
    suite: null
    unstable_suite: null

    build_vendor: debian
    build_suite: null
    build_architecture: "${architecture}"
    builder: "autopkgtest-virt-qemu ${storage}/${builder_qemu_image}"
    builder_qemu_image: null

    bootstrap_mirror: "${mirror}"

    sbuild_force_parallel: 0
    parallel: null
    sbuild_together: false
    output_builds: ".."

    sbuild_buildables: null
    sbuild_resolver: []
    apt_suite: "${suite}"
    dpkg_source_tar_ignore: []
    dpkg_source_diff_ignore: null
    dpkg_source_extend_diff_ignore: []

vendors:
    debian:
        extra_components: contrib non-free
        suites:
            sid: {}
            unstable:
                alias_for: sid
            experimental:
                base: sid
                sbuild_resolver:
                    - "--build-dep-resolver=aspcud"
                    - "--aspcud-criteria=-removed,-changed,-new,-count(solution,APT-Release:=/experimental/)"
            rc-buggy:
                alias_for: experimental
            "*-backports":
                sbuild_resolver:
                    - "--build-dep-resolver=aptitude"
            "*-backports-sloppy":
                sbuild_resolver:
                    - "--build-dep-resolver=aptitude"
            # *-proposed-updates intentionally omitted because nobody is
            # meant to upload to it
            "*-security":
                mirror: "http://192.168.122.1:3142/security.debian.org"
                apt_suite: "${base}/updates"
            "*-updates":
                null: null

    ubuntu:
        build_suite: "${stable_suite}"
        build_vendor: ubuntu
        extra_components: universe restricted multiverse
        suites:
            "*-backports":
                null: null
            "*-proposed":
                null: null
            "*-security":
                null: null
            "*-updates":
                null: null

directories:
    /:
        # Directory-specific configuration has highest priority, do not put
        # anything in here by default. We configure '/' so that path search
        # always terminates.
        null: null
'''

class _ConfigLike:
    def __init__(self):
        self._raw = None

    def _get_string_set(self, name):
        value = self[name]

        if value is None:
            return set()
        elif isinstance(value, str):
            return set(value.split())
        else:
            return set(value)

    def _get_int(self, name):
        return int(self[name])

    @property
    def all_components(self):
        return self.components | self.extra_components

    @property
    def components(self):
        return self._get_string_set('components')

    @property
    def extra_components(self):
        return self._get_string_set('extra_components')

    @property
    def sbuild_force_parallel(self):
        return self._get_int('sbuild_force_parallel')

    @property
    def parallel(self):
        return self._get_int('parallel')

    @property
    def sbuild_together(self):
        return self._get_bool('sbuild_together')

    def _get_bool(self, name):
        value = self[name]

        if isinstance(value, bool):
            return value

        raise ConfigError('Invalid value for {!r}: {!r} is not a boolean '
                'value'.format(name, value))

    def _get_mandatory_string(self, name):
        value = self[name]

        if isinstance(value, str):
            return value

        raise ConfigError('{!r} key {!r} has no default and must be '
                'configured'.format(self, name))

    # FIXME: architecture and suite can't be mandatory like this because
    # we have to be able to say they're None as a way to mean "please guess"

    @property
    def unstable_suite(self):
        return self._get_mandatory_string('unstable_suite')

    @property
    def stable_suite(self):
        return self._get_mandatory_string('stable_suite')

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as e:
            raise AttributeError('No configuration item {!r}'.format(name))

    @property
    def qemu_image(self):
        return Template(self['qemu_image']).substitute(
                architecture=self.architecture,
                suite=self.suite,
                vendor=self.vendor,
                )

    @property
    def build_suite(self):
        value = self['build_suite']

        if value is None:
            value = self.build_vendor.unstable_suite

        return value

    @property
    def builder_qemu_image(self):
        value = self['builder_qemu_image']

        if value is None:
            value = self.build_vendor['qemu_image']

        return Template(value).substitute(
                architecture=self.build_architecture,
                suite=self.build_suite,
                vendor=self.build_vendor,
                )

    @property
    def builder(self):
        return Template(self['builder']).substitute(
                builder_qemu_image=self.builder_qemu_image,
                storage=self.storage,
                )

    @property
    def storage(self):
        return Template(self['storage']).substitute(self)

    @property
    def build_architecture(self):
        return Template(self['build_architecture']).substitute(
                architecture=self.architecture,
                )

    @property
    def archive(self):
        return Template(self['archive']).substitute(
                vendor=self.vendor,
                )

    @property
    def debootstrap_script(self):
        return Template(self['debootstrap_script']).substitute(
                suite=self.suite,
                )

    @property
    def mirror(self):
        return Template(self['mirror']).substitute(
                archive=self.archive,
                vendor=self.vendor,
                )

    @property
    def bootstrap_mirror(self):
        return Template(self['bootstrap_mirror']).substitute(
                archive=self.archive,
                mirror=self.mirror,
                vendor=self.vendor,
                )

    @property
    def apt_suite(self):
        suite = self['apt_suite']

        if suite is None:
            return str(self.suite)

        return Template(suite).substitute(
                base=self.base,
                suite=self.suite,
                )

class Vendor(_ConfigLike):
    def __init__(self, name, raw):
        super(Vendor, self).__init__()
        self._name = name
        self._raw = raw
        self._suites = WeakValueDictionary()

        for r in self._raw:
            p = r.get('vendors', {}).get(self._name, {})
            suites = p.get('suites', {})

            for suite in suites.keys():
                if '*' not in suite:
                    continue

                if (not suite.startswith('*-') or
                        '*' in suite[2:]):
                    raise ConfigError('Suite wildcards must be of the '
                            'form *-something')

    @property
    def vendor(self):
        return self

    def get_suite(self, name, create=True):
        if name is None:
            return None

        s = self._suites.get(name)

        if s is not None:
            return s

        raw = None
        aliases = set()
        base = None
        pattern = None

        while True:
            for r in self._raw:
                p = r.get('vendors', {}).get(self._name, {})
                raw = p.get('suites', {}).get(name)

                if raw:
                    break

            if raw is None or 'alias_for' not in raw:
                break

            name = raw['alias_for']
            if name in aliases:
                raise ConfigError('{!r}/{!r} is an alias for '
                        'itself'.format(self, name))
            aliases.add(name)
            continue

        if raw is None and '-' in name:
            base, pocket = name.split('-', 1)
            base = self.get_suite(base, create=False)

            if base is not None:
                pattern = '*-{}'.format(pocket)
                for r in self._raw:
                    p = r.get('vendors', {}).get(self._name, {})
                    raw = p.get('suites', {}).get(pattern)

                    if raw is not None:
                        name = '{}-{}'.format(base, pocket)
                        break

        if raw is None and not create:
            return None

        s = Suite(name, self, self._raw, base=base, pattern=pattern)
        self._suites[name] = s
        return s

    def __str__(self):
        return self._name

    def __repr__(self):
        return '<Vendor {!r}>'.format(self._name)

    def __getitem__(self, name):
        if name not in self._raw[-1]['defaults']:
            raise KeyError('{!r} does not configure {!r}'.format(self, name))

        for r in self._raw:
            p = r.get('vendors', {}).get(self._name, {})

            if name in p:
                return p[name]

        for r in self._raw:
            d = r.get('defaults', {})

            if name in d:
                return d[name]

        # We already checked that it was in _raw[-1], which is the set of
        # hard-coded defaults from this file, as augmented with environment
        # variables etc.
        raise AssertionError('Not reached')

class Suite(_ConfigLike):
    def __init__(self, name, vendor, raw, base=None, pattern=None):
        super(Suite, self).__init__()
        self._name = name
        self._vendor = vendor
        self._raw = raw
        self.base = None

        if pattern is None:
            self._pattern = name
        else:
            self._pattern = pattern

        if base is None:
            base = vendor.get_suite(self.__get('base'))

        self.base = base
        self.hierarchy = []
        suite = self

        while suite is not None:
            self.hierarchy.append(suite)
            suite = suite.base

    @property
    def vendor(self):
        return self._vendor

    @property
    def suite(self):
        return self

    def __str__(self):
        return self._name

    def __repr__(self):
        return '<Suite {!r}/{!r}>'.format(self._vendor, self._name)

    def __getitem__(self, name):
        if name == 'base':
            return str(self.base)

        for ancestor in self.hierarchy:
            value = ancestor.__get(name)

            if value is not None:
                return value

        return self.vendor[name]

    def __get(self, name):
        if (name not in self._raw[-1]['defaults'] and
                name not in ('apt_suite', 'base')):
            raise KeyError('{!r} does not configure {!r}'.format(self, name))

        for r in self._raw:
            p = r.get('vendors', {}).get(str(self._vendor), {})
            s = p.get('suites', {}).get(self._pattern, {})

            if name in s:
                return s[name]

        return None

class Directory(_ConfigLike):
    def __init__(self, path, raw):
        super(Directory, self).__init__()
        self._path = path
        self._raw = raw

    def __str__(self):
        return self._path

    def __repr__(self):
        return '<Directory {!r}>'.format(self._path)

    def __getitem__(self, name):
        if name not in self._raw[-1]['defaults']:
            raise KeyError('{!r} does not configure {!r}'.format(self, name))

        for r in self._raw:
            d = r.get('directories', {}).get(self._path, {})

            if name in d:
                return d[name]

        raise KeyError(name)

    def __contains__(self, name):
        try:
            self.__getitem__(name)
        except KeyError:
            return False
        else:
            return True

class Config(_ConfigLike):
    def __init__(self, config_layers=(), current_directory=None):
        super(Config, self).__init__()

        self._vendors = {}
        self._overrides = {}
        self._relevant_directory = None

        d = yaml.safe_load(DEFAULTS)

        # Let these be used for expansion, unconditionally
        d['defaults']['HOME'] = os.path.expanduser('~')
        d['defaults']['XDG_CACHE_HOME'] = os.getenv('XDG_CACHE_HOME',
                os.path.expanduser('~/.cache'))
        d['defaults']['XDG_CONFIG_HOME'] = os.getenv('XDG_CONFIG_HOME',
                os.path.expanduser('~/.config'))
        d['defaults']['XDG_CONFIG_DIRS'] = os.getenv('XDG_CONFIG_DIRS',
                '/etc/xdg')
        d['defaults']['XDG_DATA_HOME'] = os.getenv('XDG_DATA_HOME',
                os.path.expanduser('~/.local/share'))
        d['defaults']['XDG_DATA_DIRS'] = os.getenv('XDG_DATA_DIRS',
                os.path.expanduser('~/.local/share'))

        # Some things can have better defaults that can't be hard-coded
        d['defaults']['parallel'] = str(os.cpu_count())

        try:
            d['defaults']['architecture'] = subprocess.check_output(
                    ['dpkg', '--print-architecture'],
                    universal_newlines=True).strip()
        except subprocess.CalledProcessError:
            pass

        try:
            import distro_info
        except ImportError:
            pass
        else:
            debian = distro_info.DebianDistroInfo()
            ubuntu = distro_info.UbuntuDistroInfo()
            d['vendors']['debian']['stable_suite'] = debian.stable()
            d['vendors']['ubuntu']['stable_suite'] = ubuntu.lts()
            d['vendors']['debian']['unstable_suite'] = debian.devel()
            d['vendors']['ubuntu']['unstable_suite'] = ubuntu.devel()
            d['vendors']['debian']['suites']['stable'] = {
                    'alias_for': debian.stable(),
            }
            d['vendors']['debian']['suites']['testing'] = {
                    'alias_for': debian.testing(),
            }
            d['vendors']['debian']['suites']['oldstable'] = {
                    'alias_for': debian.old(),
            }
            d['vendors']['ubuntu']['suites']['devel'] = {
                    'alias_for': ubuntu.devel(),
            }

            for suite in debian.all:
                d['vendors']['debian']['suites'].setdefault(suite, {})

            for suite in ubuntu.all:
                d['vendors']['ubuntu']['suites'].setdefault(suite, {})

        self._raw = []
        self._raw.append(d)

        if config_layers:
            self._raw[:0] = list(config_layers)
        else:
            config_dirs = d['defaults']['XDG_CONFIG_DIRS'].split(':')
            config_dirs = list(reversed(config_dirs))
            config_dirs.append(d['defaults']['XDG_CONFIG_HOME'])
            for p in config_dirs:
                conffile = os.path.join(p, 'vectis', 'vectis.yaml')

                try:
                    reader = open(conffile)
                except FileNotFoundError:
                    continue

                with reader:
                    raw = yaml.safe_load(reader)

                    if not isinstance(raw, dict):
                        raise ConfigError('Reading {!r} did not yield a '
                                'dict'.format(conffile))

                    self._raw.insert(0, raw)

        if current_directory is None:
            current_directory = os.getcwd()

        self._relevant_directory = None

        while self._relevant_directory is None:
            for r in self._raw:
                if current_directory in r.get('directories', {}):
                    self._relevant_directory = current_directory
                    break
            else:
                parent, _ = os.path.split(current_directory)
                # Guard against infinite recursion. If current_directory == '/'
                # we would already have found directories./ in the hard-coded
                # defaults, and broken out of the loop
                assert len(parent) < len(current_directory)
                current_directory = parent
                continue

        assert self._relevant_directory is not None
        self._path_based = Directory(self._relevant_directory, self._raw)

    def _get_vendor(self, name):
        if name not in self._vendors:
            self._vendors[name] = Vendor(name, self._raw)
        return self._vendors[name]

    def __getitem__(self, name):
        if name in self._overrides:
            return self._overrides[name]

        if name in self._path_based:
            return self._path_based[name]

        if name != 'vendor':
            return self.vendor[name]

        for r in self._raw:
            if 'vendor' in r.get('defaults', {}):
                return r['defaults']['vendor']

        raise AssertionError('I know the defaults do specify a vendor')

    @property
    def vendor(self):
        return self._get_vendor(self['vendor'])

    @property
    def build_vendor(self):
        return self._get_vendor(self['build_vendor'])

    def __setattr__(self, name, value):
        if name.startswith('_'):
            super(Config, self).__setattr__(name, value)
        else:
            self._overrides[name] = value

if __name__ == '__main__':
    for args in (
            {},
            { 'vendor': 'debian' },
            { 'vendor': 'ubuntu', 'unstable_suite': 'yakkety' },
            { 'vendor': 'steamos',
                'stable_suite': 'alchemist',
                'unstable_suite': 'brewmaster',
                'extra_components': 'contrib non-free',
                'debootstrap_script': 'sid',
                'mirror': 'http://repo.steampowered.com/${archive}' },
            { 'vendor': 'xyz',
                'default_suite': 'whatever',
                'components': 'main drivers sdk',
                'debootstrap_script': 'xenial',
                'mirror': 'http://example.com/${archive}' },
            ):
        print(args)

        c = Config()
        for k, v in args.items():
            setattr(c, k, v)

        for x in sorted(set(c._raw[-1]['defaults'].keys()) |
                set('all_components'.split())):
            try:
                print('\t{}={!r}'.format(x, getattr(c, x)))
            except ValueError:
                print('\t{}=<no default>'.format(x))
