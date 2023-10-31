#!/usr/bin/env python3

import platform

from seedemu.core import Node, Service, Server

class ScionKuboServer(Server):
    __address: str

    def __init__(self):
        super().__init__()

    def setAddress(self, address: str):
        self.__address = address

    def install(self, node: Node):
        node.addSoftware('curl git build-essential')

        if platform.machine() == 'aarch64':
            node.addBuildCommand('curl -O https://dl.google.com/go/go1.19.12.linux-arm64.tar.gz')
            node.addBuildCommand('rm -rf /usr/local/go && tar -C /usr/local -xzf go1.19.12.linux-arm64.tar.gz')
        else:
            node.addBuildCommand('curl -O https://dl.google.com/go/go1.19.12.linux-amd64.tar.gz')
            node.addBuildCommand('rm -rf /usr/local/go && tar -C /usr/local -xzf go1.19.12.linux-amd64.tar.gz')

        node.addBuildCommand('git clone -b v0.19.2+dhtsort https://git.leon.fyi/ipfs/kubo')
        node.addBuildCommand('export PATH=$PATH:/usr/local/go/bin && cd kubo && make build')

        node.appendStartCommand('/kubo/cmd/ipfs/ipfs init -p test')
        node.appendStartCommand('/kubo/cmd/ipfs/ipfs config --json Addresses.Swarm \'["{}"]\''.format(self.__address))
        node.appendStartCommand('/kubo/cmd/ipfs/ipfs config --json Swarm.Transports.Network \'{"QUIC": false, "SCIONQUIC": true}\'')

        node.appendStartCommand('while true; do /kubo/cmd/ipfs/ipfs daemon; done')

    def print(self, indent: int) -> str:
        out = ' ' * indent
        out += 'ScionKuboServer'
        return out

class ScionKuboService(Service):
    def __init__(self):
        super().__init__()
        self.addDependency('Base', False, False)

    def _createServer(self) -> Server:
        return ScionKuboServer()

    def getName(self) -> str:
        return 'ScionKuboService'

    def print(self, indent: int) -> str:
        out = ' ' * indent
        out += 'ScionKuboService'
        return out
