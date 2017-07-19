#!/usr/bin/python3

# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import io
import os
import subprocess
import unittest

import yaml

import vectis.config
from vectis.config import (
        Config,
        ConfigError,
        )

XDG_CACHE_HOME = os.getenv('XDG_CACHE_HOME', os.path.expanduser('~/.cache'))

try:
    ARCHITECTURE = subprocess.check_output(['dpkg', '--print-architecture'],
            universal_newlines=True).strip()
except:
    ARCHITECTURE = None

CONFIG="""
defaults:
    mirrors:
        null: http://192.168.122.1:3142/${archive}
        steamos: http://localhost/steamos
        http://archive.ubuntu.com/ubuntu: http://mirror/ubuntu
    architecture: mips
"""

VENDORS="""
vendors:
    steamrt:
        archive: repo.steamstatic.com/steamrt
        uris:
            - http://repo.steamstatic.com/steamrt
        components:
            - main
            - contrib
            - non-free
        suites:
            scout:
                base: ubuntu/precise
"""

class DefaultsTestCase(unittest.TestCase):
    def setUp(self):
        self.__config = Config(
            config_layers=(
                yaml.safe_load(io.StringIO(CONFIG)),
                yaml.safe_load(io.StringIO(VENDORS)),
            ),
            current_directory='/',
        )

    def test_defaults(self):
        self.__config = Config(config_layers=({},), current_directory='/')
        c = self.__config

        self.assertGreaterEqual(c.parallel, 1)
        self.assertIs(type(c.parallel), int)

        debian = c.get_vendor('debian')
        ubuntu = c.get_vendor('ubuntu')

        self.assertEqual(str(c.vendor), 'debian')
        self.assertEqual(str(c.worker_vendor), 'debian')
        self.assertEqual(str(c.vmdebootstrap_worker_vendor),
                'debian')
        self.assertEqual(str(c.sbuild_worker_vendor), 'debian')
        self.assertIs(c.vendor, debian)
        self.assertIs(c.worker_vendor, debian)
        self.assertIs(c.sbuild_worker_vendor, debian)
        self.assertIs(c.vmdebootstrap_worker_vendor, debian)
        with self.assertRaises(AttributeError):
            c.archive
        self.assertIs(c.sbuild_together, False)
        self.assertEqual(c.output_builds, '..')
        self.assertEqual(c.qemu_image_size, '42G')
        self.assertIsNone(c.sbuild_buildables)
        self.assertEqual(c.sbuild_resolver, [])
        self.assertEqual(c.debootstrap_script, None)
        self.assertEqual(c.apt_key,
                '/usr/share/keyrings/debian-archive-keyring.gpg')
        self.assertEqual(c.dpkg_source_tar_ignore, [])
        self.assertIsNone(c.dpkg_source_diff_ignore)
        self.assertEqual(c.dpkg_source_extend_diff_ignore, [])

        if ARCHITECTURE is not None:
            self.assertEqual(c.architecture, ARCHITECTURE)

        if 0:
            # FIXME: these raise, because suite is undefined,
            # but then the error is trapped and __getattr__ is called
            # instead
            self.assertEqual(c.qemu_image,
                    '{}/vectis/{}/debian/sid/autopkgtest.qcow2'.format(
                        XDG_CACHE_HOME, ARCHITECTURE))
            self.assertEqual(c.write_qemu_image,
                    '{}/vectis/{}/debian/sid/autopkgtest.qcow2'.format(
                        XDG_CACHE_HOME, ARCHITECTURE))
            self.assertEqual(c.worker_architecture, ARCHITECTURE)
            self.assertEqual(c.worker,
                    ['qemu', c.worker_qemu_image])
            self.assertEqual(c.worker_qemu_image,
                    '{}/vectis/{}/debian/sid/autopkgtest.qcow2'.format(
                        XDG_CACHE_HOME, ARCHITECTURE))
            self.assertEqual(c.sbuild_worker,
                    ['qemu', c.sbuild_worker_qemu_image])
            self.assertEqual(c.sbuild_worker_qemu_image,
                    '{}/vectis/{}/debian/sid/autopkgtest.qcow2'.format(
                        XDG_CACHE_HOME, ARCHITECTURE))

        self.assertEqual(c.autopkgtest, ['lxc', 'qemu'])
        self.assertEqual(c.suite, None)
        with self.assertRaises(AttributeError):
            c.apt_suite

        try:
            import distro_info
        except ImportError:
            pass
        else:
            self.assertEqual(c.worker_suite,
                    c.get_suite(c.vendor,
                        distro_info.DebianDistroInfo().stable()))
            self.assertEqual(c.default_worker_suite,
                        distro_info.DebianDistroInfo().stable())

        stable = c.get_suite(c.vendor, 'stable')
        self.assertEqual(c.sbuild_worker_suite, stable)
        self.assertEqual(c.default_suite, 'sid')
        self.assertEqual(c.components, {'main'})
        self.assertEqual(c.extra_components,
                {'contrib', 'non-free'})
        self.assertEqual(c.all_components, {'main',
            'contrib', 'non-free'})

        self.assertEqual(c.storage,
            '{}/vectis'.format(XDG_CACHE_HOME))

    def test_substitutions(self):
        c = self.__config

        c.architecture = 'm68k'
        c.suite = 'potato'
        c.worker_suite = 'sarge'
        c.sbuild_worker_suite = 'alchemist'
        c.sbuild_worker_vendor = 'steamos'
        c.vmdebootstrap_worker_suite = 'xenial'
        c.vmdebootstrap_worker_vendor = 'ubuntu'

        debian = c.get_vendor('debian')
        potato = c.get_suite(debian, 'potato')
        sarge = c.get_suite(debian, 'sarge')
        self.assertEqual(list(potato.hierarchy), [potato])
        self.assertEqual(list(sarge.hierarchy), [sarge])
        self.assertEqual(c.suite, potato)
        self.assertEqual(c.worker_suite, sarge)

        self.assertEqual(c.debootstrap_script, 'potato')
        self.assertEqual(c.qemu_image,
                '{}/m68k/debian/potato/autopkgtest.qcow2'.format(
                    c.storage))
        self.assertEqual(c.worker_qemu_image,
                '{}/m68k/debian/sarge/autopkgtest.qcow2'.format(
                    c.storage))
        self.assertEqual(c.worker,
                ['qemu', '{}/m68k/debian/sarge/autopkgtest.qcow2'.format(
                    c.storage)])

        self.assertEqual(c.sbuild_worker_qemu_image,
                '{}/m68k/steamos/alchemist/autopkgtest.qcow2'.format(
                    c.storage))
        self.assertEqual(c.vmdebootstrap_worker_qemu_image,
                '{}/m68k/ubuntu/xenial/autopkgtest.qcow2'.format(
                    c.storage))

        self.assertEqual(
            c.get_mirrors().lookup_suite(potato),
            'http://192.168.122.1:3142/debian')
        self.assertEqual(
            c.get_mirrors().lookup_suite(sarge),
            'http://192.168.122.1:3142/debian')

        with self.assertRaises(AttributeError):
            c.apt_suite

    def test_debian(self):
        c = self.__config
        c.vendor = 'debian'
        c.suite = 'sid'

        debian = c.get_vendor('debian')
        self.assertIs(c.vendor, debian)

        sid = c.get_suite(debian, 'sid')

        self.assertIs(c.suite, sid)

        # Properties of the vendor itself
        self.assertEqual(str(debian), 'debian')
        self.assertEqual(debian.default_suite, 'sid')
        self.assertIs(c.get_suite(debian, 'unstable'), sid)
        self.assertEqual(debian.components, {'main'})
        self.assertEqual(debian.extra_components, {'contrib', 'non-free'})
        self.assertEqual(debian.all_components, {'main', 'contrib',
            'non-free'})
        self.assertIsNone(c.get_suite(debian, 'xenial', create=False))

        # Properties of the suite itswelf
        self.assertEqual(sid.apt_key,
                '/usr/share/keyrings/debian-archive-keyring.gpg')
        self.assertEqual(sid.archive, 'debian')
        self.assertEqual(
            c.get_mirrors().lookup_suite(sid),
            'http://192.168.122.1:3142/debian')
        self.assertIs(sid.base, None)
        self.assertEqual(sid.components, {'main'})
        self.assertEqual(sid.extra_components, {'contrib', 'non-free'})
        self.assertEqual(sid.all_components, {'main', 'contrib', 'non-free'})
        self.assertEqual(sid.apt_suite, 'sid')
        self.assertEqual(sid.sbuild_resolver, [])

        # Properties of the Config determined by the suite being Debian sid
        self.assertEqual(c.autopkgtest, ['lxc', 'qemu'])
        self.assertIs(c.worker_vendor, debian)
        self.assertIs(c.sbuild_worker_vendor, debian)
        self.assertIs(c.vmdebootstrap_worker_vendor, debian)
        with self.assertRaises(AttributeError):
            c.archive
        self.assertEqual(c.qemu_image_size, '42G')
        self.assertGreaterEqual(c.parallel, 1)
        self.assertIs(c.sbuild_together, False)
        self.assertEqual(c.sbuild_resolver, [])
        self.assertEqual(c.apt_key,
                '/usr/share/keyrings/debian-archive-keyring.gpg')
        self.assertIsNone(c.dpkg_source_diff_ignore)
        self.assertEqual(c.dpkg_source_tar_ignore, [])
        self.assertEqual(c.dpkg_source_extend_diff_ignore, [])
        self.assertEqual(c.output_builds, '..')
        self.assertEqual(c.architecture, 'mips')
        self.assertEqual(c.worker_architecture, 'mips')

        with self.assertRaises(AttributeError):
            c.apt_suite

        # Below this point relies on knowledge of distro_info
        try:
            import distro_info
        except ImportError:
            return

        debian_info = distro_info.DebianDistroInfo()
        self.assertEqual(debian.default_worker_suite,
                debian_info.stable())
        self.assertIs(c.sbuild_worker_suite,
                c.get_suite(debian, debian_info.stable()))
        self.assertIs(c.worker_suite, c.get_suite(debian, 
            debian_info.stable()))

        self.assertEqual(str(c.get_suite(debian, 'unstable')),
                'sid')
        self.assertEqual(str(c.get_suite(debian, 'testing')),
                debian_info.testing())
        self.assertEqual(str(c.get_suite(debian, 'oldstable')),
                debian_info.old())
        self.assertEqual(str(c.get_suite(debian, 'rc-buggy')),
                'experimental')
        stable = c.get_suite(debian, 'stable')
        self.assertEqual(str(stable), debian_info.stable())

    def test_debian_experimental(self):
        c = self.__config
        c.vendor = 'debian'
        c.suite = 'experimental'

        debian = c.get_vendor('debian')
        self.assertIs(c.vendor, debian)

        experimental = c.get_suite(debian, 'experimental')
        self.assertIs(c.get_suite(debian, 'rc-buggy'), experimental)
        self.assertIs(c.suite, experimental)

        # Properties of the suite itself
        self.assertEqual(list(experimental.hierarchy),
                [experimental, c.get_suite(debian, 'sid')])
        self.assertIs(experimental.base, c.get_suite(debian, 'sid'))
        self.assertEqual(experimental.sbuild_resolver[0],
                '--build-dep-resolver=aspcud')

        # Properties of the Config determined by the suite being
        # Debian experimental
        self.assertEqual(c.sbuild_resolver[0], '--build-dep-resolver=aspcud')

    def test_debian_wheezy(self):
        c = self.__config
        c.vendor = 'debian'
        c.suite = 'wheezy'

        debian = c.get_vendor('debian')
        self.assertIs(c.vendor, debian)

        wheezy = c.get_suite(debian, 'wheezy', True)
        self.assertEqual(list(wheezy.hierarchy), [wheezy])
        self.assertIs(c.suite, wheezy)
        self.assertEqual(wheezy.components, {'main'})
        self.assertEqual(wheezy.extra_components, {'contrib', 'non-free'})
        self.assertEqual(wheezy.all_components, {'main', 'contrib',
            'non-free'})
        self.assertIs(wheezy.vendor, debian)
        self.assertIs(wheezy.base, None)
        self.assertEqual(wheezy.apt_suite, 'wheezy')
        self.assertEqual(wheezy.archive, 'debian')
        self.assertEqual(
            c.get_mirrors().lookup_suite(wheezy),
            'http://192.168.122.1:3142/debian')

        # Properties of the Config determined by it being wheezy
        self.assertEqual(c.autopkgtest, ['lxc', 'qemu'])
        self.assertEqual(c.default_suite, 'sid')
        self.assertEqual(c.components, {'main'})
        self.assertEqual(c.extra_components, {'contrib', 'non-free'})
        self.assertEqual(c.all_components, {'main', 'contrib',
            'non-free'})
        self.assertIs(c.vendor, debian)
        self.assertIs(c.worker_vendor, debian)
        self.assertIs(c.sbuild_worker_vendor, debian)
        self.assertIs(c.vmdebootstrap_worker_vendor, debian)
        self.assertIs(c.vmdebootstrap_worker_suite,
                c.get_suite(debian, 'jessie'))
        self.assertEqual(c.vmdebootstrap_options,
                ['--boottype=ext3', '--extlinux', '--mbr', '--no-grub',
                    '--enable-dhcp'])
        with self.assertRaises(AttributeError):
            c.archive
        self.assertEqual(c.qemu_image_size, '42G')
        self.assertGreaterEqual(c.parallel, 1)
        self.assertIs(c.sbuild_together, False)
        self.assertEqual(c.sbuild_resolver, [])
        self.assertEqual(c.apt_key,
                '/usr/share/keyrings/debian-archive-keyring.gpg')
        self.assertIsNone(c.dpkg_source_diff_ignore)
        self.assertEqual(c.dpkg_source_tar_ignore, [])
        self.assertEqual(c.dpkg_source_extend_diff_ignore, [])
        self.assertEqual(c.output_builds, '..')
        self.assertEqual(c.debootstrap_script, 'wheezy')
        self.assertIs(c.suite, wheezy)

        try:
            import distro_info
        except ImportError:
            return

        stable = c.get_suite(debian, 'stable')
        self.assertIs(c.worker_suite, stable)
        self.assertIs(c.sbuild_worker_suite, stable)

    def test_debian_buildd(self):
        c = self.__config
        c.vendor = 'debian'
        c.suite = 'jessie-apt.buildd.debian.org'

        debian = c.get_vendor('debian')
        self.assertIs(c.vendor, debian)

        jessie = c.get_suite(debian, 'jessie')
        buildd = c.get_suite(debian, 'jessie-apt.buildd.debian.org')
        self.assertIs(c.suite, buildd)

        self.assertEqual(list(buildd.hierarchy), [buildd, jessie])
        self.assertIs(buildd.base, jessie)
        self.assertEqual(buildd.components, {'main'})
        self.assertEqual(buildd.extra_components, {'contrib', 'non-free'})
        self.assertEqual(buildd.all_components, {'main', 'contrib',
            'non-free'})
        self.assertIs(buildd.vendor, debian)
        self.assertEqual(buildd.apt_suite, 'jessie')
        self.assertEqual(buildd.apt_key,
                os.path.join(os.path.dirname(vectis.config.__file__),
                    'keys', 'buildd.debian.org_archive_key_2017_2018.gpg'))
        self.assertEqual(buildd.archive, 'apt.buildd.debian.org')
        self.assertEqual(
            c.get_mirrors().lookup_suite(buildd),
            'http://192.168.122.1:3142/apt.buildd.debian.org')

        # Properties of the Config determined by it being jessie
        self.assertEqual(c.autopkgtest, ['lxc', 'qemu'])
        self.assertEqual(c.default_suite, 'sid')
        self.assertEqual(c.components, {'main'})
        self.assertEqual(c.extra_components, {'contrib', 'non-free'})
        self.assertEqual(c.all_components, {'main', 'contrib',
            'non-free'})
        self.assertIs(c.vendor, debian)
        self.assertIs(c.worker_vendor, debian)
        self.assertIs(c.sbuild_worker_vendor, debian)
        self.assertIs(c.vmdebootstrap_worker_vendor, debian)
        with self.assertRaises(AttributeError):
            c.archive
        self.assertEqual(c.qemu_image_size, '42G')
        self.assertGreaterEqual(c.parallel, 1)
        self.assertIs(c.sbuild_together, False)
        self.assertEqual(c.sbuild_resolver, [])
        self.assertEqual(c.apt_key,
                os.path.join(os.path.dirname(vectis.config.__file__),
                    'keys', 'buildd.debian.org_archive_key_2017_2018.gpg'))
        self.assertIsNone(c.dpkg_source_diff_ignore)
        self.assertEqual(c.dpkg_source_tar_ignore, [])
        self.assertEqual(c.dpkg_source_extend_diff_ignore, [])
        self.assertEqual(c.output_builds, '..')
        # FIXME: this makes little sense
        self.assertEqual(c.debootstrap_script, 'jessie-apt.buildd.debian.org')

        try:
            import distro_info
        except ImportError:
            return

        stable = c.get_suite(debian, 'stable')
        self.assertIs(c.worker_suite, stable)
        self.assertIs(c.sbuild_worker_suite, stable)

    def test_debian_backports(self):
        try:
            import distro_info
        except ImportError:
            return

        c = self.__config
        c.vendor = 'debian'
        c.suite = 'stable-backports'

        debian = c.get_vendor('debian')

        self.assertIs(c.vendor, debian)

        debian_info = distro_info.DebianDistroInfo()
        backports = c.get_suite(debian, 'stable-backports')
        stable = c.get_suite(debian, 'stable')
        self.assertIs(c.suite, backports)
        self.assertEqual(str(backports),
                debian_info.stable() + '-backports')
        self.assertEqual(backports.hierarchy[0], backports)
        self.assertEqual(str(backports.hierarchy[1]), str(stable))
        self.assertEqual(backports.sbuild_resolver,
                ['--build-dep-resolver=aptitude'])
        self.assertEqual(
            c.get_mirrors().lookup_suite(backports),
            'http://192.168.122.1:3142/debian')
        self.assertEqual(backports.archive, 'debian')

        self.assertEqual(c.sbuild_resolver,
                ['--build-dep-resolver=aptitude'])

    def test_debian_stable_security(self):
        c = self.__config
        c.vendor = 'debian'
        c.suite = 'stable-security'

        try:
            import distro_info
        except ImportError:
            return

        debian = c.get_vendor('debian')
        self.assertIs(c.vendor, debian)

        debian_info = distro_info.DebianDistroInfo()
        security = c.get_suite(debian, 'stable-security')
        stable = c.get_suite(debian, 'stable')

        self.assertEqual(security.apt_suite,
                '{}/updates'.format(debian_info.stable()))
        self.assertEqual(
            c.get_mirrors().lookup_suite(security),
            'http://192.168.122.1:3142/security.debian.org')
        self.assertEqual(security.archive, 'security.debian.org')
        self.assertEqual(security.hierarchy[0], security)
        self.assertEqual(str(security.hierarchy[1]), str(stable))

        with self.assertRaises(AttributeError):
            c.archive

    def test_debian_wheezy_security(self):
        c = self.__config
        c.vendor = 'debian'
        c.suite = 'wheezy-security'

        debian = c.get_vendor('debian')
        self.assertIs(c.vendor, debian)

        wheezy = c.get_suite(debian, 'wheezy', True)
        sec = c.get_suite(debian, 'wheezy-security', True)
        self.assertEqual(list(wheezy.hierarchy), [wheezy])
        self.assertEqual(list(sec.hierarchy), [sec, wheezy])
        self.assertIs(c.suite, sec)

        # Properties of the Config determined by it being wheezy-security
        # We inherit these from wheezy
        self.assertIs(c.vmdebootstrap_worker_suite,
                c.get_suite(debian, 'jessie'))
        self.assertEqual(c.vmdebootstrap_options,
                ['--boottype=ext3', '--extlinux', '--mbr', '--no-grub',
                    '--enable-dhcp'])

    def test_ubuntu(self):
        c = self.__config
        c.vendor = 'ubuntu'
        ubuntu = c.get_vendor('ubuntu')

        self.assertIs(c.vendor, ubuntu)

        self.assertEqual(str(ubuntu), 'ubuntu')
        self.assertIsNone(c.get_suite(ubuntu, 'unstable', create=False))
        self.assertIsNone(c.get_suite(ubuntu, 'stable', create=False))

        self.assertEqual(c.components, {'main', 'universe'})
        self.assertEqual(c.extra_components, {'restricted',
            'multiverse'})
        self.assertEqual(c.all_components, {'main', 'universe',
            'restricted', 'multiverse'})
        self.assertIs(c.vendor, ubuntu)
        self.assertIs(c.worker_vendor, ubuntu)
        self.assertIs(c.sbuild_worker_vendor, ubuntu)
        self.assertIs(c.vmdebootstrap_worker_vendor, ubuntu)
        with self.assertRaises(AttributeError):
            c.archive
        self.assertEqual(c.autopkgtest, ['lxc', 'qemu'])
        self.assertEqual(c.components, {'main', 'universe'})
        self.assertEqual(c.extra_components, {'restricted',
            'multiverse'})
        self.assertEqual(c.all_components, {'main', 'universe',
            'restricted', 'multiverse'})
        self.assertIs(c.vendor, ubuntu)
        self.assertEqual(c.qemu_image_size, '42G')
        self.assertGreaterEqual(c.parallel, 1)
        self.assertIs(c.sbuild_together, False)
        self.assertEqual(c.sbuild_resolver, [])
        self.assertEqual(c.apt_key,
                '/usr/share/keyrings/ubuntu-archive-keyring.gpg')
        with self.assertRaises(AttributeError):
            c.apt_suite
        self.assertIsNone(c.dpkg_source_diff_ignore)
        self.assertEqual(c.dpkg_source_tar_ignore, [])
        self.assertEqual(c.dpkg_source_extend_diff_ignore, [])
        self.assertEqual(c.output_builds, '..')

        try:
            import distro_info
        except ImportError:
            return

        ubuntu_info = distro_info.UbuntuDistroInfo()

        try:
            ubuntu_devel = ubuntu_info.devel()
        except distro_info.DistroDataOutdated:
            ubuntu_devel = ubuntu_info.stable()

        self.assertEqual(str(c.get_suite(ubuntu, 'devel')), ubuntu_devel)
        self.assertEqual(ubuntu.default_suite, ubuntu_devel)
        self.assertEqual(ubuntu.default_worker_suite,
                ubuntu_info.lts() + '-backports')
        devel = c.get_suite(ubuntu, 'devel')
        self.assertEqual(devel.archive, 'ubuntu')
        self.assertEqual(
            c.get_mirrors().lookup_suite(devel),
            'http://mirror/ubuntu')

        backports = c.get_suite(ubuntu, ubuntu_info.lts() + '-backports')
        self.assertEqual(c.worker_suite, backports)
        self.assertEqual(c.sbuild_worker_suite, backports)
        self.assertEqual(c.vmdebootstrap_worker_suite, backports)
        self.assertEqual(backports.archive, 'ubuntu')
        self.assertEqual(
            c.get_mirrors().lookup_suite(backports),
            'http://mirror/ubuntu')

    def test_ubuntu_xenial(self):
        c = self.__config
        c.vendor = 'ubuntu'
        c.suite = 'xenial'

        ubuntu = c.get_vendor('ubuntu')
        xenial = c.get_suite(ubuntu, 'xenial', True)
        self.assertEqual(list(xenial.hierarchy), [xenial])
        self.assertEqual(xenial.components, {'main', 'universe'})
        self.assertEqual(xenial.extra_components, {'multiverse',
            'restricted'})
        self.assertEqual(xenial.all_components, {'main', 'universe',
            'multiverse', 'restricted'})
        self.assertIs(xenial.base, None)
        self.assertEqual(xenial.archive, 'ubuntu')
        self.assertEqual(
            c.get_mirrors().lookup_suite(xenial),
            'http://mirror/ubuntu')
        self.assertEqual(xenial.apt_key,
                '/usr/share/keyrings/ubuntu-archive-keyring.gpg')
        self.assertEqual(xenial.apt_suite, 'xenial')

        self.assertEqual(c.components, {'main', 'universe'})
        self.assertEqual(c.extra_components, {'multiverse',
            'restricted'})
        self.assertEqual(c.all_components, {'main', 'universe',
            'multiverse', 'restricted'})
        self.assertIs(c.vendor, ubuntu)
        self.assertIs(c.worker_vendor, ubuntu)
        self.assertIs(c.sbuild_worker_vendor, ubuntu)
        self.assertIs(c.vmdebootstrap_worker_vendor, ubuntu)

        with self.assertRaises(AttributeError):
            c.archive
        self.assertEqual(c.qemu_image_size, '42G')
        self.assertGreaterEqual(c.parallel, 1)
        self.assertIs(c.sbuild_together, False)
        self.assertEqual(c.sbuild_resolver, [])
        self.assertEqual(c.apt_key,
                '/usr/share/keyrings/ubuntu-archive-keyring.gpg')
        self.assertIsNone(c.dpkg_source_diff_ignore)
        self.assertEqual(c.dpkg_source_tar_ignore, [])
        self.assertEqual(c.dpkg_source_extend_diff_ignore, [])
        self.assertEqual(c.output_builds, '..')
        self.assertEqual(c.debootstrap_script, 'xenial')
        self.assertIs(c.suite, xenial)

        try:
            import distro_info
        except ImportError:
            return

        ubuntu_info = distro_info.UbuntuDistroInfo()
        backports = c.get_suite(ubuntu, ubuntu_info.lts() + '-backports')
        self.assertIs(c.worker_suite, backports)
        self.assertIs(c.sbuild_worker_suite, backports)
        self.assertIs(c.vmdebootstrap_worker_suite, backports)

        try:
            ubuntu_devel = ubuntu_info.devel()
        except distro_info.DistroDataOutdated:
            ubuntu_devel = ubuntu_info.stable()

        # FIXME: this seems wrong
        self.assertEqual(c.default_suite, ubuntu_devel)

    def test_ubuntu_xenial_security(self):
        c = self.__config
        c.vendor = 'ubuntu'
        c.suite = 'xenial-security'

        ubuntu = c.get_vendor('ubuntu')
        sec = c.get_suite(ubuntu, 'xenial-security', True)
        xenial = c.get_suite(ubuntu, 'xenial', True)
        self.assertEqual(list(sec.hierarchy), [sec, xenial])
        self.assertIs(sec.base, xenial)
        self.assertEqual(sec.components, {'main', 'universe'})
        self.assertEqual(sec.extra_components, {'multiverse',
            'restricted'})
        self.assertEqual(sec.all_components, {'main', 'universe',
            'multiverse', 'restricted'})
        self.assertEqual(sec.archive, 'ubuntu')
        self.assertEqual(
            c.get_mirrors().lookup_suite(sec),
            'http://mirror/ubuntu')
        self.assertEqual(sec.apt_key,
                '/usr/share/keyrings/ubuntu-archive-keyring.gpg')
        self.assertEqual(sec.apt_suite, 'xenial-security')

        with self.assertRaises(AttributeError):
            c.archive
        self.assertEqual(c.qemu_image_size, '42G')
        self.assertGreaterEqual(c.parallel, 1)
        self.assertIs(c.sbuild_together, False)
        self.assertEqual(c.sbuild_resolver, [])
        self.assertEqual(c.apt_key,
                '/usr/share/keyrings/ubuntu-archive-keyring.gpg')
        self.assertIsNone(c.dpkg_source_diff_ignore)
        self.assertEqual(c.dpkg_source_tar_ignore, [])
        self.assertEqual(c.dpkg_source_extend_diff_ignore, [])
        self.assertEqual(c.output_builds, '..')
        self.assertEqual(c.debootstrap_script, 'xenial-security')
        self.assertIs(c.suite, sec)

        try:
            import distro_info
        except ImportError:
            return

        ubuntu_info = distro_info.UbuntuDistroInfo()
        backports = c.get_suite(ubuntu, ubuntu_info.lts() + '-backports')
        self.assertIs(c.worker_suite, backports)
        self.assertIs(c.sbuild_worker_suite, backports)
        self.assertIs(c.vmdebootstrap_worker_suite, backports)

    def test_unknown_vendor(self):
        c = self.__config
        c.vendor = 'steamos'
        c.suite = 'brewmaster'

        steamos = c.get_vendor('steamos')
        debian = c.get_vendor('debian')
        brewmaster = c.get_suite(steamos, 'brewmaster')

        self.assertEqual(str(steamos), 'steamos')
        self.assertEqual(steamos.components, {'main'})
        self.assertEqual(list(brewmaster.hierarchy), [brewmaster])
        with self.assertRaises(AttributeError):
            steamos.archive

        self.assertEqual(c.components, {'main'})
        self.assertEqual(c.vendor, steamos)
        self.assertIs(c.worker_vendor, debian)
        self.assertIs(c.sbuild_worker_vendor, debian)
        self.assertIs(c.vmdebootstrap_worker_vendor, debian)
        with self.assertRaises(AttributeError):
            c.archive
        self.assertEqual(c.autopkgtest, ['schroot', 'qemu'])

        self.assertIsNone(c.get_suite(steamos, 'xyzzy', create=False))
        self.assertIsNotNone(c.get_suite(steamos, 'xyzzy'))
        self.assertIs(
            c.get_suite(steamos, 'xyzzy'),
            c.get_suite(steamos, 'xyzzy'))

        self.assertEqual(
            c.get_mirrors().lookup_suite(brewmaster),
            'http://localhost/steamos')
        self.assertEqual(brewmaster.archive, 'steamos')

        try:
            import distro_info
        except ImportError:
            return

        debian_info = distro_info.DebianDistroInfo()
        self.assertIs(
            c.worker_suite,
            c.get_suite(debian, debian_info.stable()))

    def test_cross_vendor(self):
        c = self.__config
        c.vendor = 'steamrt'
        c.suite = 'scout'

        steamrt = c.get_vendor('steamrt')
        ubuntu = c.get_vendor('ubuntu')
        scout = c.get_suite(steamrt, 'scout')
        precise = c.get_suite(ubuntu, 'precise')

        self.assertEqual(list(scout.hierarchy), [scout, precise])

        self.assertEqual(c.components, {'main', 'contrib', 'non-free'})
        self.assertEqual(c.vendor, steamrt)

        # TODO: not sure whether it's correct for these to be inherited
        # from Ubuntu due to the cross-vendor base suite?
        self.assertIs(c.worker_vendor, ubuntu)
        self.assertIs(c.sbuild_worker_vendor, ubuntu)
        self.assertIs(c.vmdebootstrap_worker_vendor, ubuntu)

        # TODO: not sure whether it's correct for these to be inherited
        # from Ubuntu due to the cross-vendor base suite?
        self.assertEqual(c.autopkgtest, ['lxc', 'qemu'])

        self.assertEqual(
            c.get_mirrors().lookup_suite(scout),
            'http://192.168.122.1:3142/repo.steamstatic.com/steamrt')
        self.assertEqual(scout.archive, 'repo.steamstatic.com/steamrt')

        try:
            import distro_info
        except ImportError:
            return

        ubuntu_info = distro_info.UbuntuDistroInfo()
        self.assertIs(
            c.worker_suite,
            c.get_suite(ubuntu, ubuntu_info.lts() + '-backports'))

    def tearDown(self):
        pass

if __name__ == '__main__':
    import tap
    runner = tap.TAPTestRunner()
    runner.set_stream(True)
    unittest.main(verbosity=2, testRunner=runner)
