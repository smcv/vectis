#!/usr/bin/python3

# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import os
import subprocess
import unittest

from vectis.config import (Config)

class DefaultsTestCase(unittest.TestCase):
    def setUp(self):
        self.__config = Config(config_layers=({},), current_directory='/')

    def test_defaults(self):
        self.assertGreaterEqual(self.__config.parallel, 1)

        debian = self.__config._get_platform('debian')
        ubuntu = self.__config._get_platform('ubuntu')

        self.assertEqual(str(self.__config.platform), 'debian')
        self.assertEqual(str(self.__config.build_platform), 'debian')
        self.assertIs(self.__config.platform, debian)
        self.assertIs(self.__config.build_platform, debian)
        self.assertEqual(self.__config.mirror,
                'http://192.168.122.1:3142/debian')
        self.assertEqual(self.__config.bootstrap_mirror,
                'http://192.168.122.1:3142/debian')
        self.assertEqual(self.__config.archive, 'debian')
        self.assertEqual(self.__config.sbuild_force_parallel, 0)
        self.assertIs(self.__config.sbuild_together, False)
        self.assertEqual(self.__config.output_builds, '..')
        self.assertIsNone(self.__config.sbuild_buildables)

        # FIXME: these contain the suite, which is undefined, so their values
        # are not useful - for now just assert they don't crash
        self.assertIsNotNone(self.__config.debootstrap_script)
        self.assertIsNotNone(self.__config.qemu_image)
        self.__config.suite

        self.assertEqual(self.__config.unstable_suite, 'sid')
        self.assertEqual(self.__config.components, {'main'})
        self.assertEqual(self.__config.extra_components,
                {'contrib', 'non-free'})
        self.assertEqual(self.__config.all_components, {'main',
            'contrib', 'non-free'})

        self.assertEqual(self.__config.XDG_CACHE_HOME,
                os.environ.get('XDG_CACHE_HOME',
                    os.path.expanduser('~/.cache')))
        self.assertEqual(self.__config.XDG_CONFIG_HOME,
                os.environ.get('XDG_CONFIG_HOME',
                    os.path.expanduser('~/.config')))
        self.assertEqual(self.__config.XDG_DATA_HOME,
                os.environ.get('XDG_DATA_HOME',
                    os.path.expanduser('~/.local/share')))

        self.assertEqual(self.__config.XDG_CONFIG_DIRS,
                os.environ.get('XDG_CONFIG_DIRS', '/etc/xdg'))
        self.assertEqual(self.__config.XDG_DATA_DIRS,
                os.environ.get('XDG_DATA_DIRS', '/usr/local/share:/usr/share'))

        self.assertEqual(self.__config.storage,
            '{}/vectis'.format(self.__config.XDG_CACHE_HOME))
        self.assertEqual(self.__config.builder,
            'autopkgtest-virt-qemu {}/{}'.format(self.__config.storage,
                self.__config.builder_qemu_image))

    def test_known_platforms(self):
        debian = self.__config._get_platform('debian')
        ubuntu = self.__config._get_platform('ubuntu')

        self.assertEqual(debian.unstable_suite, 'sid')
        self.assertEqual(debian.aliases.get('unstable'), 'sid')
        self.assertEqual(debian.components, {'main'})
        self.assertEqual(debian.extra_components, {'contrib', 'non-free'})
        self.assertEqual(debian.all_components, {'main', 'contrib',
            'non-free'})
        self.assertEqual(debian.platform, 'debian')
        self.assertEqual(debian.build_platform, 'debian')
        #self.assertEqual(debian.archive, 'debian')
        #self.assertEqual(debian.mirror, 'http://192.168.122.1:3142/debian')

        self.assertEqual(ubuntu.aliases, {})
        self.assertEqual(ubuntu.components, {'main'})
        self.assertEqual(ubuntu.extra_components, {'universe', 'restricted',
            'multiverse'})
        self.assertEqual(ubuntu.all_components, {'main', 'universe',
            'restricted', 'multiverse'})
        # FIXME: fails: is "debian"
        #self.assertEqual(ubuntu.platform, 'ubuntu')
        self.assertEqual(ubuntu.build_platform, 'ubuntu')
        #self.assertEqual(ubuntu.archive, 'ubuntu')
        #self.assertEqual(ubuntu.mirror, 'http://192.168.122.1:3142/ubuntu')

    def test_unknown_platform(self):
        steamos = self.__config._get_platform('steamos')

        self.assertEqual(steamos.aliases, {})
        self.assertEqual(steamos.components, {'main'})
        # FIXME: fails: is "debian"
        #self.assertEqual(steamos.platform, 'steamos')
        self.assertEqual(steamos.build_platform, 'debian')
        # FIXME: fails: is "${platform}"
        #self.assertEqual(steamos.archive, 'steamos')
        # FIXME: fails: ends with "${archive}"
        #self.assertEqual(steamos.mirror, 'http://192.168.122.1:3142/steamos')

        with self.assertRaises(ValueError):
            steamos.stable_suite

        with self.assertRaises(ValueError):
            steamos.unstable_suite

    def test_architecture(self):
        try:
            arch = subprocess.check_output(['dpkg', '--print-architecture'])
        except subprocess.CalledProcessError:
            pass
        else:
            self.assertEqual(self.__config.architecture,
                    arch.decode('utf-8').strip())
            self.assertEqual(self.__config.architecture,
                self.__config.build_architecture)

    def test_distro_info(self):
        debian = self.__config._get_platform('debian')
        ubuntu = self.__config._get_platform('ubuntu')

        try:
            import distro_info
        except ImportError:
            self.assertIsNone(debian.stable_suite)
            self.assertIsNone(ubuntu.stable_suite)
            self.assertIsNone(ubuntu.unstable_suite)

            with self.assertRaises(ValueError):
                print(self.__config.stable_suite)
        else:
            debian_info = distro_info.DebianDistroInfo()
            ubuntu_info = distro_info.UbuntuDistroInfo()

            self.assertEqual(self.__config.stable_suite, debian_info.stable())
            self.assertEqual(debian.stable_suite, debian_info.stable())
            self.assertEqual(ubuntu.stable_suite, ubuntu_info.lts())
            self.assertEqual(ubuntu.unstable_suite, ubuntu_info.devel())
            self.assertEqual(debian.aliases.get('unstable'), 'sid')
            self.assertEqual(debian.aliases.get('stable'),
                    debian_info.stable())
            self.assertEqual(debian.aliases.get('testing'),
                    debian_info.testing())
            self.assertEqual(debian.aliases.get('oldstable'),
                    debian_info.old())
            self.assertEqual(debian.aliases.get('rc-buggy'), 'experimental')

    def tearDown(self):
        pass

if __name__ == '__main__':
    import tap
    runner = tap.TAPTestRunner()
    runner.set_stream(True)
    unittest.main(verbosity=2, testRunner=runner)
