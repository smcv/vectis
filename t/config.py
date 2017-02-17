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
        self.assertIsNone(c.apt_suite)
        self.assertEqual(c.dpkg_source_tar_ignore, [])
        self.assertIsNone(c.dpkg_source_diff_ignore)
        self.assertEqual(c.dpkg_source_extend_diff_ignore, [])

        if ARCHITECTURE is not None:
            self.assertEqual(c.architecture, ARCHITECTURE)
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

        sid = c.vendor.get_suite('sid')
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

    def test_debian(self):
        c = self.__config
        debian = c._get_vendor('debian')

        self.assertEqual(str(debian), 'debian')
        self.assertEqual(debian.autopkgtest, ['qemu'])
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
        self.assertEqual(debian.sbuild_worker_vendor, None)
        self.assertEqual(debian.vmdebootstrap_worker_vendor, None)
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
        self.assertEqual(debian.qemu_image_size, '42G')
        self.assertEqual(debian.force_parallel, 0)
        self.assertGreaterEqual(debian.parallel, 1)
        self.assertIs(debian.sbuild_together, False)
        self.assertEqual(debian.sbuild_resolver, [])
        self.assertEqual(debian.apt_key,
                '/usr/share/keyrings/debian-archive-keyring.gpg')
        self.assertIsNone(debian.apt_suite)
        self.assertIsNone(debian.dpkg_source_diff_ignore)
        self.assertEqual(debian.dpkg_source_tar_ignore, [])
        self.assertEqual(debian.dpkg_source_extend_diff_ignore, [])
        self.assertEqual(debian.output_builds, '..')
        self.assertEqual(debian.qemu_image, 'autopkgtest.qcow2')
        self.assertEqual(debian.worker_qemu_image, None)
        self.assertEqual(debian.sbuild_worker_qemu_image, None)
        self.assertEqual(debian.write_qemu_image, None)

        # FIXME: should all be AttributeError because a vendor doesn't imply
        # an architecture
        #with self.assertRaises(AttributeError): debian.architecture
        #with self.assertRaises(AttributeError): debian.worker_architecture
        #with self.assertRaises(AttributeError): debian.sbuild_worker
        #with self.assertRaises(AttributeError): debian.worker
        #with self.assertRaises(AttributeError): debian.debootstrap_script
        #with self.assertRaises(AttributeError): debian.suite
        # FIXME: this only makes sense as a global?
        #with self.assertRaises(AttributeError): debian.storage
        #with self.assertRaises(AttributeError): debian.sbuild_buildables

        jessie = debian.get_suite('jessie', True)
        sec = debian.get_suite('jessie-security', True)
        self.assertEqual(list(jessie.hierarchy), [jessie])
        self.assertEqual(list(sec.hierarchy), [sec, jessie])

        self.assertEqual(jessie.autopkgtest, ['qemu'])
        self.assertEqual(jessie.default_suite, 'sid')
        self.assertEqual(jessie.components, {'main'})
        self.assertEqual(jessie.extra_components, {'contrib', 'non-free'})
        self.assertEqual(jessie.all_components, {'main', 'contrib',
            'non-free'})
        self.assertIs(jessie.vendor, debian)
        # FIXME: should be a Vendor?
        self.assertEqual(jessie.worker_vendor, 'debian')
        self.assertEqual(jessie.sbuild_worker_vendor, None)
        self.assertEqual(jessie.vmdebootstrap_worker_vendor, None)
        # FIXME: should be a Suite? or 'sid'?
        self.assertEqual(jessie.worker_suite, None)
        # FIXME: should be a Suite?
        self.assertEqual(jessie.sbuild_worker_suite, 'jessie-apt.buildd.debian.org')
        self.assertEqual(jessie.archive, 'debian')
        self.assertEqual(jessie.apt_cacher_ng, 'http://192.168.122.1:3142')
        self.assertEqual(jessie.mirror, 'http://192.168.122.1:3142/debian')
        self.assertEqual(jessie.bootstrap_mirror, 'http://192.168.122.1:3142/debian')
        self.assertEqual(jessie.qemu_image_size, '42G')
        self.assertEqual(jessie.force_parallel, 1)
        self.assertEqual(sec.force_parallel, 1)
        self.assertGreaterEqual(jessie.parallel, 1)
        self.assertIs(jessie.sbuild_together, False)
        self.assertEqual(jessie.sbuild_resolver, [])
        self.assertEqual(jessie.apt_key,
                '/usr/share/keyrings/debian-archive-keyring.gpg')
        self.assertEqual(jessie.apt_suite, 'jessie')
        self.assertIsNone(jessie.dpkg_source_diff_ignore)
        self.assertEqual(jessie.dpkg_source_tar_ignore, [])
        self.assertEqual(jessie.dpkg_source_extend_diff_ignore, [])
        self.assertEqual(jessie.output_builds, '..')
        self.assertEqual(jessie.debootstrap_script, 'jessie')
        self.assertIs(jessie.suite, jessie)
        self.assertEqual(jessie.qemu_image, 'autopkgtest.qcow2')
        self.assertEqual(jessie.worker_qemu_image, None)
        self.assertEqual(jessie.sbuild_worker_qemu_image, None)
        self.assertEqual(jessie.write_qemu_image, None)

        # FIXME: should all be AttributeError because a suite doesn't imply
        # an architecture either
        #with self.assertRaises(AttributeError): jessie.architecture
        #with self.assertRaises(AttributeError): jessie.worker_architecture
        #with self.assertRaises(AttributeError): jessie.sbuild_worker
        #with self.assertRaises(AttributeError): jessie.worker
        #with self.assertRaises(AttributeError): jessie.debootstrap_script
        #with self.assertRaises(AttributeError): jessie.suite
        # FIXME: this only makes sense as a global?
        #with self.assertRaises(AttributeError): jessie.storage
        #with self.assertRaises(AttributeError): jessie.sbuild_buildables

        try:
            import distro_info
        except ImportError:
            return

        debian_info = distro_info.DebianDistroInfo()

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

    def test_ubuntu(self):
        c = self.__config
        ubuntu = c._get_vendor('ubuntu')

        self.assertEqual(str(ubuntu), 'ubuntu')
        self.assertEqual(ubuntu.components, {'main', 'universe'})
        self.assertEqual(ubuntu.extra_components, {'restricted',
            'multiverse'})
        self.assertEqual(ubuntu.all_components, {'main', 'universe',
            'restricted', 'multiverse'})
        self.assertEqual(ubuntu.vendor, ubuntu)
        self.assertEqual(ubuntu.worker_vendor, 'ubuntu')
        self.assertEqual(ubuntu.sbuild_worker_vendor, None)
        self.assertEqual(ubuntu.vmdebootstrap_worker_vendor, None)
        self.assertEqual(ubuntu.archive, 'ubuntu')
        self.assertEqual(ubuntu.mirror, 'http://192.168.122.1:3142/ubuntu')
        self.assertIsNone(ubuntu.get_suite('unstable', create=False))
        self.assertIsNone(ubuntu.get_suite('stable', create=False))

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

        self.assertEqual(str(ubuntu), 'ubuntu')
        self.assertEqual(ubuntu.autopkgtest, ['qemu'])
        self.assertEqual(ubuntu.default_suite, ubuntu_devel)
        self.assertEqual(ubuntu.components, {'main', 'universe'})
        self.assertEqual(ubuntu.extra_components, {'restricted',
            'multiverse'})
        self.assertEqual(ubuntu.all_components, {'main', 'universe',
            'restricted', 'multiverse'})
        self.assertIs(ubuntu.vendor, ubuntu)
        # FIXME: should be a Vendor?
        self.assertEqual(ubuntu.worker_vendor, 'ubuntu')
        self.assertEqual(ubuntu.sbuild_worker_vendor, None)
        self.assertEqual(ubuntu.vmdebootstrap_worker_vendor, None)
        # FIXME: should be a Suite?
        self.assertEqual(ubuntu.default_worker_suite, ubuntu_info.lts())
        # FIXME: should be a Suite? or ubuntu_info.lts()?
        self.assertEqual(ubuntu.worker_suite, None)
        self.assertEqual(ubuntu.sbuild_worker_suite, None)
        self.assertEqual(ubuntu.vmdebootstrap_worker_suite, None)
        self.assertEqual(ubuntu.archive, 'ubuntu')
        self.assertEqual(ubuntu.apt_cacher_ng, 'http://192.168.122.1:3142')
        self.assertEqual(ubuntu.mirror, 'http://192.168.122.1:3142/ubuntu')
        self.assertEqual(ubuntu.bootstrap_mirror, 'http://192.168.122.1:3142/ubuntu')
        self.assertIsNone(ubuntu.get_suite('sid', create=False))
        self.assertEqual(ubuntu.qemu_image_size, '42G')
        self.assertEqual(ubuntu.force_parallel, 0)
        self.assertGreaterEqual(ubuntu.parallel, 1)
        self.assertIs(ubuntu.sbuild_together, False)
        self.assertEqual(ubuntu.sbuild_resolver, [])
        self.assertEqual(ubuntu.apt_key,
                '/usr/share/keyrings/ubuntu-archive-keyring.gpg')
        self.assertIsNone(ubuntu.apt_suite)
        self.assertIsNone(ubuntu.dpkg_source_diff_ignore)
        self.assertEqual(ubuntu.dpkg_source_tar_ignore, [])
        self.assertEqual(ubuntu.dpkg_source_extend_diff_ignore, [])
        self.assertEqual(ubuntu.output_builds, '..')
        self.assertEqual(ubuntu.qemu_image, 'autopkgtest.qcow2')
        self.assertEqual(ubuntu.worker_qemu_image, None)
        self.assertEqual(ubuntu.sbuild_worker_qemu_image, None)
        self.assertEqual(ubuntu.write_qemu_image, None)

        # FIXME: should all be AttributeError because a vendor doesn't imply
        # an architecture
        #with self.assertRaises(AttributeError): ubuntu.architecture
        #with self.assertRaises(AttributeError): ubuntu.worker_architecture
        #with self.assertRaises(AttributeError): ubuntu.sbuild_worker
        #with self.assertRaises(AttributeError): ubuntu.worker
        #with self.assertRaises(AttributeError): ubuntu.debootstrap_script
        #with self.assertRaises(AttributeError): ubuntu.suite
        # FIXME: this only makes sense as a global?
        #with self.assertRaises(AttributeError): ubuntu.storage
        #with self.assertRaises(AttributeError): ubuntu.sbuild_buildables

        xenial = ubuntu.get_suite('xenial', True)
        sec = ubuntu.get_suite('xenial-security', True)
        self.assertEqual(list(xenial.hierarchy), [xenial])
        self.assertEqual(list(sec.hierarchy), [sec, xenial])

        self.assertEqual(xenial.autopkgtest, ['qemu'])
        # FIXME: this seems wrong
        self.assertEqual(xenial.default_suite, ubuntu_devel)
        self.assertEqual(xenial.components, {'main', 'universe'})
        self.assertEqual(xenial.extra_components, {'multiverse',
            'restricted'})
        self.assertEqual(xenial.all_components, {'main', 'universe',
            'multiverse', 'restricted'})
        self.assertIs(xenial.vendor, ubuntu)
        # FIXME: should be a Vendor?
        self.assertEqual(xenial.worker_vendor, 'ubuntu')
        self.assertEqual(xenial.sbuild_worker_vendor, None)
        self.assertEqual(xenial.vmdebootstrap_worker_vendor, None)
        # FIXME: should be a Suite?
        self.assertEqual(xenial.default_worker_suite,
                ubuntu_info.lts())
        # FIXME: should be a Suite? or ubuntu_info.lts()?
        self.assertEqual(xenial.worker_suite, None)
        self.assertEqual(xenial.sbuild_worker_suite, None)
        self.assertEqual(xenial.vmdebootstrap_worker_suite, None)
        self.assertEqual(xenial.archive, 'ubuntu')
        self.assertEqual(xenial.apt_cacher_ng, 'http://192.168.122.1:3142')
        self.assertEqual(xenial.mirror, 'http://192.168.122.1:3142/ubuntu')
        self.assertEqual(xenial.bootstrap_mirror, 'http://192.168.122.1:3142/ubuntu')
        self.assertEqual(xenial.qemu_image_size, '42G')
        self.assertEqual(xenial.force_parallel, 0)
        self.assertEqual(sec.force_parallel, 0)
        self.assertGreaterEqual(xenial.parallel, 1)
        self.assertIs(xenial.sbuild_together, False)
        self.assertEqual(xenial.sbuild_resolver, [])
        self.assertEqual(xenial.apt_key,
                '/usr/share/keyrings/ubuntu-archive-keyring.gpg')
        self.assertEqual(xenial.apt_suite, 'xenial')
        self.assertIsNone(xenial.dpkg_source_diff_ignore)
        self.assertEqual(xenial.dpkg_source_tar_ignore, [])
        self.assertEqual(xenial.dpkg_source_extend_diff_ignore, [])
        self.assertEqual(xenial.output_builds, '..')
        self.assertEqual(xenial.debootstrap_script, 'xenial')
        self.assertIs(xenial.suite, xenial)
        self.assertEqual(xenial.qemu_image, 'autopkgtest.qcow2')
        self.assertEqual(xenial.worker_qemu_image, None)
        self.assertEqual(xenial.sbuild_worker_qemu_image, None)
        self.assertEqual(xenial.write_qemu_image, None)

        # FIXME: should all be AttributeError because a suite doesn't imply
        # an architecture either
        #with self.assertRaises(AttributeError): xenial.architecture
        #with self.assertRaises(AttributeError): xenial.worker_architecture
        #with self.assertRaises(AttributeError): xenial.sbuild_worker
        #with self.assertRaises(AttributeError): xenial.worker
        #with self.assertRaises(AttributeError): xenial.debootstrap_script
        #with self.assertRaises(AttributeError): xenial.suite
        # FIXME: this only makes sense as a global?
        #with self.assertRaises(AttributeError): xenial.storage
        #with self.assertRaises(AttributeError): xenial.sbuild_buildables

    def test_unknown_vendor(self):
        c = self.__config
        steamos = self.__config._get_vendor('steamos')

        self.assertEqual(str(steamos), 'steamos')
        self.assertEqual(steamos.components, {'main'})
        self.assertEqual(steamos.vendor, steamos)
        self.assertEqual(steamos.worker_vendor, 'debian')
        self.assertEqual(steamos.sbuild_worker_vendor, None)
        self.assertEqual(steamos.vmdebootstrap_worker_vendor, None)
        self.assertEqual(steamos.archive, 'steamos')
        self.assertEqual(steamos.mirror, 'http://192.168.122.1:3142/steamos')

        self.assertIsNone(steamos.get_suite('xyzzy', create=False))
        self.assertIsNotNone(steamos.get_suite('xyzzy'))
        self.assertIs(steamos.get_suite('xyzzy'), steamos.get_suite('xyzzy'))

    def tearDown(self):
        pass

if __name__ == '__main__':
    import tap
    runner = tap.TAPTestRunner()
    runner.set_stream(True)
    unittest.main(verbosity=2, testRunner=runner)
