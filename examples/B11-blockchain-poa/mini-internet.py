#!/usr/bin/env python3
# encoding: utf-8


import sys, os
from seedemu import *

def makeStubAs(emu: Emulator, base: Base, asn: int, exchange: int, hosts_total: int):

    # Create AS and internal network
    network = "net0"
    stub_as = base.createAutonomousSystem(asn)
    stub_as.createNetwork(network)

    # Create a BGP router
    # Attach the router to both the internal and external networks
    router = stub_as.createRouter('router0')
    router.joinNetwork(network)
    router.joinNetwork('ix{}'.format(exchange))

    for counter in range(hosts_total):
       name = 'host_{}'.format(counter)
       host = stub_as.createHost(name)
       host.joinNetwork(network)

#n = len(sys.argv)
#if n < 2:
#    print("Please provide the number of hosts per networks")
#    exit(0)
#hosts_total = int(sys.argv[1])

hosts_total = int(10)

###############################################################################
emu     = Emulator()
base    = Base()
routing = Routing()
ebgp    = Ebgp()
ibgp    = Ibgp()
ospf    = Ospf()


###############################################################################

ix100 = base.createInternetExchange(100)
ix101 = base.createInternetExchange(101)
ix102 = base.createInternetExchange(102)
ix103 = base.createInternetExchange(103)
ix104 = base.createInternetExchange(104)

# Customize names (for visualization purpose)
ix100.getPeeringLan().setDisplayName('NYC-100')
ix101.getPeeringLan().setDisplayName('San Jose-101')
ix102.getPeeringLan().setDisplayName('Chicago-102')
ix103.getPeeringLan().setDisplayName('Miami-103')
ix104.getPeeringLan().setDisplayName('Boston-104')


###############################################################################
# Create Transit Autonomous Systems 

## Tier 1 ASes
Makers.makeTransitAs(base, 2, [100, 101, 102], 
       [(100, 101), (101, 102)] 
)

Makers.makeTransitAs(base, 3, [100, 103, 104], 
       [(100, 103), (103, 104)]
)

Makers.makeTransitAs(base, 4, [100, 102, 104], 
       [(100, 104), (102, 104)]
)

## Tier 2 ASes
Makers.makeTransitAs(base, 12, [101, 104], [(101, 104)])


###############################################################################
# Create single-homed stub ASes. "None" means create a host only 

makeStubAs(emu, base, 150, 100, hosts_total)
makeStubAs(emu, base, 151, 100, hosts_total)

makeStubAs(emu, base, 152, 101, hosts_total)
makeStubAs(emu, base, 153, 101, hosts_total)

makeStubAs(emu, base, 154, 102, hosts_total)

makeStubAs(emu, base, 160, 103, hosts_total)
makeStubAs(emu, base, 161, 103, hosts_total)
makeStubAs(emu, base, 162, 103, hosts_total)

makeStubAs(emu, base, 163, 104, hosts_total)
makeStubAs(emu, base, 164, 104, hosts_total)


###############################################################################
# Peering via RS (route server). The default peering mode for RS is PeerRelationship.Peer, 
# which means each AS will only export its customers and their own prefixes. 
# We will use this peering relationship to peer all the ASes in an IX.
# None of them will provide transit service for others. 

ebgp.addRsPeers(100, [2, 3, 4])
ebgp.addRsPeers(102, [2, 4])
ebgp.addRsPeers(104, [3, 4])

# To buy transit services from another autonomous system, 
# we will use private peering  

ebgp.addPrivatePeerings(100, [2],  [150, 151], PeerRelationship.Provider)
ebgp.addPrivatePeerings(100, [3],  [150], PeerRelationship.Provider)

ebgp.addPrivatePeerings(101, [2],  [12], PeerRelationship.Provider)
ebgp.addPrivatePeerings(101, [12], [152, 153], PeerRelationship.Provider)

ebgp.addPrivatePeerings(102, [2, 4],  [154], PeerRelationship.Provider)

ebgp.addPrivatePeerings(103, [3],  [160, 161, 162], PeerRelationship.Provider)

ebgp.addPrivatePeerings(104, [3, 4], [12], PeerRelationship.Provider)
ebgp.addPrivatePeerings(104, [4],  [163], PeerRelationship.Provider)
ebgp.addPrivatePeerings(104, [12], [164], PeerRelationship.Provider)



###############################################################################
# Create the Ethereum layer
# saveState=True: will set the blockchain folder using `volumes`, 
# so the blockchain data will be preserved when containers are deleted.
eth = EthereumService()
docker = Docker()

for i in range (1, hosts_total*10+1):
    e = eth.install("eth{}".format(i)).setConsensusMechanism(ConsensusMechanism.POA)
    
    # Customizing the display names (for visualization purpose)
    if i <= hosts_total*5:
        asn = 150 
        asn = asn + (i-1)//hosts_total
        id = (i-1)%hosts_total
    else:
        asn = 160
        asn = asn + (i-hosts_total*5-1)//hosts_total
        id = (i-1)%hosts_total

    if id == 0:
        e.setBootNode(True)
    if id % 3 == 0:
        e.startMiner()
        e.unlockAccounts()

    emu.getVirtualNode('eth{}'.format(i)).setDisplayName('Ethereum-POA-{}'.format(i))
    
    print("############################"+str(asn)+"######"+str(id))
    emu.addBinding(Binding('eth{}'.format(i), filter=Filter(asn=asn, nodeName="host_{}".format(id))))
    

# Add layers to the emulator
emu.addLayer(base)
emu.addLayer(routing)
emu.addLayer(ebgp)
emu.addLayer(ibgp)
emu.addLayer(ospf)
emu.addLayer(eth)

emu.render()

#docker.addImage(DockerImage('eth-base', [], local = True)

emu.compile(docker, './output', override = True)
