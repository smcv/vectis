# Copyright © 2015-2017 Simon McVittie
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

HOME = os.path.expanduser('~')
XDG_CACHE_HOME = os.getenv('XDG_CACHE_HOME', os.path.expanduser('~/.cache'))
XDG_CONFIG_HOME = os.getenv('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
XDG_CONFIG_DIRS = os.getenv('XDG_CONFIG_DIRS', '/etc/xdg')
XDG_DATA_HOME = os.getenv(
    'XDG_DATA_HOME', os.path.expanduser('~/.local/share'))
XDG_DATA_DIRS = os.getenv(
    'XDG_DATA_DIRS', os.path.expanduser('~/.local/share'))


class Mirrors:

    def __init__(self, mapping):
        if mapping is None:
            self._raw = {}
        else:
            self._raw = mapping

    def _lookup_template(self, suite):
        for uri in suite.uris:
            value = self._raw.get(uri)

            if value is not None:
                return value

            value = self._raw.get(uri.rstrip('/'))

            if value is not None:
                return value

        value = self._raw.get(str(suite.archive))

        if value is not None:
            return value

        value = self._raw.get(None)

        if value is not None:
            return value

        return None

    def lookup_suite(self, suite):
        t = self._lookup_template(suite)

        if t is None:
            return None

        return Template(t).substitute(
            archive=suite.archive,
        )


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


class Vendor(_ConfigLike):

    def __init__(self, name, raw):
        super(Vendor, self).__init__()
        self._name = name
        self._raw = raw

        for r in self._raw:
            p = r.get('vendors', {}).get(self._name, {})
            suites = p.get('suites', {})

            for suite in suites.keys():
                if '*' not in suite:
                    continue

                if (not suite.startswith('*-') or
                        '*' in suite[2:]):
                    raise ConfigError(
                        'Suite wildcards must be of the form *-something')

    @property
    def vendor(self):
        return self

    @property
    def default_suite(self):
        return self['default_suite']

    @property
    def default_worker_suite(self):
        return self['default_worker_suite']

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
        self.base = base

        if pattern is None:
            self._pattern = name
        else:
            self._pattern = pattern

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
    def sbuild_resolver(self):
        return self['sbuild_resolver']

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
                name not in ('apt_suite', 'archive', 'base')):
            raise KeyError('{!r} does not configure {!r}'.format(self, name))

        for r in self._raw:
            p = r.get('vendors', {}).get(str(self._vendor), {})
            s = p.get('suites', {}).get(self._pattern, {})

            if name in s:
                return s[name]

        for r in self._raw:
            p = r.get('vendors', {}).get(str(self._vendor), {})

            if name in p:
                return p[name]

        return None

    @property
    def apt_suite(self):
        suite = self.__get('apt_suite')

        if suite is None:
            return str(self.suite)

        if '*' in suite and self.base is not None:
            return suite.replace('*', str(self.base))

        return suite

    @property
    def archive(self):
        value = self.__get('archive')

        if value is None:
            value = str(self.vendor)

        return value

    @property
    def uris(self):
        return self['uris'] or self.vendor['uris']


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

        self._suites = WeakValueDictionary()
        self._vendors = {}
        self._overrides = {}
        self._relevant_directory = None

        d = yaml.safe_load(
            open(os.path.join(os.path.dirname(__file__), 'defaults.yaml')))

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
            d['vendors']['debian']['default_worker_suite'] = 'sid'
        else:
            debian = distro_info.DebianDistroInfo()
            ubuntu = distro_info.UbuntuDistroInfo()
            d['vendors']['debian']['default_suite'] = 'sid'
            d['vendors']['debian']['default_worker_suite'] = debian.stable()
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
            d['vendors']['ubuntu']['default_worker_suite'] = (
                ubuntu.lts() + '-backports')
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
                        raise ConfigError(
                            'Reading {!r} did not yield a dict'.format(
                                conffile))

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

    def __delattr__(self, name):
        with suppress(KeyError):
            del self._overrides[name]

    def get_vendor(self, name):
        if name not in self._vendors:
            self._vendors[name] = Vendor(name, self._raw)
        return self._vendors[name]

    def _get_filenames(self, name, default=None):
        value = self[name]

        if value is None:
            value = default

        if value is None:
            return value

        if isinstance(value, str):
            value = [value]

        value = map(os.path.expandvars, value)
        value = map(os.path.expanduser, value)
        return list(value)

    def _get_filename(self, name, default=None):
        value = self[name]

        if value is None:
            value = default

        if value is None:
            return value

        value = os.path.expandvars(value)
        value = os.path.expanduser(value)
        return value

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

        raise ConfigError(
            'Invalid value for {!r}: {!r} is not a boolean value'.format(
                name, value))

    def _get_mandatory_string(self, name):
        value = self[name]

        if isinstance(value, str):
            return value

        raise ConfigError(
            '{!r} key {!r} has no default and must be configured'.format(
                self, name))

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as e:
            raise AttributeError('No configuration item {!r}'.format(name))

    @property
    def storage(self):
        return self._get_filename(
            'storage', os.path.join(XDG_CACHE_HOME, 'vectis'))

    @property
    def output_dir(self):
        """
        The directory in which we will place the results, overriding
        output_parent.
        """
        return self._get_filename('output_dir')

    @property
    def output_parent(self):
        """
        The directory in which we will create a new subdirectory for the
        results.
        """
        return self._get_filename('output_parent')

    @property
    def link_builds(self):
        return self._get_filenames('link_builds', ())

    @property
    def worker_architecture(self):
        value = self['worker_architecture']

        if value is None:
            value = self.architecture

        return value

    @property
    def lxc_worker_architecture(self):
        value = self['lxc_worker_architecture']

        if value is None:
            value = self.worker_architecture

        return value

    @property
    def sbuild_worker_architecture(self):
        value = self['sbuild_worker_architecture']

        if value is None:
            value = self.worker_architecture

        return value

    @property
    def vmdebootstrap_worker_architecture(self):
        value = self['vmdebootstrap_worker_architecture']

        if value is None:
            value = self.worker_architecture

        return value

    def get_kernel_package(self, architecture):
        mapping = self['kernel_package']

        if not isinstance(mapping, dict):
            mapping = {None: mapping}

        value = mapping.get(architecture)

        if value is None:
            value = mapping.get(None)

        return value

    def __getitem__(self, name):
        if name not in self._raw[-1]['defaults']:
            raise KeyError('{!r} does not configure {!r}'.format(self, name))

        if name in self._overrides:
            return self._overrides[name]

        if name in self._path_based:
            return self._path_based[name]

        if (name not in ('vendor', 'suite') and
                self.suite is not None):
            return self.suite[name]

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
            return None

        return self.get_suite(self.vendor, suite)

    @property
    def vendor(self):
        return self.get_vendor(self['vendor'])

    @property
    def worker_vendor(self):
        return self.get_vendor(self['worker_vendor'])

    @property
    def vmdebootstrap_worker_vendor(self):
        value = self['vmdebootstrap_worker_vendor']

        if value is None:
            value = self['worker_vendor']

        return self.get_vendor(value)

    @property
    def lxc_worker_vendor(self):
        value = self['lxc_worker_vendor']

        if value is None:
            value = self['worker_vendor']

        return self.get_vendor(value)

    @property
    def sbuild_worker_vendor(self):
        value = self['sbuild_worker_vendor']

        if value is None:
            value = self['worker_vendor']

        return self.get_vendor(value)

    def __setattr__(self, name, value):
        if name.startswith('_'):
            super(Config, self).__setattr__(name, value)
        else:
            self._overrides[name] = value

    @property
    def worker_suite(self):
        value = self['worker_suite']

        if value is None:
            value = self.worker_vendor.default_worker_suite

        if value is None:
            return None

        return self.get_suite(self.worker_vendor, value, True)

    @property
    def lxc_worker_suite(self):
        value = self['lxc_worker_suite']

        if value is None:
            value = self.lxc_worker_vendor.default_worker_suite

        if value is None:
            return None

        return self.get_suite(self.lxc_worker_vendor, value, True)

    @property
    def sbuild_worker_suite(self):
        value = self['sbuild_worker_suite']

        if value is None:
            value = self.sbuild_worker_vendor.default_worker_suite

        if value is None:
            return None

        return self.get_suite(self.sbuild_worker_vendor, value, True)

    @property
    def vmdebootstrap_worker_suite(self):
        value = self['vmdebootstrap_worker_suite']

        if value is None:
            value = self.vmdebootstrap_worker_vendor.default_worker_suite

        if value is None:
            return None

        return self.get_suite(self.vmdebootstrap_worker_vendor, value, True)

    @property
    def piuparts_tarballs(self):
        return self['piuparts_tarballs']

    def get_piuparts_tarballs(self,
            architecture=None,
            suite=None,
            vendor=None):
        value = self.piuparts_tarballs

        if architecture is None:
            architecture = self.architecture

        if suite is None:
            suite = self.suite

        if vendor is None:
            vendor = suite.vendor

        for v in value:
            if '/' in v:
                yield v
            else:
                yield os.path.join(
                    self.storage, architecture, str(vendor),
                    str(suite.hierarchy[-1]), v)

    @property
    def qemu_image(self):
        value = self['qemu_image']

        assert value is not None

        if '/' not in value:
            return os.path.join(
                self.storage, self.architecture, str(self.vendor),
                str(self.suite.hierarchy[-1]), value)

        return value

    @property
    def worker_qemu_image(self):
        value = self['worker_qemu_image']

        if value is None:
            value = self.worker_vendor['qemu_image']

        assert value is not None

        if '/' not in value:
            return os.path.join(
                self.storage, self.worker_architecture,
                str(self.worker_vendor),
                str(self.worker_suite.hierarchy[-1]), value)

        return value

    @property
    def lxc_worker_qemu_image(self):
        value = self['lxc_worker_qemu_image']

        if value is None:
            value = self.lxc_worker_vendor['qemu_image']

        assert value is not None

        if '/' not in value:
            return os.path.join(
                self.storage, self.lxc_worker_architecture,
                str(self.lxc_worker_vendor),
                str(self.lxc_worker_suite.hierarchy[-1]), value)

        return value

    @property
    def sbuild_worker_qemu_image(self):
        value = self['sbuild_worker_qemu_image']

        if value is None:
            value = self.sbuild_worker_vendor['qemu_image']

        assert value is not None

        if '/' not in value:
            return os.path.join(
                self.storage, self.sbuild_worker_architecture,
                str(self.sbuild_worker_vendor),
                str(self.sbuild_worker_suite.hierarchy[-1]), value)

        return value

    @property
    def write_qemu_image(self):
        value = self['write_qemu_image']

        if value is None:
            value = self['qemu_image']

        if '/' not in value:
            return os.path.join(
                self.storage, self.architecture,
                str(self.vendor), str(self.suite.hierarchy[-1]), value)

        return value

    @property
    def worker(self):
        value = self['worker']

        if value is None:
            value = ['qemu', self.worker_qemu_image]

        return value

    @property
    def lxc_worker(self):
        value = self['lxc_worker']

        if value is None:
            value = ['qemu', self.lxc_worker_qemu_image]

        return value

    @property
    def sbuild_worker(self):
        value = self['sbuild_worker']

        if value is None:
            value = ['qemu', self.sbuild_worker_qemu_image]

        return value

    @property
    def vmdebootstrap_worker_qemu_image(self):
        value = self['vmdebootstrap_worker_qemu_image']

        if value is None:
            value = self.vmdebootstrap_worker_vendor['qemu_image']

        assert value is not None

        if '/' not in value:
            return os.path.join(
                self.storage, self.vmdebootstrap_worker_architecture,
                str(self.vmdebootstrap_worker_vendor),
                str(self.vmdebootstrap_worker_suite.hierarchy[-1]), value)

        return value

    @property
    def vmdebootstrap_worker(self):
        value = self['vmdebootstrap_worker']

        if value is None:
            value = ['qemu', self.vmdebootstrap_worker_qemu_image]

        return value

    @property
    def vmdebootstrap_options(self):
        return self.suite['vmdebootstrap_options']

    @property
    def debootstrap_script(self):
        value = self['debootstrap_script']

        if value is not None:
            return value

        if self.suite is None:
            return None

        return str(self.suite)

    @property
    def apt_key(self):
        value = self['apt_key']

        if value is None:
            return None

        if '/' in value:
            return value

        return os.path.join(os.path.dirname(__file__), 'keys', value)

    def get_mirrors(self):
        return Mirrors(self['mirrors'])

    def get_suite(self, vendor, name, create=True):
        original_name = name

        if name is None:
            return None

        if isinstance(name, Suite):
            return name

        s = self._suites.get((str(vendor), name))

        if s is not None:
            return s

        raw = None
        aliases = set()
        base = None
        pattern = None

        while True:
            for r in self._raw:
                p = r.get('vendors', {}).get(str(vendor), {})
                raw = p.get('suites', {}).get(name)

                if raw:
                    break

            if raw is None or 'alias_for' not in raw:
                break

            name = raw['alias_for']
            if name in aliases:
                raise ConfigError(
                    '{!r}/{!r} is an alias for itself'.format(vendor, name))
            aliases.add(name)
            continue

        s = self._suites.get((str(vendor), name))

        if s is not None:
            return s

        if raw is None and '-' in name:
            base, pocket = name.split('-', 1)
            base = self.get_suite(vendor, base, create=False)

            if base is not None:
                pattern = '*-{}'.format(pocket)
                for r in self._raw:
                    p = r.get('vendors', {}).get(str(vendor), {})
                    raw = p.get('suites', {}).get(pattern)

                    if raw is not None:
                        name = '{}-{}'.format(base, pocket)
                        break

        if raw is None and not create:
            return None

        if base is None:
            for r in self._raw:
                p = r.get('vendors', {}).get(str(vendor), {})
                s = p.get('suites', {}).get(name, {})

                if 'base' in s:
                    b = s['base']

                    if '/' in b:
                        v, b = b.split('/', 1)
                        base_vendor = self.get_vendor(v)
                    else:
                        base_vendor = vendor

                    base = self.get_suite(base_vendor, b)
                    break

        s = Suite(name, vendor, self._raw, base=base, pattern=pattern)
        self._suites[(str(vendor), original_name)] = s
        self._suites[(str(vendor), name)] = s
        return s
