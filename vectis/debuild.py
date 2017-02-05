# Copyright © 2016 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import glob
import logging
import os
import subprocess
from collections import (
        OrderedDict,
        )

from debian.changelog import (
        Changelog,
        )
from debian.deb822 import (
        Changes,
        Deb822,
        Dsc,
        )
from debian.debian_support import (
        Version,
        )

from vectis.error import (
        ArgumentError,
        )

logger = logging.getLogger(__name__)

class Buildable:
    def __init__(self, buildable, *, vendor):
        self.buildable = buildable

        self._product_prefix = None
        self.arch_wildcards = set()
        self.archs = []
        self.binary_packages = []
        self.changes_produced = {}
        self.dirname = None
        self.dsc = None
        self.dsc_name = None
        self.indep = False
        self.logs = {}
        self.merged_changes = OrderedDict()
        self.nominal_suite = None
        self.source_from_archive = False
        self.source_package = None
        self.sourceful_changes_name = None
        self.suite = None
        self.together_with = None
        self.vendor = vendor
        self.version = None

        if os.path.exists(self.buildable):
            if os.path.isdir(self.buildable):
                changelog = os.path.join(self.buildable, 'debian', 'changelog')
                changelog = Changelog(open(changelog))
                self.source_package = changelog.get_package()
                self.nominal_suite = changelog.distributions
                self.version = Version(changelog.version)
                control = os.path.join(self.buildable, 'debian', 'control')

                if len(changelog.distributions.split()) != 1:
                    raise ArgumentError('Cannot build for multiple '
                            'distributions at once')

                for paragraph in Deb822.iter_paragraphs(open(control)):
                    self.arch_wildcards |= set(
                            paragraph.get('architecture', '').split())
                    binary = paragraph.get('package')

                if binary is not None:
                    self.binary_packages.append(binary)

            elif self.buildable.endswith('.changes'):
                self.dirname = os.path.dirname(self.buildable)
                self.sourceful_changes_name = self.buildable
                sourceful_changes = Changes(open(self.buildable))
                if 'source' not in sourceful_changes['architecture']:
                    raise ArgumentError('Changes file {!r} must be '
                            'sourceful'.format(self.buildable))

                self.nominal_suite = sourceful_changes['distribution']

                for f in sourceful_changes['files']:
                    if f['name'].endswith('.dsc'):
                        if self.dsc_name is not None:
                            raise ArgumentError('Changes file {!r} contained '
                                    'more than one .dsc '
                                    'file'.format(self.buildable))

                        self.dsc_name = os.path.join(self.dirname, f['name'])

                if self.dsc_name is None:
                    raise ArgumentError('Changes file {!r} did not contain a '
                            '.dsc file'.format(self.buildable))

                self.dsc = Dsc(open(self.dsc_name))

            elif self.buildable.endswith('.dsc'):
                self.dirname = os.path.dirname(self.buildable)
                self.dsc_name = self.buildable
                self.dsc = Dsc(open(self.dsc_name))

            else:
                raise ArgumentError('buildable must be .changes, .dsc or '
                        'directory, not {!r}'.format(self.buildable))
        else:
            self.source_from_archive = True

            if '_' in self.buildable:
                source, version = self.buildable.split('_', 1)
            else:
                source = self.buildable
                version = None

            self.source_package = source
            self.version = Version(version)

        if self.dsc is not None:
            self.source_package = self.dsc['source']
            self.version = Version(self.dsc['version'])
            self.arch_wildcards = set(self.dsc['architecture'].split())
            self.binary_packages = [p.strip()
                    for p in self.dsc['binary'].split(',')]

    @property
    def product_prefix(self):
        if self._product_prefix is None:
            version_no_epoch = Version(self.version)
            version_no_epoch.epoch = None
            self._product_prefix = '{}_{}'.format(self.source_package,
                    version_no_epoch)

        return self._product_prefix

    def copy_source_to(self, machine):
        machine.check_call(['mkdir', '-p', '-m755',
            '{}/in'.format(machine.scratch)])

        if self.dsc_name is not None:
            assert self.dsc is not None

            machine.copy_to_guest(self.dsc_name,
                    '{}/in/{}'.format(machine.scratch,
                        os.path.basename(self.dsc_name)))

            for f in self.dsc['files']:
                machine.copy_to_guest(os.path.join(self.dirname, f['name']),
                        '{}/in/{}'.format(machine.scratch, f['name']))
        elif not self.source_from_archive:
            machine.copy_to_guest(os.path.join(self.buildable, ''),
                    '{}/in/{}_source/'.format(machine.scratch,
                        self.product_prefix))
            machine.check_call(['chown', '-R', 'sbuild:sbuild',
                    '{}/in/'.format(machine.scratch)])
            if self.version.debian_revision is not None:
                machine.check_call(['install', '-d', '-m755',
                    '-osbuild', '-gsbuild',
                    '{}/out'.format(machine.scratch)])

                orig_pattern = glob.escape(os.path.join(self.buildable, '..',
                        '{}_{}.orig.tar.'.format(self.source_package,
                            self.version.upstream_version))) + '*'
                logger.info('Looking for original tarballs: {}'.format(
                        orig_pattern))

                for orig in glob.glob(orig_pattern):
                    logger.info('Copying original tarball: {}'.format(orig))
                    machine.copy_to_guest(orig,
                            '{}/in/{}'.format(machine.scratch,
                                os.path.basename(orig)))
                    machine.check_call(['ln', '-s',
                            '{}/in/{}'.format(machine.scratch,
                                os.path.basename(orig)),
                            '{}/out/{}'.format(machine.scratch,
                                os.path.basename(orig))])

    def select_archs(self, machine_arch, archs, indep, together):
        builds_i386 = False
        builds_natively = False

        for wildcard in self.arch_wildcards:
            if subprocess.call(['dpkg-architecture',
                    '-a' + machine_arch, '--is', wildcard]) == 0:
                logger.info('Package builds natively on %s', machine_arch)
                builds_natively = True

            if subprocess.call(['dpkg-architecture',
                    '-ai386', '--is', wildcard]) == 0:
                logger.info('Package builds on i386')
                builds_i386 = True

        if archs or indep:
            # the user is always right
            logger.info('Using architectures from command-line')
            self.archs = archs[:]
        else:
            logger.info('Choosing architectures to build')
            indep = ('all' in self.arch_wildcards)
            self.archs = []

            if builds_natively:
                self.archs.append(machine_arch)

            for line in subprocess.check_output([
                    'sh', '-c', '"$@" || :',
                    'sh', # argv[0]
                    'dpkg-query', '-W', r'--showformat=${binary:Package}\n',
                    ] + [p.strip() for p in self.binary_packages],
                    universal_newlines=True).splitlines():
                if ':' in line:
                    arch = line.split(':')[-1]
                    if arch not in self.archs:
                        logger.info('Building on %s because %s is installed',
                                arch, line)
                        self.archs.append(arch)

            if (machine_arch == 'amd64' and builds_i386 and
                    not builds_natively and 'i386' not in self.archs):
                self.archs.append('i386')

        if 'all' not in self.arch_wildcards:
            indep = False

        if indep:
            if together and self.archs:
                if machine_arch in self.archs:
                    self.together_with = machine_arch
                else:
                    self.together_with = self.archs[0]
            else:
                self.archs.insert(0, 'all')

        logger.info('Selected architectures: %r', self.archs)

        if indep and self.together_with is not None:
            logger.info('Architecture-independent packages will be built '
                        'alongside %s', self.together_with)

    def select_suite(self, suite):
        self.suite = self.nominal_suite

        if suite is not None:
            self.suite = suite

            if self.nominal_suite is None:
                self.nominal_suite = suite

        if self.suite is None:
            raise ArgumentError('Must specify --suite when building from '
                    '{!r}'.format(self.buildable))

    def __str__(self):
        return self.buildable

