#!/usr/bin/env python3
# encoding: utf-8

import time
import json
import random

import docker
import python_on_whales

from seedemu.compiler import Docker
from seedemu.core import Emulator, Binding, Filter
from seedemu.layers import Base, Routing, Ebgp, PeerRelationship
from seedemu.services import KuboService

# Initialize the emulator and layers
emu     = Emulator()
base    = Base()
routing = Routing()
ebgp    = Ebgp()
kubo    = KuboService()

# Internet Exchange
base.createInternetExchange(100)

# AS-150
as150 = base.createAutonomousSystem(150)
as150.createNetwork('net0')
as150.createRouter('router0').joinNetwork('net0').joinNetwork('ix100')

# kubo-150
as150 \
    .createHost('kubo-150') \
    .joinNetwork('net0', address='10.150.0.30') \
    .addSoftware('time')
kubo150 = kubo.install('kubo-150')
kubo150.setAddress('/ip4/10.150.0.30/udp/12345/quic')
emu.addBinding(Binding('kubo-150', filter=Filter(asn=150, nodeName='kubo-150')))

# AS-151
as151 = base.createAutonomousSystem(151)
as151.createNetwork('net0')
as151.createRouter('router0').joinNetwork('net0').joinNetwork('ix100')

# AS-152
as152 = base.createAutonomousSystem(152)
as152.createNetwork('net0')
as152.createRouter('router0').joinNetwork('net0').joinNetwork('ix100')

# kubo-152
as152 \
    .createHost('kubo-152') \
    .joinNetwork('net0', address='10.152.0.30') \
    .addSoftware('time')
kubo152 = kubo.install('kubo-152')
kubo152.setAddress('/ip4/10.152.0.30/udp/12345/quic')
emu.addBinding(Binding('kubo-152', filter=Filter(asn=152, nodeName='kubo-152')))

# Peering
ebgp.addPrivatePeering(100, 150, 151, abRelationship=PeerRelationship.Provider)
ebgp.addPrivatePeering(100, 151, 152, abRelationship=PeerRelationship.Provider)

# Rendering
emu.addLayer(base)
emu.addLayer(routing)
emu.addLayer(ebgp)
emu.addLayer(kubo)

emu.render()

# Compilation
emu.compile(Docker(), './output')

# Build Docker containers and run the network
whales = python_on_whales.DockerClient(compose_files=['./output/docker-compose.yml'])
whales.compose.build()

nruns = 3
results = []

while nruns > 0:
    whales.compose.up(detach=True)

    # Use Docker SDK to interact with the containers
    client: docker.DockerClient = docker.from_env()
    ctrs = {ctr.name: client.containers.get(ctr.id) for ctr in whales.compose.ps()}

    # Wait for containers to come up
    time.sleep(10)

    kubos = dict()

    try:
        # Collect node addresses
        for name, ctr in ctrs.items():
            if 'kubo' not in name:
                continue

            _, output = ctr.exec_run('/kubo/cmd/ipfs/ipfs id -f="<addrs>"')
            output = output.decode('utf8').splitlines()[0]
            print(output)
            if '/udp/12345/quic/p2p/' not in output: raise
            kubos[name] = output

        print(json.dumps(kubos, sort_keys=True, indent=4))

        # Interconnect kubos
        for name, ctr in sorted(ctrs.items(), key=lambda x: random.random()):
            if 'kubo' not in name:
                continue

            for peerName, peerAddr in sorted(kubos.items(), key=lambda x: random.random()):
                if name == peerName:
                    continue

                _, output = ctr.exec_run(f'/kubo/cmd/ipfs/ipfs swarm connect {peerAddr}')
                output = output.decode('utf8').splitlines()[0]
                print(output)
                if 'success' not in output: raise

        # Pick two nodes to transfer content between
        (name_a, addr_a), (name_b, addr_b) = \
                sorted(kubos.items(), key=lambda x: random.random())[:2]

        # Add some random test content
        _, output = ctrs[name_a].exec_run('dd if=/dev/urandom of=testfile bs=1024 count=102400')
        output = output.decode('utf8').splitlines()[-1]
        print(output)
        if '100 MiB) copied' not in output: raise

        _, output = ctrs[name_a].exec_run('/kubo/cmd/ipfs/ipfs add testfile')
        output = output.decode('utf8').splitlines()[-3]
        print(output)
        if 'added' not in output: raise

        # CID of added test content
        cid = output.split()[1]
        print(cid)
        if not cid.startswith('Qm'): raise

        # Try to retrieve content
        _, output = ctrs[name_b].exec_run(f'time -f %e /kubo/cmd/ipfs/ipfs get {cid}')
        results.append(output.decode('utf8').splitlines()[-1])

        # Shut the network down
        whales.compose.down()

        nruns = nruns - 1
    except:
        print('this run seems to have failed')
        pass

print(results)
