#!/usr/bin/env python3
# encoding: utf-8

import time
import json
import random
import re

import docker
import python_on_whales

from seedemu.compiler import Docker
from seedemu.core import Emulator, Binding, Filter
from seedemu.layers import ScionBase, ScionRouting, ScionIsd, Scion
from seedemu.layers.Scion import LinkType as ScLinkType
from seedemu.services import ScionKuboService

# Initialize the emulator and layers
emu       = Emulator()
base      = ScionBase()
routing   = ScionRouting()
scion_isd = ScionIsd()
scion     = Scion()
scionkubo = ScionKuboService()

# SCION ISDs
base.createIsolationDomain(1)

# Internet Exchange
base.createInternetExchange(100)

# AS-150
as150 = base.createAutonomousSystem(150)
scion_isd.addIsdAs(1, 150, is_core=True)
as150.createNetwork('net0')
as150.createControlService('cs1').joinNetwork('net0')
as150.createRouter('br0').joinNetwork('net0').joinNetwork('ix100')

# kubo-150
for i in range(16):
    as150 \
        .createHost(f'kubo-150-{i}') \
        .joinNetwork('net0', address=f'10.150.0.{30+i}')
    kubo150 = scionkubo.install(f'kubo-150-{i}')
    kubo150.setAddress(f'/scion/1-150,[10.150.0.{30+i}]/udp/12345/quic')
    emu.addBinding(Binding(f'kubo-150-{i}',
        filter=Filter(asn=150, nodeName=f'kubo-150-{i}')))

# AS-151
as151 = base.createAutonomousSystem(151)
scion_isd.addIsdAs(1, 151, is_core=True)
as151.createNetwork('net0')
as151.createControlService('cs1').joinNetwork('net0')
as151.createRouter('br0').joinNetwork('net0').joinNetwork('ix100')

# kubo-151
for i in range(16):
    as151 \
        .createHost(f'kubo-151-{i}') \
        .joinNetwork('net0', address=f'10.151.0.{30+i}')
    kubo151 = scionkubo.install(f'kubo-151-{i}')
    kubo151.setAddress(f'/scion/1-151,[10.151.0.{30+i}]/udp/12345/quic')
    emu.addBinding(Binding(f'kubo-151-{i}',
        filter=Filter(asn=151, nodeName=f'kubo-151-{i}')))

# AS-152
as152 = base.createAutonomousSystem(152)
scion_isd.addIsdAs(1, 152, is_core=True)
as152.createNetwork('net0')
as152.createControlService('cs1').joinNetwork('net0')
as152.createRouter('br0').joinNetwork('net0').joinNetwork('ix100')

# kubo-152
for i in range(16):
    as152 \
        .createHost(f'kubo-152-{i}') \
        .joinNetwork('net0', address=f'10.152.0.{30+i}')
    kubo152 = scionkubo.install(f'kubo-152-{i}')
    kubo152.setAddress(f'/scion/1-152,[10.152.0.{30+i}]/udp/12345/quic')
    emu.addBinding(Binding(f'kubo-152-{i}',
        filter=Filter(asn=152, nodeName=f'kubo-152-{i}')))

# Inter-AS routing
scion.addIxLink(100, (1, 150), (1, 151), ScLinkType.Core)
scion.addIxLink(100, (1, 151), (1, 152), ScLinkType.Core)

# Rendering
emu.addLayer(base)
emu.addLayer(routing)
emu.addLayer(scion_isd)
emu.addLayer(scion)
emu.addLayer(scionkubo)

emu.render()

# Compilation
emu.compile(Docker(), './output')

# Build Docker containers and run the network
whales = python_on_whales.DockerClient(compose_files=['./output/docker-compose.yml'])
whales.compose.build()

id_pattern = r'.*(12D3KooW[^\s]+).*'
asn_pattern = r'.*/scion/1-(\d+),.*'

nruns = 1
results = []

while nruns > 0:
    whales.compose.up(detach=True)

    # Use Docker SDK to interact with the containers
    client: docker.DockerClient = docker.from_env()
    ctrs = {ctr.name: client.containers.get(ctr.id) for ctr in whales.compose.ps()}

    # Wait for containers to come up
    time.sleep(10)

    kubos = dict()
    id2asn = dict()

    try:
        # Collect node info
        for name, ctr in ctrs.items():
            if 'kubo' not in name:
                continue

            _, output = ctr.exec_run('/kubo/cmd/ipfs/ipfs id -f="<addrs>"')
            output = output.decode('utf8').splitlines()[0]
            print(output)
            if '/udp/12345/quic/p2p/' not in output: raise
            kubos[name] = output

            peer_id = re.match(id_pattern, output).group(1)
            print(peer_id)
            if len(peer_id) != 52: raise
            asn = int(re.match(asn_pattern, output).group(1))
            print(asn)
            if asn not in [ 150, 151, 152 ]: raise
            id2asn[peer_id] = asn

        print(json.dumps(kubos, sort_keys=True, indent=4))
        print(json.dumps(id2asn, sort_keys=True, indent=4))

        # Interconnect kubos
        for name, ctr in sorted(ctrs.items(), key=lambda x: random.random()):
            if 'kubo' not in name:
                continue

            my_asn = int(re.match(asn_pattern, kubos[name]).group(1))
            if my_asn not in [ 150, 151, 152 ]: raise

            for peer_name, peer_addr in sorted(kubos.items(), key=lambda x: random.random()):
                if name == peer_name:
                    continue

                peer_id = re.match(id_pattern, peer_addr).group(1)
                print(peer_id)
                if len(peer_id) != 52: raise

                peer_asn = int(re.match(asn_pattern, peer_addr).group(1))
                if peer_asn not in [ 150, 151, 152 ]: raise

                dist = abs(my_asn - peer_asn)

                _, output = ctr.exec_run(f'/kubo/cmd/ipfs/ipfs scionhops set {peer_id} {dist}')
                output = output.decode('utf8').splitlines()[0]
                print(output)
                if 'success' not in output: raise

                _, output = ctr.exec_run(f'/kubo/cmd/ipfs/ipfs swarm connect {peer_addr}')
                output = output.decode('utf8').splitlines()[0]
                print(output)
                if 'success' not in output: raise

        dht_distances = dict()

        # Collect DHT peers
        for name, ctr in ctrs.items():
            if 'kubo' not in name:
                continue

            _, output = ctr.exec_run('/kubo/cmd/ipfs/ipfs stats dht')
            output = output.decode('utf8').splitlines()
            dht_peers = [ match.group(1) for line in output \
                for match in re.finditer(id_pattern, line) ]
            print(dht_peers)
            if len(dht_peers) == 0: raise

            my_asn = int(re.match(asn_pattern, kubos[name]).group(1))
            print(my_asn)
            if my_asn not in [ 150, 151, 152 ]: raise

            dht_distances[my_asn] = \
                [ abs(my_asn - id2asn[peer]) for peer in dht_peers ]

        # Shut the network down
        whales.compose.down()

        results.append({
            'kubos': kubos,
            'id2asn': id2asn,
            'distances': dht_distances,
        })
        nruns = nruns - 1
    except Exception as e:
        print('this run seems to have failed', e)
        pass

print(results)
