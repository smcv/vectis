#!/usr/bin/python3

# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import os
import subprocess
import unittest

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

class DefaultsTestCase(unittest.TestCase):
    def setUp(self):
        self.__config = Config(config_layers=(dict(
                    defaults=dict(
                        apt_cacher_ng='http://192.168.122.1:3142',
                        architecture='mips',
                        )),),
                current_directory='/')

    def test_defaults(self):
        self.__config = Config(config_layers=({},), current_directory='/')
        c = self.__config

        self.assertGreaterEqual(c.parallel, 1)
        self.assertIs(type(c.parallel), int)

        debian = c._get_vendor('debian')
        ubuntu = c._get_vendor('ubuntu')

        self.assertEqual(str(c.vendor), 'debian')
        self.assertEqual(str(c.worker_vendor), 'debian')
        self.assertEqual(str(c.vmdebootstrap_worker_vendor),
                'debian')
        self.assertEqual(str(c.sbuild_worker_vendor), 'debian')
        self.assertIs(c.vendor, debian)
        self.assertIs(c.worker_vendor, debian)
        self.assertIs(c.sbuild_worker_vendor, debian)
        self.assertIs(c.vmdebootstrap_worker_vendor, debian)
        self.assertEqual(c.archive, 'debian')
        self.assertEqual(c.apt_cacher_ng, None)
        self.assertEqual(c.force_parallel, 0)
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
            self.assertEqual(c.autopkgtest_qemu_image,
                    '{}/vectis/{}/debian/sid/autopkgtest.qcow2'.format(
                        XDG_CACHE_HOME, ARCHITECTURE))
            self.assertEqual(c.write_qemu_image,
                    '{}/vectis/{}/debian/sid/autopkgtest.qcow2'.format(
                        XDG_CACHE_HOME, ARCHITECTURE))
            self.assertEqual(c.worker_architecture, ARCHITECTURE)
            self.assertEqual(c.worker,
                    'qemu {}'.format(c.worker_qemu_image))
            self.assertEqual(c.worker_qemu_image,
                    '{}/vectis/{}/debian/sid/autopkgtest.qcow2'.format(
                        XDG_CACHE_HOME, ARCHITECTURE))
            self.assertEqual(c.sbuild_worker,
                    'qemu {}'.format(c.sbuild_worker_qemu_image))
            self.assertEqual(c.sbuild_worker_qemu_image,
                    '{}/vectis/{}/debian/sid/autopkgtest.qcow2'.format(
                        XDG_CACHE_HOME, ARCHITECTURE))

        self.assertEqual(c.autopkgtest, ['qemu'])
        self.assertEqual(c.suite, None)

        try:
            import distro_info
        except ImportError:
            pass
        else:
            self.assertEqual(c.worker_suite,
                    c.vendor.get_suite(
                        distro_info.DebianDistroInfo().testing()))
            self.assertEqual(c.default_worker_suite,
                        distro_info.DebianDistroInfo().testing())

        jb = c.vendor.get_suite('jessie-apt.buildd.debian.org')
        self.assertEqual(c.sbuild_worker_suite, jb)
        self.assertEqual(c.default_suite, 'sid')
        self.assertEqual(c.components, {'main'})
        self.assertEqual(c.extra_components,
                {'contrib', 'non-free'})
        self.assertEqual(c.all_components, {'main',
            'contrib', 'non-free'})

        self.assertEqual(c.storage,
            '{}/vectis'.format(XDG_CACHE_HOME))

        with self.assertRaises(ConfigError): c.mirror
        with self.assertRaises(ConfigError): c.bootstrap_mirror

    def test_substitutions(self):
        c = self.__config

        c.architecture = 'm68k'
        c.suite = 'potato'
        c.worker_suite = 'sarge'
        c.sbuild_worker_suite = 'alchemist'
        c.sbuild_worker_vendor = 'steamos'
        c.vmdebootstrap_worker_suite = 'xenial'
        c.vmdebootstrap_worker_vendor = 'ubuntu'

        debian = c._get_vendor('debian')
        potato = debian.get_suite('potato')
        sarge = debian.get_suite('sarge')
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
                'qemu {}/m68k/debian/sarge/autopkgtest.qcow2'.format(
                    c.storage))

        self.assertEqual(c.sbuild_worker_qemu_image,
                '{}/m68k/steamos/alchemist/autopkgtest.qcow2'.format(
                    c.storage))
        self.assertEqual(c.vmdebootstrap_worker_qemu_image,
                '{}/m68k/ubuntu/xenial/autopkgtest.qcow2'.format(
                    c.storage))

        self.assertEqual(c.mirror,
                'http://192.168.122.1:3142/debian')
        self.assertEqual(c.bootstrap_mirror,
                'http://192.168.122.1:3142/debian')

        self.assertEqual(potato.mirror,
                'http://192.168.122.1:3142/debian')
        self.assertEqual(sarge.mirror,
                'http://192.168.122.1:3142/debian')

    def test_debian(self):
        c = self.__config
        c.vendor = 'debian'
        c.suite = 'sid'

        debian = c._get_vendor('debian')
        self.assertIs(c.vendor, debian)

        sid = debian.get_suite('sid')

        self.assertIs(c.suite, sid)

        # Properties of the vendor itself
        self.assertEqual(str(debian), 'debian')
        self.assertEqual(debian.default_suite, 'sid')
        self.assertIs(debian.get_suite('unstable'), sid)
        self.assertEqual(debian.components, {'main'})
        self.assertEqual(debian.extra_components, {'contrib', 'non-free'})
        self.assertEqual(debian.all_components, {'main', 'contrib',
            'non-free'})
        self.assertIsNone(debian.get_suite('xenial', create=False))

        # Properties of the suite itswelf
        self.assertEqual(sid.apt_key,
                '/usr/share/keyrings/debian-archive-keyring.gpg')
        self.assertEqual(sid.mirror, 'http://192.168.122.1:3142/debian')
        self.assertEqual(sid.force_parallel, 0)
        self.assertIs(sid.base, None)
        self.assertEqual(sid.components, {'main'})
        self.assertEqual(sid.extra_components, {'contrib', 'non-free'})
        self.assertEqual(sid.all_components, {'main', 'contrib', 'non-free'})
        self.assertEqual(sid.apt_suite, 'sid')

        # Properties of the Config determined by the suite being Debian sid
        self.assertEqual(c.autopkgtest, ['qemu'])
        self.assertIs(c.worker_vendor, debian)
        self.assertIs(c.sbuild_worker_vendor, debian)
        self.assertIs(c.vmdebootstrap_worker_vendor, debian)
        self.assertIs(c.sbuild_worker_suite,
                debian.get_suite('jessie-apt.buildd.debian.org'))
        self.assertEqual(c.archive, 'debian')
        self.assertEqual(c.apt_cacher_ng, 'http://192.168.122.1:3142')
        self.assertEqual(c.mirror, 'http://192.168.122.1:3142/debian')
        self.assertEqual(c.bootstrap_mirror, 'http://192.168.122.1:3142/debian')
        self.assertEqual(c.qemu_image_size, '42G')
        self.assertEqual(c.force_parallel, 0)
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

        # Below this point relies on knowledge of distro_info
        try:
            import distro_info
        except ImportError:
            return

        debian_info = distro_info.DebianDistroInfo()
        self.assertEqual(debian.default_worker_suite, debian_info.testing())
        self.assertIs(c.worker_suite, debian.get_suite('testing'))

        self.assertEqual(str(debian.get_suite('unstable')),
                'sid')
        self.assertEqual(str(debian.get_suite('testing')),
                debian_info.testing())
        self.assertEqual(str(debian.get_suite('oldstable')),
                debian_info.old())
        self.assertEqual(str(debian.get_suite('rc-buggy')),
                'experimental')
        stable = debian.get_suite('stable')
        self.assertEqual(str(stable), debian_info.stable())

    def test_debian_experimental(self):
        c = self.__config
        c.vendor = 'debian'
        c.suite = 'experimental'

        debian = c._get_vendor('debian')
        self.assertIs(c.vendor, debian)

        experimental = debian.get_suite('experimental')
        self.assertIs(debian.get_suite('rc-buggy'), experimental)
        self.assertIs(c.suite, experimental)

        # Properties of the suite itself
        self.assertEqual(list(experimental.hierarchy),
                [experimental, debian.get_suite('sid')])
        self.assertIs(experimental.base, debian.get_suite('sid'))

        # Properties of the Config determined by the suite being
        # Debian experimental
        self.assertEqual(c.sbuild_resolver[0], '--build-dep-resolver=aspcud')

    def test_debian_jessie(self):
        c = self.__config
        c.vendor = 'debian'
        c.suite = 'jessie'

        debian = c._get_vendor('debian')
        self.assertIs(c.vendor, debian)

        jessie = debian.get_suite('jessie', True)
        self.assertEqual(list(jessie.hierarchy), [jessie])
        self.assertIs(c.suite, jessie)
        self.assertEqual(jessie.components, {'main'})
        self.assertEqual(jessie.extra_components, {'contrib', 'non-free'})
        self.assertEqual(jessie.all_components, {'main', 'contrib',
            'non-free'})
        self.assertIs(jessie.vendor, debian)
        self.assertEqual(jessie.force_parallel, 1)
        self.assertIs(jessie.base, None)
        self.assertEqual(jessie.apt_suite, 'jessie')

        # Properties of the Config determined by it being jessie
        self.assertEqual(c.autopkgtest, ['qemu'])
        self.assertEqual(c.default_suite, 'sid')
        self.assertEqual(c.components, {'main'})
        self.assertEqual(c.extra_components, {'contrib', 'non-free'})
        self.assertEqual(c.all_components, {'main', 'contrib',
            'non-free'})
        self.assertIs(c.vendor, debian)
        self.assertIs(c.worker_vendor, debian)
        self.assertIs(c.sbuild_worker_vendor, debian)
        self.assertIs(c.vmdebootstrap_worker_vendor, debian)
        self.assertIs(c.sbuild_worker_suite,
                debian.get_suite('jessie-apt.buildd.debian.org'))
        self.assertEqual(c.archive, 'debian')
        self.assertEqual(c.apt_cacher_ng, 'http://192.168.122.1:3142')
        self.assertEqual(c.mirror, 'http://192.168.122.1:3142/debian')
        self.assertEqual(c.bootstrap_mirror, 'http://192.168.122.1:3142/debian')
        self.assertEqual(c.qemu_image_size, '42G')
        self.assertEqual(c.force_parallel, 1)
        self.assertGreaterEqual(c.parallel, 1)
        self.assertIs(c.sbuild_together, False)
        self.assertEqual(c.sbuild_resolver, [])
        self.assertEqual(c.apt_key,
                '/usr/share/keyrings/debian-archive-keyring.gpg')
        self.assertIsNone(c.dpkg_source_diff_ignore)
        self.assertEqual(c.dpkg_source_tar_ignore, [])
        self.assertEqual(c.dpkg_source_extend_diff_ignore, [])
        self.assertEqual(c.output_builds, '..')
        self.assertEqual(c.debootstrap_script, 'jessie')
        self.assertIs(c.suite, jessie)

        try:
            import distro_info
        except ImportError:
            return

        testing = debian.get_suite('testing')
        self.assertIs(c.worker_suite, testing)

    def test_debian_buildd(self):
        c = self.__config
        c.vendor = 'debian'
        c.suite = 'jessie-apt.buildd.debian.org'

        debian = c._get_vendor('debian')
        self.assertIs(c.vendor, debian)

        jessie = debian.get_suite('jessie')
        buildd = debian.get_suite('jessie-apt.buildd.debian.org')
        self.assertIs(c.suite, buildd)

        self.assertEqual(list(buildd.hierarchy), [buildd, jessie])
        self.assertIs(buildd.base, jessie)
        self.assertEqual(buildd.components, {'main'})
        self.assertEqual(buildd.extra_components, {'contrib', 'non-free'})
        self.assertEqual(buildd.all_components, {'main', 'contrib',
            'non-free'})
        self.assertIs(buildd.vendor, debian)
        self.assertEqual(buildd.force_parallel, 1)
        self.assertEqual(buildd.apt_suite, 'jessie')
        self.assertEqual(buildd.apt_key,
                os.path.join(os.path.dirname(vectis.config.__file__),
                    'keys', 'buildd.debian.org_archive_key_2015_2016.gpg'))

        # Properties of the Config determined by it being jessie
        self.assertEqual(c.autopkgtest, ['qemu'])
        self.assertEqual(c.default_suite, 'sid')
        self.assertEqual(c.components, {'main'})
        self.assertEqual(c.extra_components, {'contrib', 'non-free'})
        self.assertEqual(c.all_components, {'main', 'contrib',
            'non-free'})
        self.assertIs(c.vendor, debian)
        self.assertIs(c.worker_vendor, debian)
        self.assertIs(c.sbuild_worker_vendor, debian)
        self.assertIs(c.vmdebootstrap_worker_vendor, debian)
        self.assertIs(c.sbuild_worker_suite, buildd)
        self.assertEqual(c.archive, 'apt.buildd.debian.org')
        self.assertEqual(c.apt_cacher_ng, 'http://192.168.122.1:3142')
        self.assertEqual(c.mirror, 'http://192.168.122.1:3142/apt.buildd.debian.org')
        self.assertEqual(c.bootstrap_mirror,
                'http://192.168.122.1:3142/apt.buildd.debian.org')
        self.assertEqual(c.qemu_image_size, '42G')
        self.assertEqual(c.force_parallel, 1)
        self.assertGreaterEqual(c.parallel, 1)
        self.assertIs(c.sbuild_together, False)
        self.assertEqual(c.sbuild_resolver, [])
        self.assertEqual(c.apt_key,
                os.path.join(os.path.dirname(vectis.config.__file__),
                    'keys', 'buildd.debian.org_archive_key_2015_2016.gpg'))
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

        testing = debian.get_suite('testing')
        self.assertIs(c.worker_suite, testing)

    def test_debian_backports(self):
        try:
            import distro_info
        except ImportError:
            return

        c = self.__config
        c.vendor = 'debian'
        c.suite = 'stable-backports'

        debian = c._get_vendor('debian')

        self.assertIs(c.vendor, debian)

        debian_info = distro_info.DebianDistroInfo()
        backports = debian.get_suite('stable-backports')
        stable = debian.get_suite('stable')
        self.assertIs(c.suite, backports)
        self.assertEqual(str(backports),
                debian_info.stable() + '-backports')
        self.assertEqual(backports.hierarchy[0], backports)
        self.assertEqual(str(backports.hierarchy[1]), str(stable))

        self.assertEqual(c.sbuild_resolver,
                ['--build-dep-resolver=aptitude'])
        self.assertEqual(c.mirror,
                'http://192.168.122.1:3142/debian')

    def test_debian_stable_security(self):
        c = self.__config
        c.vendor = 'debian'
        c.suite = 'stable-security'

        try:
            import distro_info
        except ImportError:
            return

        debian = c._get_vendor('debian')
        self.assertIs(c.vendor, debian)

        debian_info = distro_info.DebianDistroInfo()
        security = debian.get_suite('stable-security')
        stable = debian.get_suite('stable')

        self.assertEqual(security.apt_suite,
                '{}/updates'.format(debian_info.stable()))
        self.assertEqual(security.mirror,
                'http://192.168.122.1:3142/security.debian.org')
        self.assertEqual(security.hierarchy[0], security)
        self.assertEqual(str(security.hierarchy[1]), str(stable))

        self.assertEqual(c.mirror,
                'http://192.168.122.1:3142/security.debian.org')

    def test_debian_jessie_security(self):
        c = self.__config
        c.vendor = 'debian'
        c.suite = 'jessie-security'

        debian = c._get_vendor('debian')
        self.assertIs(c.vendor, debian)

        jessie = debian.get_suite('jessie', True)
        sec = debian.get_suite('jessie-security', True)
        self.assertEqual(list(jessie.hierarchy), [jessie])
        self.assertEqual(list(sec.hierarchy), [sec, jessie])
        self.assertIs(c.suite, sec)

        # Properties of the Config determined by it being jessie-security
        # We inherit force_parallel = 1 from jessie
        self.assertEqual(c.force_parallel, 1)

    def test_ubuntu(self):
        c = self.__config
        c.vendor = 'ubuntu'
        ubuntu = c._get_vendor('ubuntu')

        self.assertIs(c.vendor, ubuntu)

        self.assertEqual(str(ubuntu), 'ubuntu')
        self.assertEqual(ubuntu.mirror, 'http://192.168.122.1:3142/ubuntu')
        self.assertIsNone(ubuntu.get_suite('unstable', create=False))
        self.assertIsNone(ubuntu.get_suite('stable', create=False))

        self.assertEqual(c.components, {'main', 'universe'})
        self.assertEqual(c.extra_components, {'restricted',
            'multiverse'})
        self.assertEqual(c.all_components, {'main', 'universe',
            'restricted', 'multiverse'})
        self.assertIs(c.vendor, ubuntu)
        self.assertIs(c.worker_vendor, ubuntu)
        self.assertIs(c.sbuild_worker_vendor, ubuntu)
        self.assertIs(c.vmdebootstrap_worker_vendor, ubuntu)
        self.assertEqual(c.archive, 'ubuntu')
        self.assertEqual(c.mirror, 'http://192.168.122.1:3142/ubuntu')
        self.assertEqual(c.autopkgtest, ['qemu'])
        self.assertEqual(c.components, {'main', 'universe'})
        self.assertEqual(c.extra_components, {'restricted',
            'multiverse'})
        self.assertEqual(c.all_components, {'main', 'universe',
            'restricted', 'multiverse'})
        self.assertIs(c.vendor, ubuntu)
        self.assertEqual(c.archive, 'ubuntu')
        self.assertEqual(c.apt_cacher_ng, 'http://192.168.122.1:3142')
        self.assertEqual(c.mirror, 'http://192.168.122.1:3142/ubuntu')
        self.assertEqual(c.bootstrap_mirror, 'http://192.168.122.1:3142/ubuntu')
        self.assertEqual(c.qemu_image_size, '42G')
        self.assertEqual(c.force_parallel, 0)
        self.assertGreaterEqual(c.parallel, 1)
        self.assertIs(c.sbuild_together, False)
        self.assertEqual(c.sbuild_resolver, [])
        self.assertEqual(c.apt_key,
                '/usr/share/keyrings/ubuntu-archive-keyring.gpg')
        self.assertIsNone(c.apt_suite)
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

        self.assertEqual(str(ubuntu.get_suite('devel')), ubuntu_devel)
        self.assertEqual(ubuntu.default_suite, ubuntu_devel)
        self.assertEqual(ubuntu.default_worker_suite, ubuntu_info.lts())

        lts = ubuntu.get_suite(ubuntu_info.lts())
        self.assertEqual(c.worker_suite, lts)
        self.assertEqual(c.sbuild_worker_suite, lts)
        self.assertEqual(c.vmdebootstrap_worker_suite, lts)

    def test_ubuntu_xenial(self):
        c = self.__config
        c.vendor = 'ubuntu'
        c.suite = 'xenial'

        ubuntu = c._get_vendor('ubuntu')
        xenial = ubuntu.get_suite('xenial', True)
        self.assertEqual(list(xenial.hierarchy), [xenial])
        self.assertEqual(xenial.components, {'main', 'universe'})
        self.assertEqual(xenial.extra_components, {'multiverse',
            'restricted'})
        self.assertEqual(xenial.all_components, {'main', 'universe',
            'multiverse', 'restricted'})
        self.assertEqual(xenial.force_parallel, 0)
        self.assertIs(xenial.base, None)
        self.assertEqual(xenial.mirror, 'http://192.168.122.1:3142/ubuntu')
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

        self.assertEqual(c.archive, 'ubuntu')
        self.assertEqual(c.apt_cacher_ng, 'http://192.168.122.1:3142')
        self.assertEqual(c.mirror, 'http://192.168.122.1:3142/ubuntu')
        self.assertEqual(c.bootstrap_mirror, 'http://192.168.122.1:3142/ubuntu')
        self.assertEqual(c.qemu_image_size, '42G')
        self.assertEqual(c.force_parallel, 0)
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
        lts = ubuntu.get_suite(ubuntu_info.lts())
        self.assertIs(c.worker_suite, lts)
        self.assertIs(c.sbuild_worker_suite, lts)
        self.assertIs(c.vmdebootstrap_worker_suite, lts)

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

        ubuntu = c._get_vendor('ubuntu')
        sec = ubuntu.get_suite('xenial-security', True)
        xenial = ubuntu.get_suite('xenial', True)
        self.assertEqual(list(sec.hierarchy), [sec, xenial])
        self.assertIs(sec.base, xenial)
        self.assertEqual(sec.components, {'main', 'universe'})
        self.assertEqual(sec.extra_components, {'multiverse',
            'restricted'})
        self.assertEqual(sec.all_components, {'main', 'universe',
            'multiverse', 'restricted'})
        self.assertEqual(sec.mirror, 'http://192.168.122.1:3142/ubuntu')
        self.assertEqual(sec.apt_key,
                '/usr/share/keyrings/ubuntu-archive-keyring.gpg')
        self.assertEqual(sec.apt_suite, 'xenial-security')
        self.assertEqual(sec.force_parallel, 0)

        self.assertEqual(c.archive, 'ubuntu')
        self.assertEqual(c.apt_cacher_ng, 'http://192.168.122.1:3142')
        self.assertEqual(c.mirror, 'http://192.168.122.1:3142/ubuntu')
        self.assertEqual(c.bootstrap_mirror, 'http://192.168.122.1:3142/ubuntu')
        self.assertEqual(c.qemu_image_size, '42G')
        self.assertEqual(c.force_parallel, 0)
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
        lts = ubuntu.get_suite(ubuntu_info.lts())
        self.assertIs(c.worker_suite, lts)
        self.assertIs(c.sbuild_worker_suite, lts)
        self.assertIs(c.vmdebootstrap_worker_suite, lts)

    def test_unknown_vendor(self):
        c = self.__config
        c.vendor = 'steamos'
        c.suite = 'brewmaster'

        steamos = c._get_vendor('steamos')
        debian = c._get_vendor('debian')
        brewmaster = steamos.get_suite('brewmaster')

        self.assertEqual(str(steamos), 'steamos')
        self.assertEqual(steamos.components, {'main'})
        self.assertEqual(list(brewmaster.hierarchy), [brewmaster])
        self.assertEqual(steamos.mirror, 'http://192.168.122.1:3142/steamos')

        self.assertEqual(c.components, {'main'})
        self.assertEqual(c.vendor, steamos)
        self.assertIs(c.worker_vendor, debian)
        self.assertIs(c.sbuild_worker_vendor, debian)
        self.assertIs(c.vmdebootstrap_worker_vendor, debian)
        self.assertEqual(c.archive, 'steamos')
        self.assertEqual(c.mirror, 'http://192.168.122.1:3142/steamos')

        self.assertIsNone(steamos.get_suite('xyzzy', create=False))
        self.assertIsNotNone(steamos.get_suite('xyzzy'))
        self.assertIs(steamos.get_suite('xyzzy'), steamos.get_suite('xyzzy'))

        try:
            import distro_info
        except ImportError:
            return

        debian_info = distro_info.DebianDistroInfo()
        self.assertIs(c.worker_suite,
                debian.get_suite(debian_info.testing()))

    def tearDown(self):
        pass

if __name__ == '__main__':
    import tap
    runner = tap.TAPTestRunner()
    runner.set_stream(True)
    unittest.main(verbosity=2, testRunner=runner)
