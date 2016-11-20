# Copyright © 2015-2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import os
import subprocess
from configparser import ConfigParser
from string import Template

DEFAULTS = '''
[Defaults]
storage = ${XDG_CACHE_HOME}/vectis
platform = debian
size = 42G
components = main
extra_components =
archive = ${platform}
mirror = http://192.168.122.1:3142/${archive}
qemu_image = vectis-${platform}-${suite}-${architecture}.qcow2
debootstrap_script = ${suite}
default_suite = ${unstable_suite}
aliases =

build_platform = debian
build_suite = ${build_platform__unstable_suite}
build_architecture = ${architecture}
builder = autopkgtest-virt-qemu ${storage}/${builder_qemu_image}
builder_qemu_image = vectis-${build_platform}-${build_suite}-${build_architecture}.qcow2

bootstrap_mirror = ${mirror}

sbuild_force_parallel = 0
parallel = 0
sbuild_together = false
output_builds = ..

[Platform debian]
stable_suite = jessie
unstable_suite = sid
build_suite = ${unstable_suite}
extra_components = contrib non-free
aliases = unstable:sid testing:stretch stable:jessie rc-buggy:experimental

[Platform ubuntu]
build_platform = ubuntu
stable_suite = xenial
unstable_suite = yakkety
extra_components = universe restricted multiverse

[Directory /]
# directory-specific configuration has highest priority, do not put anything
# in here by default
'''

_NO_DEFAULT = set((
    'architecture',
    'sbuild_buildables',
    'sbuild_together',
    'stable_suite',
    'suite',
    'unstable_suite',
    ))

class _ConfigLike:
    def __init__(self):
        self._cp = None

    @property
    def all_components(self):
        return set(self['extra_components'].split()) | set(self['components'].split())

    @property
    def components(self):
        return set(self['components'].split())

    @property
    def extra_components(self):
        return set(self['extra_components'].split())

    @property
    def sbuild_force_parallel(self):
        return int(self['sbuild_force_parallel'])

    @property
    def parallel(self):
        return int(self['parallel'])

    @property
    def sbuild_together(self):
        return self._bool('sbuild_together')

    def _bool(self, name):
        v = self[name].lower()

        if v in ('yes', 'true', 'on', '1'):
            return True

        if v in ('no', 'false', 'off', '0'):
            return False

        raise ValueError('{!r} is not a boolean value'.format(v))

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as e:
            raise AttributeError(str(e))

class Platform(_ConfigLike):
    def __init__(self, name, parser):
        super(Platform, self).__init__()
        self._name = name
        self._cp = parser

    def __str__(self):
        return self._name

    def __repr__(self):
        return '<Platform {!r}>'.format(self._name)

    def __getitem__(self, name):
        if name in _NO_DEFAULT or name in self._cp['Defaults']:
            return self._cp.setdefault('Platform ' + self._name, {}).get(name,
                    self._cp['Defaults'].get(name))

        raise KeyError('{!r} does not configure "{}"'.format(
            self, name))

class Config(_ConfigLike):
    def __init__(self):
        super(Config, self).__init__()

        self._platforms = {}
        self._overrides = {}
        self._path_based = {}

        self._cp = ConfigParser(interpolation=None, delimiters=('=',),
                comment_prefixes=('#',),
                # We reimplement the "default section" behaviour so that
                # we can have multiple levels of precedence.
                default_section='there is no default section')
        self._cp['Defaults'] = {}
        self._cp['Defaults']['HOME'] = os.path.expanduser('~')
        self._cp['Defaults']['XDG_CACHE_HOME'] = os.getenv('XDG_CACHE_HOME',
                os.path.expanduser('~/.cache'))
        self._cp['Defaults']['XDG_CONFIG_HOME'] = os.getenv('XDG_CONFIG_HOME',
                os.path.expanduser('~/.config'))
        self._cp['Defaults']['XDG_CONFIG_DIRS'] = os.getenv('XDG_CONFIG_DIRS',
                '/etc/xdg')
        self._cp['Defaults']['XDG_DATA_HOME'] = os.getenv('XDG_DATA_HOME',
                os.path.expanduser('~/.local/share'))
        self._cp['Defaults']['XDG_DATA_DIRS'] = os.getenv('XDG_DATA_DIRS',
                os.path.expanduser('~/.local/share'))
        self._cp['Defaults']['parallel'] = str(os.cpu_count())

        self._cp.read_string(DEFAULTS)

        self._cp['Defaults']['architecture'] = subprocess.check_output(
                ['dpkg', '--print-architecture'],
                universal_newlines=True).strip()

        try:
            import distro_info
        except ImportError:
            pass
        else:
            debian = distro_info.DebianDistroInfo()
            ubuntu = distro_info.UbuntuDistroInfo()
            self._cp['debian']['stable_suite'] = debian.stable()
            self._cp['ubuntu']['stable_suite'] = ubuntu.lts()
            self._cp['debian']['unstable_suite'] = debian.devel()
            self._cp['ubuntu']['unstable_suite'] = ubuntu.devel()
            self._cp['debian']['aliases'] = (
                    'unstable:{unstable} stable:{stable} testing:{testing} '
                    'oldstable:{oldstable} rc-buggy:experimental'.format(
                        unstable=debian.devel(),
                        stable=debian.stable(),
                        testing=debian.testing(),
                        oldstable=debian.old(),
                        )
                    )

        self._cp.read([os.path.join(p, 'vectis', 'vectis.conf') for p in
            list(reversed(self._cp['Defaults']['XDG_CONFIG_DIRS'].split(':'))) +
            [self._cp['Defaults']['XDG_CONFIG_HOME']]])

        self._path_based = self._cp['Directory /']

        here = os.getcwd()

        while True:
            section = 'Directory ' + here
            if section in self._cp:
                self._path_based = self._cp[section]
                break

            parent, _ = os.path.split(here)
            # Guard against infinite recursion. If here == '/' we would
            # already have found 'Directory /' and broken out of the loop
            assert len(parent) < len(here)
            here = parent

    def expand(self, value):
        if not isinstance(value, str):
            return value

        return Template(value).substitute(self)

    def _get_platform(self, name):
        if name not in self._platforms:
            self._platforms[name] = Platform(name, self._cp)
        return self._platforms[name]

    def __getitem__(self, name):
        if '__' in name:
            which, name = name.split('__')
            return self._get_platform(self[which])[name]

        if name in self._overrides:
            return self.expand(self._overrides[name])

        if name in self._path_based:
            return self.expand(self._path_based[name])

        return self.expand(self.platform[name])

    @property
    def platform(self):
        return self._get_platform(
                self._overrides.get('platform',
                    self._path_based.get('platform',
                        self._cp['Defaults']['platform'])))

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

        for x in sorted(set(c._cp['Defaults'].keys()) |
                _NO_DEFAULT |
                set('all_components'.split())):
            print('\t{}={!r}'.format(x, getattr(c, x)))
