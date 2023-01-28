from twisted.internet.protocol import DatagramProtocol
from twisted.internet import reactor
from dataclasses import dataclass
import socket
import os
from dotenv import load_dotenv

load_dotenv()

HZ_CLIENT_CNT = int(os.getenv('HZ_CLIENT_CNT'))
HZ_CLIENT_IP_PATTERN_one = os.getenv('HZ_CLIENT_IP_PATTERN_one')

HZ_CLIENT_LISTEN_PORT = int(os.getenv('HZ_CLIENT_LISTEN_PORT'))


@dataclass
class Flow:
    src_ip: str
    src_port: str


class Backup(DatagramProtocol):

    def __init__(self):
        self.next_client = 0

        # # should use redis
        # self.flow_to_client = {} 
        # self.flow_pkt_cnt = {}

        # self.hz_client_ips = []

        # for i in range(HZ_CLIENT_CNT):
        #     # adding with `i+2` because the ip of the ovs-br1 interface will be 173.16.1.1
        #     client_ip = HZ_CLIENT_IP_PATTERN_one.replace('$', str(i + 2))
        #     self.hz_client_ips.append(client_ip)
        
        # print('Configured hz_clint IP list:')
        # print(self.hz_client_ips)



    
    def datagramReceived(self, data, src_addr):
        src_ip, src_port = src_addr

        print(f'received {data} from ({src_ip}, {src_port})')


reactor.listenUDP(HZ_CLIENT_LISTEN_PORT, Backup())
print(f'Listening on port {HZ_CLIENT_LISTEN_PORT}...')

reactor.run()


