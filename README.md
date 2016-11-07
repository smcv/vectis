====================================
vectis - build software on an island
====================================

vectis compiles software in a temporary environment, using an
implementation of the autopkgtest virtualisation service interface
(currently only autopkgtest-virt-qemu is supported).

Requirements
============

* In the host system:
  - autopkgtest (for autopkgtest-virt-qemu)
  - devscripts (for mergechanges)
  - python3
  - qemu-system (or qemu-system-* for the appropriate architecture)
  - qemu-utils
  - lots of RAM, to be able to do the entire build in a tmpfs

* Encouraged on the host system, and assumed by the default configuration:
  - apt-cacher-ng on port 3142
  - libvirt-bin's default virtual network (host is 192.168.122.1)
  - python3-distro-info

* In the host system, but only once (to bootstrap an autopkgtest VM):
  - eatmydata
  - sudo (and permission to use it)
  - vmdebootstrap

* In the guest virtual machine:
  - Debian 8 (jessie) or newer, or a similarly recent Debian derivative

* In the apt archive used by the guest virtual machine:
  - python3
  - sbuild

Usage
=====

vectis bootstrap
    Create a Debian virtual machine image in which to do builds.

    This command requires root access (via sudo), but you only have to run
    it once. You can run it in a virtual machine by hand if you want.

vectis new
    Create a Debian-derived virtual machine image in which to do builds.

    After you have run "vectis bootstrap" once, you can use the resulting
    virtual machine for "vectis new" to create all your other build
    environments.

vectis tarball
    Create a base tarball for sbuild/schroot.

vectis sbuild
    Build Debian packages from source.

Design principles
=================

Vectis was the Roman name for the Isle of Wight, an island off the south
coast of England. vectis uses virtualization to compile your software
on an island.

* Build systems are sometimes horrible. Their side-effects on the host system
  should be minimized. vectis runs them inside a virtual machine.

* Packages are not always as high-quality as you might hope. vectis does
  not run package-supplied code on the real system, only in a VM. There
  is one exception to this principle to avoid a bootstrapping problem:
  the bootstrap subcommand runs vmdebootstrap to make a "blank" virtual
  machine, by default running Debian stable.

In keeping with the Isle of Wight's agricultural history, vectis
treats build environments like "cattle, not pets".

* Some build virtual machines were set up by hand, meaning you need to back
  up a potentially multi-gigabyte virtual machine image. vectis
  automates virtual machine setup, with the goal that the only thing you
  ever alter "by hand" (and hence the only thing you need to back up)
  is vectis's (source code and) configuration, which is a reasonable
  size to keep in a VCS.

* Some buildd chroots were set up by hand. vectis automates this too,
  for the same reason.

One of the towns on Isle of Wight is Ventnor, whose crest depicts Hygeia,
Greek goddess of health and cleanliness (and origin of the word "hygiene").
vectis aims to do all builds in a pedantically correct Debian environment,
such that anything that builds successfully in vectis will build correctly
on real Debian infrastructure.

* Every build is done in a clean environment, avoiding influences from
  the host system other than the vectis configuration and command-line
  options.

* vectis uses sbuild to get a minimal build environment, rather than
  simply building in a virtual machine running the target distribution,
  or using an alternative "minimal" build environment like pbuilder.
  This is because sbuild is what runs on the official Debian buildds,
  so any package that doesn't build like that is de facto unreleasable,
  even it works fine in its maintainer's pbuilder or in a virtual machine.

* By default, vectis does the Architecture: all and Architecture: any
  builds separately (even though this typically takes longer than doing
  them together). This is because that's how Debian's infrastructure
  works, so any package that fails to build in that way can't have
  source-only uploads (and is arguably release-critically buggy). Things
  that aren't routinely tested usually don't work, so vectis tests this
  code path.

Future design principles are not required to have a tenuous analogy
involving the Isle of Wight.

<!-- vim:set sw=4 sts=4 et: -->
