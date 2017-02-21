# Copyright © 2017 Simon McVittie
# SPDX-License-Identifier: GPL-2.0+
# (see vectis/__init__.py)

import os
import textwrap
from tempfile import TemporaryDirectory

from vectis.util import (
        AtomicWriter,
        )

def set_up_lxc_net(worker, subnet):
    with TemporaryDirectory(prefix='vectis-lxc-') as tmp:
        with AtomicWriter(os.path.join(tmp, 'lxc-net')) as writer:
            writer.write(textwrap.dedent('''\
            USE_LXC_BRIDGE="true"
            LXC_BRIDGE="lxcbr0"
            LXC_ADDR="{subnet}.1"
            LXC_NETMASK="255.255.255.0"
            LXC_NETWORK="{subnet}.0/24"
            LXC_DHCP_RANGE="{subnet}.2,{subnet}.254"
            LXC_DHCP_MAX="253"
            LXC_DHCP_CONFILE=""
            LXC_DOMAIN=""
            ''').format(subnet=subnet))
        worker.copy_to_guest(os.path.join(tmp, 'lxc-net'),
                '/etc/default/lxc-net')

        with AtomicWriter(os.path.join(tmp, 'default.conf')) as writer:
            writer.write(textwrap.dedent('''\
            lxc.network.type = veth
            lxc.network.link = lxcbr0
            lxc.network.flags = up
            lxc.network.hwaddr = 00:16:3e:xx:xx:xx
            '''))
        worker.copy_to_guest(os.path.join(tmp, 'default.conf'),
                '/etc/lxc/default.conf')

    worker.check_call(['systemctl', 'enable', 'lxc-net'])
    worker.check_call(['systemctl', 'stop', 'lxc-net'])
    worker.check_call(['systemctl', 'start', 'lxc-net'])
