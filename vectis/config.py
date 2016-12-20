# Copyright © 2015-2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import os
import subprocess
from string import Template

import yaml

DEFAULTS = '''
---
defaults:
    storage: "${XDG_CACHE_HOME}/vectis"
    platform: debian
    size: 42G
    components: main
    extra_components: []
    archive: "${platform}"
    mirror: "http://192.168.122.1:3142/${archive}"
    # FIXME: qemu_image doesn't actually work as intended because the value
    # of ${suite} is still None when we evaluate this. Fixing this would
    # need some sort of late-evaluation that takes into account config keys
    # with "magic" values, like guessing suite from debian/changelog
    qemu_image: "vectis-${platform}-${suite}-${architecture}.qcow2"
    debootstrap_script: "${suite}"
    default_suite: "${unstable_suite}"
    aliases: {}
    architecture: null
    stable_suite: null
    suite: null
    unstable_suite: null

    build_platform: debian
    build_suite: ${build_platform__unstable_suite}
    build_architecture: "${architecture}"
    builder: "autopkgtest-virt-qemu ${storage}/${builder_qemu_image}"
    builder_qemu_image: "vectis-${build_platform}-${build_suite}-${build_architecture}.qcow2"

    bootstrap_mirror: "${mirror}"

    sbuild_force_parallel: 0
    parallel: null
    sbuild_together: false
    output_builds: ".."

    sbuild_buildables: null

platforms:
    debian:
        extra_components: contrib non-free
        aliases:
            unstable: sid
            rc-buggy: experimental

    ubuntu:
        build_suite: "${stable_suite}"
        build_platform: ubuntu
        extra_components: universe restricted multiverse

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

        raise ValueError('Invalid value for {!r}: {!r} is not a boolean '
                'value'.format(name, value))

    def _get_mandatory_string(self, name):
        value = self[name]

        if isinstance(value, str):
            return value

        raise ValueError('{!r} key {!r} has no default and must be '
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

class Platform(_ConfigLike):
    def __init__(self, name, raw):
        super(Platform, self).__init__()
        self._name = name
        self._raw = raw

    @property
    def platform(self):
        return self

    def __str__(self):
        return self._name

    def __repr__(self):
        return '<Platform {!r}>'.format(self._name)

    def __getitem__(self, name):
        if name not in self._raw[-1]['defaults']:
            raise KeyError('{!r} does not configure {!r}'.format(self, name))

        for r in self._raw:
            p = r.get('platforms', {}).get(self._name, {})

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

        self._platforms = {}
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
            d['platforms']['debian']['stable_suite'] = debian.stable()
            d['platforms']['ubuntu']['stable_suite'] = ubuntu.lts()
            d['platforms']['debian']['unstable_suite'] = debian.devel()
            d['platforms']['ubuntu']['unstable_suite'] = ubuntu.devel()
            d['platforms']['debian']['aliases']['unstable'] = debian.devel()
            d['platforms']['debian']['aliases']['stable'] = debian.stable()
            d['platforms']['debian']['aliases']['testing'] = debian.testing()
            d['platforms']['debian']['aliases']['oldstable'] = debian.old()
            d['platforms']['debian']['aliases']['rc-buggy'] = 'experimental'

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
                        raise ValueError('Reading {!r} did not yield a '
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

    def expand(self, value):
        if not isinstance(value, str):
            return value

        return Template(value).substitute(self)

    def _get_platform(self, name):
        if name not in self._platforms:
            self._platforms[name] = Platform(name, self._raw)
        return self._platforms[name]

    def __getitem__(self, name):
        # FIXME: this hack is only here because we need to evaluate
        # builder_qemu_image, which uses the build platform's suite,
        # not the host platform's
        if '__' in name:
            which, name = name.split('__')
            return self._get_platform(self[which])[name]

        if name in self._overrides:
            return self.expand(self._overrides[name])

        if name in self._path_based:
            return self.expand(self._path_based[name])

        if name != 'platform':
            return self.expand(self.platform[name])

        for r in self._raw:
            if 'platform' in r.get('defaults', {}):
                return r['defaults']['platform']

        raise AssertionError('I know the defaults do specify a platform')

    @property
    def platform(self):
        return self._get_platform(self['platform'])

    @property
    def build_platform(self):
        return self._get_platform(self['build_platform'])

    def __setattr__(self, name, value):
        if name.startswith('_'):
            super(Config, self).__setattr__(name, value)
        else:
            self._overrides[name] = value

if __name__ == '__main__':
    for args in (
            {},
            { 'platform': 'debian' },
            { 'platform': 'ubuntu', 'unstable_suite': 'yakkety' },
            { 'platform': 'steamos',
                'stable_suite': 'alchemist',
                'unstable_suite': 'brewmaster',
                'extra_components': 'contrib non-free',
                'debootstrap_script': 'sid',
                'mirror': 'http://repo.steampowered.com/${archive}' },
            { 'platform': 'xyz',
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
