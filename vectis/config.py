# Copyright © 2015-2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import os
import subprocess
from weakref import WeakValueDictionary

from vectis.error import Error

import yaml

class ConfigError(Error):
    pass

DEFAULTS = '''
---
defaults:
    vendor: debian
    storage: null
    size: 42G
    components: main
    extra_components: []
    archive: null
    apt_cacher_ng: "http://192.168.122.1:3142"
    mirror: null
    qemu_image: null
    write_qemu_image: null
    debootstrap_script: null
    default_suite: null
    aliases: {}
    architecture: null
    suite: null

    worker_vendor: debian
    worker_suite: null
    worker_architecture: null
    worker: null
    worker_qemu_image: null

    sbuild_worker_suite: null
    sbuild_worker: null

    autopkgtest: true
    autopkgtest_qemu_image: null

    bootstrap_mirror: null

    force_parallel: 0
    parallel: null
    sbuild_together: false
    output_builds: ".."

    sbuild_buildables: null
    sbuild_resolver: []
    apt_key: null
    apt_suite: null
    dpkg_source_tar_ignore: []
    dpkg_source_diff_ignore: null
    dpkg_source_extend_diff_ignore: []

vendors:
    debian:
        extra_components: contrib non-free
        sbuild_worker_suite: jessie-apt.buildd.debian.org
        worker_vendor: debian
        suites:
            wheezy:
                force_parallel: 1
            jessie:
                force_parallel: 1
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
                archive: "security.debian.org"
                apt_suite: "*/updates"
            "*-updates":
                null: null
            "*-apt.buildd.debian.org":
                archive: "apt.buildd.debian.org"
                # https://anonscm.debian.org/cgit/mirror/dsa-puppet.git/tree/modules/buildd/
                apt_key: "buildd.debian.org_archive_key_2015_2016.gpg"
                apt_suite: "*"
                components: main
    ubuntu:
        worker_vendor: ubuntu
        extra_components: universe restricted multiverse
        suites:
            trusty:
                force_parallel: 1
            precise:
                force_parallel: 1
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

HOME = os.path.expanduser('~')
XDG_CACHE_HOME = os.getenv('XDG_CACHE_HOME', os.path.expanduser('~/.cache'))
XDG_CONFIG_HOME = os.getenv('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
XDG_CONFIG_DIRS = os.getenv('XDG_CONFIG_DIRS', '/etc/xdg')
XDG_DATA_HOME = os.getenv('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))
XDG_DATA_DIRS = os.getenv('XDG_DATA_DIRS', os.path.expanduser('~/.local/share'))

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

    def _get_filename(self, name, default=None):
        value = self[name]

        if value is None:
            value = default

        value = os.path.expandvars(value)
        value = os.path.expanduser(value)
        return value

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
    def force_parallel(self):
        return self._get_int('force_parallel')

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

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as e:
            raise AttributeError('No configuration item {!r}'.format(name))

    @property
    def write_qemu_image(self):
        value = self['write_qemu_image']

        if value is None:
            value = self.qemu_image

        if '/' not in value:
            return os.path.join(self.storage, value)

        return value

    @property
    def storage(self):
        return self._get_filename('storage',
                os.path.join(XDG_CACHE_HOME, 'vectis'))

    @property
    def output_builds(self):
        return self._get_filename('output_builds')

    @property
    def worker_architecture(self):
        value = self['worker_architecture']

        if value is None:
            value = self.architecture

        return value

    @property
    def archive(self):
        value = self['archive']

        if value is None:
            value = str(self.vendor)

        return value

    @property
    def debootstrap_script(self):
        return str(self.suite)

    @property
    def mirror(self):
        value = self['mirror']

        if value is None and self.apt_cacher_ng is not None:
            value = self.apt_cacher_ng + '/' + self.archive

        if value is None:
            raise ConfigError('Either mirror or apt_cacher_ng must be set')

        return value

    @property
    def bootstrap_mirror(self):
        value = self['bootstrap_mirror']

        if value is None:
            value = self.mirror

        return value

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

        if isinstance(name, Suite):
            return name

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

    @property
    def apt_key(self):
        value = self['apt_key']

        if value is None:
            return None

        if '/' in value:
            return value

        return os.path.join(os.path.dirname(__file__), 'keys', value)

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

    @property
    def apt_suite(self):
        suite = self['apt_suite']

        if suite is None:
            return str(self.suite)

        if '*' in suite and self.base is not None:
            return suite.replace('*', str(self.base))

        return suite

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
            d['vendors']['debian']['default_suite'] = 'sid'
            d['vendors']['debian']['suites']['stable'] = {
                    'alias_for': debian.stable(),
            }
            d['vendors']['debian']['suites']['testing'] = {
                    'alias_for': debian.testing(),
            }
            d['vendors']['debian']['suites']['oldstable'] = {
                    'alias_for': debian.old(),
            }

            # According to autopkgtest-buildvm-ubuntu-cloud, just after
            # an Ubuntu release there is briefly no development version
            # at all.
            try:
                ubuntu_devel = ubuntu.devel()
            except distro_info.DistroDataOutdated:
                ubuntu_devel = ubuntu.stable()

            d['vendors']['ubuntu']['default_suite'] = ubuntu.devel()
            d['vendors']['ubuntu']['worker_suite'] = ubuntu.lts()
            d['vendors']['ubuntu']['suites']['devel'] = {
                    'alias_for': ubuntu_devel,
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
            config_dirs = XDG_CONFIG_DIRS.split(':')
            config_dirs = list(reversed(config_dirs))
            config_dirs.append(XDG_CONFIG_HOME)
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
    def suite(self):
        suite = self['suite']

        if suite is None:
            suite = self.vendor.default_suite

        return self.vendor.get_suite(suite)

    @property
    def vendor(self):
        return self._get_vendor(self['vendor'])

    @property
    def worker_vendor(self):
        return self._get_vendor(self['worker_vendor'])

    def __setattr__(self, name, value):
        if name.startswith('_'):
            super(Config, self).__setattr__(name, value)
        else:
            self._overrides[name] = value

    @property
    def worker_suite(self):
        value = self['worker_suite']

        if value is None:
            value = self.worker_vendor.worker_suite

        if value is None:
            value = self.worker_vendor.default_suite

        if value is None:
            return None

        return self.worker_vendor.get_suite(value, True)

    @property
    def sbuild_worker_suite(self):
        suite = self['sbuild_worker_suite']

        if suite is None:
            suite = self.worker_suite

        return suite

    @property
    def autopkgtest_qemu_image(self):
        value = self['autopkgtest_qemu_image']

        if value is None:
            value = self.qemu_image

        if '/' not in value:
            return os.path.join(self.storage, value)

        return value

    @property
    def qemu_image(self):
        value = self['qemu_image']

        if value is None:
            value = 'vectis-{}-{}-{}.qcow2'.format(self.vendor,
                    self.suite.hierarchy[-1], self.architecture)

        if '/' not in value:
            return os.path.join(self.storage, value)

        return value

    @property
    def worker_qemu_image(self):
        value = self['worker_qemu_image']

        if value is None:
            value = self.worker_vendor.qemu_image

        if value is None:
            value = 'vectis-{}-{}-{}.qcow2'.format(self.worker_vendor,
                    self.worker_suite.hierarchy[-1],
                    self.worker_architecture)

        if '/' not in value:
            return os.path.join(self.storage, value)

        return value

    @property
    def worker(self):
        value = self['worker']

        if value is None:
            if str(self.worker_vendor) == 'ubuntu':
                value = ('qemu --username=ubuntu --password=ubuntu ' +
                        self.worker_qemu_image)
            else:
                value = 'qemu ' + self.worker_qemu_image

        return value

    @property
    def sbuild_worker(self):
        value = self['worker']

        if value is None:
            value = self.worker

        return value
