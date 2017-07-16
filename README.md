vectis - build software on an island
====================================

vectis compiles software in a temporary environment, using an
implementation of the autopkgtest virtualisation service interface
(currently only autopkgtest-virt-qemu is supported).

Notes for early adopters
------------------------

vectis is under heavy development. Use it if it is useful to you, but
please be aware that configuration file formats, command-line options,
Python interfaces, etc. are all subject to change at any time, at the
whim of the maintainer. Sorry, but I don't want to commit to any sort
of stability until I'm happy with the relevant interfaces.

Requirements
------------

* At build/install time:
  - GNU autoconf, autoconf-archive, automake, make
  - python3

* In the host system:
  - autopkgtest (for autopkgtest-virt-qemu)
  - devscripts (for mergechanges)
  - python3
  - qemu-system (or qemu-system-whatever for the appropriate architecture)
  - qemu-utils
  - lots of RAM, to be able to do the entire build in a tmpfs

* Recommended to have on the host system:
  - apt-cacher-ng
  - libvirt-daemon-system's default virtual network (host is 192.168.122.1)
  - python3-colorlog
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

Recommended configuration
-------------------------

Install apt-cacher-ng.

Install libvirt-daemon-system and enable its default virtual network (this
will make the host accessible to all guests as 192.168.122.1).

Create `XDG_CONFIG_DIRS/vectis/vectis.yaml` containing:

```
---
defaults:
    mirrors:
        null: "http://192.168.122.1:3142/${archive}"
...
```

If you don't do this, you will have to add `--mirror` (recommended) or
`--direct` (not recommended unless you are in the same place as the canonical
upstream source of packages) to most commands.

Usage
-----

- `vectis bootstrap`

    Create a Debian virtual machine image in which to do builds.

    This command must be run as an ordinary user, and escalates its
    privileges to root via sudo. You only have to run it once, and
    you can run it in a virtual machine by hand if you want.

- `vectis new`

    Create a Debian-derived virtual machine image in which to do builds.

    After you have run `vectis bootstrap` once, you can use the resulting
    virtual machine for `vectis new` to create all your other build
    environments.

- `vectis sbuild-tarball`

    Create a base tarball for sbuild/schroot.

- `vectis sbuild`

    Build Debian packages from source.

- `vectis minbase-tarball`

    Create a minimal base tarball for piuparts.

- `vectis run`

    Run an executable or shell command in the virtual machine.

Specifying mirrors
------------------

The recommended configuration (above) uses apt-cacher-ng, but vectis can also
be used with a local mirror.

To direct (for example) Debian and debian-security accesses to a local mirror,
use command-line options like one of these:

    # By specifying a canonical URI of the package archive
    --mirror=http://deb.debian.org/debian=http://mirror/debian
    --mirror=http://security.debian.org=http://mirror/debian-security

    # By specifying the 'archive' property of the suite after a '/' prefix
    --mirror=/debian=http://mirror/debian
    --mirror=/security.debian.org=http://mirror/debian-security

    # By specifying the vendor and suite
    --mirror=debian=http://mirror/debian
    --mirror=debian/stretch-security=http://mirror/debian-security

These can also be specified in YAML like this:

    defaults:
        mirrors:
            "http://deb.debian.org/debian": "http://mirror/debian"
            "http://security.debian.org": "http://mirror/debian-security"

If you have a sufficiently fast connection to a particular upstream that no
mirror is desired, you can select direct access to it:

    --direct=http://myos.example.com/myos
    # which is just a shortcut for:
    --mirror=http://myos.example.com/myos=http://myos.example.com/myos

or in YAML:

    defaults:
        mirrors:
            "http://myos.example.com/myos": "http://myos.example.com/myos"

Design principles
-----------------

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

Parts of the Isle of Wight have erratic mobile Internet coverage due to
inconveniently-positioned cliffs. vectis is designed for use with a
local mirror or caching proxy.

* vectis does not make any attempt to cache downloaded packages. Something
  like apt-cacher-ng or squid can do this better.

* vectis can be configured to use a specific (hopefully local) mirror for
  particular archives, vendors or suites.

* The vendor/suite configuration shipped with vectis includes canonical URIs
  for various Debian and Ubuntu archives, but to avoid hitting network
  mirrors repeatedly, these canonical URIs are not used unless specifically
  configured.

* The `--direct` command-line option can be used to allow direct use of a
  particular archive, and is suitable for nearby archives, locations with a
  transparent caching proxy, or developers willing to waste bandwidth.

Future design principles are not required to have a tenuous analogy
involving the Isle of Wight.

<!-- vim:set sw=4 sts=4 et: -->
