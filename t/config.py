#!/usr/bin/python3

# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import os
import subprocess
import unittest

from vectis.config import (
        Config,
        ConfigError,
        )

XDG_CACHE_HOME = os.getenv('XDG_CACHE_HOME', os.path.expanduser('~/.cache'))

try:
    ARCHITECTURE = subprocess.check_call(['dpkg', '--print-architecture'],
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

        self.assertGreaterEqual(self.__config.parallel, 1)
        self.assertIs(type(self.__config.parallel), int)

        debian = self.__config._get_vendor('debian')
        ubuntu = self.__config._get_vendor('ubuntu')

        self.assertEqual(str(self.__config.vendor), 'debian')
        self.assertEqual(str(self.__config.worker_vendor), 'debian')
        self.assertIs(self.__config.vendor, debian)
        self.assertIs(self.__config.worker_vendor, debian)
        self.assertEqual(self.__config.archive, 'debian')
        self.assertEqual(self.__config.apt_cacher_ng, None)
        self.assertEqual(self.__config.force_parallel, 0)
        self.assertIs(self.__config.sbuild_together, False)
        self.assertEqual(self.__config.output_builds, '..')
        self.assertEqual(self.__config.size, '42G')
        self.assertIsNone(self.__config.sbuild_buildables)
        self.assertEqual(self.__config.sbuild_resolver, [])
        self.assertEqual(self.__config.debootstrap_script, 'sid')
        self.assertIsNone(self.__config.apt_key)
        self.assertIsNone(self.__config.apt_suite)
        self.assertEqual(self.__config.dpkg_source_tar_ignore, [])
        self.assertIsNone(self.__config.dpkg_source_diff_ignore)
        self.assertEqual(self.__config.dpkg_source_extend_diff_ignore, [])

        if ARCHITECTURE is not None:
            self.assertEqual(self.__config.architecture, ARCHITECTURE)
            self.assertEqual(self.__config.qemu_image,
                    '{}/vectis/vectis-debian-sid-{}.qcow2'.format(
                        XDG_CACHE_HOME, ARCHITECTURE))
            self.assertEqual(self.__config.autopkgtest_qemu_image,
                    '{}/vectis/vectis-debian-sid-{}.qcow2'.format(
                        XDG_CACHE_HOME, ARCHITECTURE))
            self.assertEqual(self.__config.write_qemu_image,
                    '{}/vectis/vectis-debian-sid-{}.qcow2'.format(
                        XDG_CACHE_HOME, ARCHITECTURE))
            self.assertEqual(self.__config.worker_architecture, ARCHITECTURE)
            self.assertEqual(self.__config.worker,
                    'qemu {}'.format(self.__config.worker_qemu_image))
            self.assertEqual(self.__config.worker_qemu_image,
                    '{}/vectis/vectis-debian-sid-{}.qcow2'.format(
                        XDG_CACHE_HOME, ARCHITECTURE))
            self.assertEqual(self.__config.sbuild_worker,
                    'qemu {}'.format(self.__config.sbuild_worker_qemu_image))
            self.assertEqual(self.__config.sbuild_worker_qemu_image,
                    '{}/vectis/vectis-debian-sid-{}.qcow2'.format(
                        XDG_CACHE_HOME, ARCHITECTURE))

        sid = self.__config.vendor.get_suite('sid')
        self.assertIs(self.__config.autopkgtest, True)
        self.assertEqual(self.__config.suite, sid)
        self.assertEqual(self.__config.worker_suite, sid)
        jb = self.__config.vendor.get_suite('jessie-apt.buildd.debian.org')
        # FIXME: should be a Suite?
        self.assertEqual(self.__config.sbuild_worker_suite, str(jb))
        self.assertEqual(self.__config.default_suite, 'sid')
        self.assertEqual(self.__config.components, {'main'})
        self.assertEqual(self.__config.extra_components,
                {'contrib', 'non-free'})
        self.assertEqual(self.__config.all_components, {'main',
            'contrib', 'non-free'})

        self.assertEqual(self.__config.storage,
            '{}/vectis'.format(XDG_CACHE_HOME))

        with self.assertRaises(ConfigError): self.__config.mirror
        with self.assertRaises(ConfigError): self.__config.bootstrap_mirror

    def test_substitutions(self):
        self.__config.architecture = 'm68k'
        self.__config.suite = 'potato'
        self.__config.worker_suite = 'sarge'

        debian = self.__config._get_vendor('debian')
        potato = debian.get_suite('potato')
        sarge = debian.get_suite('sarge')
        self.assertEqual(list(potato.hierarchy), [potato])
        self.assertEqual(list(sarge.hierarchy), [sarge])
        self.assertEqual(self.__config.suite, potato)
        self.assertEqual(self.__config.worker_suite, sarge)

        self.assertEqual(self.__config.debootstrap_script, 'potato')
        self.assertEqual(self.__config.qemu_image,
                '{}/vectis-debian-potato-m68k.qcow2'.format(self.__config.storage))
        self.assertEqual(self.__config.worker_qemu_image,
            '{}/vectis-debian-sarge-m68k.qcow2'.format(self.__config.storage))
        self.assertEqual(self.__config.worker,
            'qemu {}/vectis-debian-sarge-m68k.qcow2'.format(
                self.__config.storage))

        self.assertEqual(self.__config.mirror,
                'http://192.168.122.1:3142/debian')
        self.assertEqual(self.__config.bootstrap_mirror,
                'http://192.168.122.1:3142/debian')

    def test_known_vendors(self):
        debian = self.__config._get_vendor('debian')
        ubuntu = self.__config._get_vendor('ubuntu')

        self.assertEqual(str(debian), 'debian')
        self.assertIs(debian.autopkgtest, True)
        self.assertEqual(debian.default_suite, 'sid')
        self.assertEqual(str(debian.get_suite('unstable')), 'sid')
        self.assertIs(debian.get_suite('unstable'), debian.get_suite('sid'))
        self.assertEqual(str(debian.get_suite('rc-buggy')), 'experimental')
        self.assertIs(debian.get_suite('rc-buggy'), debian.get_suite('experimental'))
        self.assertEqual(debian.components, {'main'})
        self.assertEqual(debian.extra_components, {'contrib', 'non-free'})
        self.assertEqual(debian.all_components, {'main', 'contrib',
            'non-free'})
        self.assertIs(debian.vendor, debian)
        # FIXME: should be a Vendor?
        self.assertEqual(debian.worker_vendor, 'debian')
        # FIXME: should be a Suite? or 'sid'?
        self.assertEqual(debian.worker_suite, None)
        # FIXME: should be a Suite?
        self.assertEqual(debian.sbuild_worker_suite, 'jessie-apt.buildd.debian.org')
        self.assertEqual(debian.archive, 'debian')
        self.assertEqual(debian.apt_cacher_ng, 'http://192.168.122.1:3142')
        self.assertEqual(debian.mirror, 'http://192.168.122.1:3142/debian')
        self.assertEqual(debian.bootstrap_mirror, 'http://192.168.122.1:3142/debian')
        self.assertIsNone(debian.get_suite('xenial', create=False))
        self.assertEqual(debian.get_suite('experimental').sbuild_resolver[0],
                '--build-dep-resolver=aspcud')
        self.assertEqual(debian.size, '42G')
        self.assertEqual(debian.force_parallel, 0)
        self.assertGreaterEqual(debian.parallel, 1)
        self.assertIs(debian.sbuild_together, False)
        self.assertEqual(debian.sbuild_resolver, [])
        self.assertIsNone(debian.apt_key)
        self.assertIsNone(debian.apt_suite)
        self.assertIsNone(debian.dpkg_source_diff_ignore)
        self.assertEqual(debian.dpkg_source_tar_ignore, [])
        self.assertEqual(debian.dpkg_source_extend_diff_ignore, [])
        self.assertEqual(debian.output_builds, '..')

        # FIXME: should all be AttributeError because a vendor doesn't imply
        # an architecture
        #with self.assertRaises(AttributeError): debian.architecture
        #with self.assertRaises(AttributeError): debian.worker_architecture
        #with self.assertRaises(AttributeError): debian.qemu_image
        #with self.assertRaises(AttributeError): debian.sbuild_worker
        with self.assertRaises(AttributeError): debian.sbuild_worker_qemu_image
        #with self.assertRaises(AttributeError): debian.worker
        #with self.assertRaises(AttributeError): debian.worker_qemu_image
        #with self.assertRaises(AttributeError): debian.write_qemu_image
        #with self.assertRaises(AttributeError): debian.debootstrap_script
        #with self.assertRaises(AttributeError): debian.suite
        # FIXME: this only makes sense as a global?
        #with self.assertRaises(AttributeError): debian.storage
        #with self.assertRaises(AttributeError): debian.sbuild_buildables

        jessie = debian.get_suite('jessie', True)
        sec = debian.get_suite('jessie-security', True)
        self.assertEqual(list(jessie.hierarchy), [jessie])
        self.assertEqual(list(sec.hierarchy), [sec, jessie])

        self.assertIs(jessie.autopkgtest, True)
        self.assertEqual(jessie.default_suite, 'sid')
        self.assertEqual(jessie.components, {'main'})
        self.assertEqual(jessie.extra_components, {'contrib', 'non-free'})
        self.assertEqual(jessie.all_components, {'main', 'contrib',
            'non-free'})
        self.assertIs(jessie.vendor, debian)
        # FIXME: should be a Vendor?
        self.assertEqual(jessie.worker_vendor, 'debian')
        # FIXME: should be a Suite? or 'sid'?
        self.assertEqual(jessie.worker_suite, None)
        # FIXME: should be a Suite?
        self.assertEqual(jessie.sbuild_worker_suite, 'jessie-apt.buildd.debian.org')
        self.assertEqual(jessie.archive, 'debian')
        self.assertEqual(jessie.apt_cacher_ng, 'http://192.168.122.1:3142')
        self.assertEqual(jessie.mirror, 'http://192.168.122.1:3142/debian')
        self.assertEqual(jessie.bootstrap_mirror, 'http://192.168.122.1:3142/debian')
        self.assertEqual(jessie.size, '42G')
        self.assertEqual(jessie.force_parallel, 1)
        self.assertEqual(sec.force_parallel, 1)
        self.assertGreaterEqual(jessie.parallel, 1)
        self.assertIs(jessie.sbuild_together, False)
        self.assertEqual(jessie.sbuild_resolver, [])
        self.assertIsNone(jessie.apt_key)
        self.assertEqual(jessie.apt_suite, 'jessie')
        self.assertIsNone(jessie.dpkg_source_diff_ignore)
        self.assertEqual(jessie.dpkg_source_tar_ignore, [])
        self.assertEqual(jessie.dpkg_source_extend_diff_ignore, [])
        self.assertEqual(jessie.output_builds, '..')
        self.assertEqual(jessie.debootstrap_script, 'jessie')
        self.assertIs(jessie.suite, jessie)

        # FIXME: should all be AttributeError because a suite doesn't imply
        # an architecture either
        #with self.assertRaises(AttributeError): jessie.architecture
        #with self.assertRaises(AttributeError): jessie.worker_architecture
        #with self.assertRaises(AttributeError): jessie.qemu_image
        #with self.assertRaises(AttributeError): jessie.sbuild_worker
        with self.assertRaises(AttributeError): jessie.sbuild_worker_qemu_image
        #with self.assertRaises(AttributeError): jessie.worker
        #with self.assertRaises(AttributeError): jessie.worker_qemu_image
        #with self.assertRaises(AttributeError): jessie.write_qemu_image
        #with self.assertRaises(AttributeError): jessie.debootstrap_script
        #with self.assertRaises(AttributeError): jessie.suite
        # FIXME: this only makes sense as a global?
        #with self.assertRaises(AttributeError): jessie.storage
        #with self.assertRaises(AttributeError): jessie.sbuild_buildables

        self.assertEqual(str(ubuntu), 'ubuntu')
        self.assertEqual(ubuntu.components, {'main'})
        self.assertEqual(ubuntu.extra_components, {'universe', 'restricted',
            'multiverse'})
        self.assertEqual(ubuntu.all_components, {'main', 'universe',
            'restricted', 'multiverse'})
        self.assertEqual(ubuntu.vendor, ubuntu)
        self.assertEqual(ubuntu.worker_vendor, 'ubuntu')
        self.assertEqual(ubuntu.archive, 'ubuntu')
        self.assertEqual(ubuntu.mirror, 'http://192.168.122.1:3142/ubuntu')
        self.assertIsNone(ubuntu.get_suite('unstable', create=False))
        self.assertIsNone(ubuntu.get_suite('stable', create=False))

    def test_unknown_vendor(self):
        steamos = self.__config._get_vendor('steamos')

        self.assertEqual(str(steamos), 'steamos')
        self.assertEqual(steamos.components, {'main'})
        self.assertEqual(steamos.vendor, steamos)
        self.assertEqual(steamos.worker_vendor, 'debian')
        self.assertEqual(steamos.archive, 'steamos')
        self.assertEqual(steamos.mirror, 'http://192.168.122.1:3142/steamos')

        self.assertIsNone(steamos.get_suite('xyzzy', create=False))
        self.assertIsNotNone(steamos.get_suite('xyzzy'))
        self.assertIs(steamos.get_suite('xyzzy'), steamos.get_suite('xyzzy'))

    def test_distro_info(self):
        debian = self.__config._get_vendor('debian')
        ubuntu = self.__config._get_vendor('ubuntu')

        try:
            import distro_info
        except ImportError:
            return

        debian_info = distro_info.DebianDistroInfo()
        ubuntu_info = distro_info.UbuntuDistroInfo()

        try:
            ubuntu_devel = ubuntu_info.devel()
        except distro_info.DistroDataOutdated:
            ubuntu_devel = ubuntu_info.stable()

        self.assertEqual(str(ubuntu.get_suite('devel')), ubuntu_devel)
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
        self.assertEqual(stable.sbuild_resolver, [])

        backports = debian.get_suite('stable-backports')
        self.assertEqual(str(backports),
                debian_info.stable() + '-backports')
        self.assertEqual(backports.sbuild_resolver,
                ['--build-dep-resolver=aptitude'])
        self.assertEqual(backports.apt_suite,
                debian_info.stable() + '-backports')
        self.assertEqual(backports.mirror,
                'http://192.168.122.1:3142/debian')
        self.assertEqual(backports.hierarchy[0], backports)
        self.assertEqual(str(backports.hierarchy[1]), str(stable))

        security = debian.get_suite('stable-security')
        self.assertEqual(security.apt_suite,
                '{}/updates'.format(debian_info.stable()))
        self.assertEqual(security.mirror,
                'http://192.168.122.1:3142/security.debian.org')
        self.assertEqual(security.hierarchy[0], security)
        self.assertEqual(str(security.hierarchy[1]), str(stable))

    def tearDown(self):
        pass

if __name__ == '__main__':
    import tap
    runner = tap.TAPTestRunner()
    runner.set_stream(True)
    unittest.main(verbosity=2, testRunner=runner)
