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

class DefaultsTestCase(unittest.TestCase):
    def setUp(self):
        self.__config = Config(config_layers=(dict(
                    defaults=dict(
                        apt_cacher_ng='http://192.168.122.1:3142',
                        )),),
                current_directory='/')

    def test_defaults(self):
        self.__config = Config(config_layers=({},), current_directory='/')

        self.assertGreaterEqual(self.__config.parallel, 1)

        debian = self.__config._get_vendor('debian')
        ubuntu = self.__config._get_vendor('ubuntu')

        self.assertEqual(str(self.__config.vendor), 'debian')
        self.assertEqual(str(self.__config.worker_vendor), 'debian')
        self.assertIs(self.__config.vendor, debian)
        self.assertIs(self.__config.worker_vendor, debian)
        self.assertEqual(self.__config.archive, 'debian')
        self.assertEqual(self.__config.force_parallel, 0)
        self.assertIs(self.__config.sbuild_together, False)
        self.assertEqual(self.__config.output_builds, '..')
        self.assertIsNone(self.__config.sbuild_buildables)

        # FIXME: these contain the suite, which is undefined, so their values
        # are not useful - for now just assert they don't crash
        self.assertIsNotNone(self.__config.debootstrap_script)
        self.assertIsNotNone(self.__config.qemu_image)
        self.__config.suite

        self.assertEqual(self.__config.default_suite, 'sid')
        self.assertEqual(self.__config.components, {'main'})
        self.assertEqual(self.__config.extra_components,
                {'contrib', 'non-free'})
        self.assertEqual(self.__config.all_components, {'main',
            'contrib', 'non-free'})

        self.assertEqual(self.__config.storage,
            '{}/vectis'.format(os.getenv('XDG_CACHE_HOME',
                os.path.expanduser('~/.cache'))))
        self.assertEqual(self.__config.worker,
            'qemu {}'.format(self.__config.worker_qemu_image))

        with self.assertRaises(ConfigError):
            self.__config.mirror

        with self.assertRaises(ConfigError):
            self.__config.bootstrap_mirror

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
        self.assertEqual(debian.default_suite, 'sid')
        self.assertEqual(str(debian.get_suite('unstable')), 'sid')
        self.assertIs(debian.get_suite('unstable'), debian.get_suite('sid'))
        self.assertEqual(str(debian.get_suite('rc-buggy')), 'experimental')
        self.assertIs(debian.get_suite('rc-buggy'), debian.get_suite('experimental'))
        self.assertEqual(debian.components, {'main'})
        self.assertEqual(debian.extra_components, {'contrib', 'non-free'})
        self.assertEqual(debian.all_components, {'main', 'contrib',
            'non-free'})
        self.assertEqual(debian.vendor, debian)
        self.assertEqual(debian.worker_vendor, 'debian')
        self.assertEqual(debian.sbuild_worker_suite, 'jessie-apt.buildd.debian.org')
        #self.assertEqual(debian.archive, 'debian')
        #self.assertEqual(debian.mirror, 'http://192.168.122.1:3142/debian')
        self.assertIsNone(debian.get_suite('xenial', create=False))
        self.assertEqual(debian.get_suite('experimental').sbuild_resolver[0],
                '--build-dep-resolver=aspcud')

        self.assertEqual(str(ubuntu), 'ubuntu')
        self.assertEqual(ubuntu.components, {'main'})
        self.assertEqual(ubuntu.extra_components, {'universe', 'restricted',
            'multiverse'})
        self.assertEqual(ubuntu.all_components, {'main', 'universe',
            'restricted', 'multiverse'})
        self.assertEqual(ubuntu.vendor, ubuntu)
        self.assertEqual(ubuntu.worker_vendor, 'ubuntu')
        #self.assertEqual(ubuntu.archive, 'ubuntu')
        #self.assertEqual(ubuntu.mirror, 'http://192.168.122.1:3142/ubuntu')
        self.assertIsNone(ubuntu.get_suite('unstable', create=False))
        self.assertIsNone(ubuntu.get_suite('stable', create=False))

    def test_unknown_vendor(self):
        steamos = self.__config._get_vendor('steamos')

        self.assertEqual(str(steamos), 'steamos')
        self.assertEqual(steamos.components, {'main'})
        self.assertEqual(steamos.vendor, steamos)
        self.assertEqual(steamos.worker_vendor, 'debian')
        # FIXME: fails: is "${vendor}"
        #self.assertEqual(steamos.archive, 'steamos')
        # FIXME: fails: ends with "${archive}"
        #self.assertEqual(steamos.mirror, 'http://192.168.122.1:3142/steamos')

        self.assertIsNone(steamos.get_suite('xyzzy', create=False))
        self.assertIsNotNone(steamos.get_suite('xyzzy'))
        self.assertIs(steamos.get_suite('xyzzy'), steamos.get_suite('xyzzy'))

    def test_architecture(self):
        try:
            arch = subprocess.check_output(['dpkg', '--print-architecture'])
        except subprocess.CalledProcessError:
            pass
        else:
            self.assertEqual(self.__config.architecture,
                    arch.decode('utf-8').strip())
            self.assertEqual(self.__config.architecture,
                self.__config.worker_architecture)

    def test_distro_info(self):
        debian = self.__config._get_vendor('debian')
        ubuntu = self.__config._get_vendor('ubuntu')

        try:
            import distro_info
        except ImportError:
            pass
        else:
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
