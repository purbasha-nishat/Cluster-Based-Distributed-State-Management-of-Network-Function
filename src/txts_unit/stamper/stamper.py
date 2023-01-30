from twisted.internet.protocol import DatagramProtocol
from twisted.internet import reactor
from dataclasses import dataclass

import os
from dotenv import load_dotenv

load_dotenv()

HZ_CLIENT_CNT = int(os.getenv('HZ_CLIENT_CNT'))
HZ_CLIENT_CLUSTER_CNT = int(os.getenv('HZ_CLIENT_CLUSTER_CNT'))
HZ_CLIENT_IP_PATTERN_one = os.getenv('HZ_CLIENT_IP_PATTERN_one')
# HZ_CLIENT_IP_PATTERN_two = os.getenv('HZ_CLIENT_IP_PATTERN_two')
# HZ_CLIENT_IP_PATTERN_three = os.getenv('HZ_CLIENT_IP_PATTERN_three')

STAMPER_LISTEN_PORT = int(os.getenv('STAMPER_LISTEN_PORT'))
HZ_CLIENT_LISTEN_PORT = int(os.getenv('HZ_CLIENT_LISTEN_PORT'))

TOTAL_PACKETS_RECEIVED_PER_NF = 50


@dataclass
class Flow:
    src_ip: str
    src_port: str


class Stamper(DatagramProtocol):

    def __init__(self):
        self.next_client = 0

        # should use redis
        self.flow_to_client = {} 
        self.flow_pkt_cnt = {}

        # new dictionary to store ip_addr_to_packet_count
        self.hz_client_to_packet_count = {}



        self.hz_client_ips = []

        for i in range(HZ_CLIENT_CNT):
            # adding with `i+2` because the ip of the ovs-br1 interface will be 173.16.1.1
            client_ip = HZ_CLIENT_IP_PATTERN_one.replace('$', str(i + 2))
            self.hz_client_ips.append(client_ip)
        # for i in range(HZ_CLIENT_CNT):
        #     client_ip = HZ_CLIENT_IP_PATTERN_two.replace('$', str(i + 2))
        #     self.hz_client_ips.append(client_ip)
        # for i in range(HZ_CLIENT_CNT):
        #     client_ip = HZ_CLIENT_IP_PATTERN_three.replace('$', str(i + 2))
        #     self.hz_client_ips.append(client_ip)
        
        print('Configured hz_client IP list:')
        print(self.hz_client_ips)

    def select_hz_client(self, flow):

        # migration = False

        if flow not in self.flow_to_client:
            self.flow_to_client[flow] = self.hz_client_ips[self.next_client]

            print(f'next_client id is --------------------- {self.next_client}')
            print(f' val is --------------------------------------------{HZ_CLIENT_CNT*HZ_CLIENT_CLUSTER_CNT}')
            self.next_client = (self.next_client + 1) % (HZ_CLIENT_CNT*HZ_CLIENT_CLUSTER_CNT)

        ##############  if the packet count for an hz_client exceeds the desired number    ################
        elif self.hz_client_to_packet_count[self.flow_to_client[flow]] > TOTAL_PACKETS_RECEIVED_PER_NF:
            
            # self.hz_client_to_packet_count[self.flow_to_client[flow]] = 0

            src_ip, src_port = flow
            dst_ip, dst_port = self.flow_to_client[flow], HZ_CLIENT_LISTEN_PORT


            # choose another hz_client
            self.flow_to_client[flow] = self.hz_client_ips[self.next_client]
            self.next_client = (self.next_client + 1) % (HZ_CLIENT_CNT*HZ_CLIENT_CLUSTER_CNT)

            new_dst_ip, new_dst_port = self.flow_to_client[flow], HZ_CLIENT_LISTEN_PORT

            pkt = f'migrate#{src_ip}#{src_port}#{dst_ip}#{dst_port}#{new_dst_ip}#{new_dst_port}'

            print(f'\n\n-------MIGRATION MESSAGE : {pkt}-------------\n\n')
            self.transport.write(bytes(pkt, 'utf-8'), (dst_ip, dst_port))
            
            # for i in range(HZ_CLIENT_CNT):
            #     ip_breakdown = dst_ip.split('.')
            #     sending_ip = ip_breakdown[0] + '.' + ip_breakdown[1] + '.' + ip_breakdown[2] + '.' + str(i+2)
            #     if sending_ip != dst_ip:
            #         # print(f'asholei going from dest_ip: {dst_ip} and sending_ip in cluster: {sending_ip} -----------------')
            #         self.transport.write(bytes(pkt, 'utf-8'), (sending_ip, HZ_CLIENT_LISTEN_PORT))

            # # choose another hz_client
            # self.next_client = (self.next_client + 1) % (HZ_CLIENT_CNT*HZ_CLIENT_CLUSTER_CNT)

            # # redirect the flow to the new hz_client
            # self.flow_to_client[flow] = self.hz_client_ips[self.next_client]

            # migration = True
                
            self.hz_client_to_packet_count[self.flow_to_client[flow]] = 0

        return self.flow_to_client[flow]

    def stamp_packet(self, data, flow, hz_client_addr):
        if flow not in self.flow_pkt_cnt:
            self.flow_pkt_cnt[flow] = 0

        src_ip, src_port = flow
        dst_ip, dst_port = hz_client_addr

        print(data)

        self.flow_pkt_cnt[flow] += 1
        stamp = f'#{self.flow_pkt_cnt[flow]}#{src_ip}#{src_port}#{dst_ip}#{dst_port}'
        print(f'stamp val: {self.flow_pkt_cnt[flow]}')
        data += bytes(stamp, 'ascii')
        print(data)
        return data


    
    def datagramReceived(self, data, src_addr):
        src_ip, src_port = src_addr

        print(f'received {data} from ({src_ip}, {src_port})')
        

        dst_hz_client = self.select_hz_client(src_addr)

        print(f'forwarding to ip {dst_hz_client} & port {HZ_CLIENT_LISTEN_PORT}')

        dst_addr = dst_hz_client, HZ_CLIENT_LISTEN_PORT

        data = self.stamp_packet(data, src_addr, dst_addr)

        self.transport.write(data, (dst_hz_client, HZ_CLIENT_LISTEN_PORT))

        ##############  incrementing the packet count for the ip_addr    ################
        if dst_hz_client not in self.hz_client_to_packet_count:
            self.hz_client_to_packet_count[dst_hz_client] = 1
        else:
            self.hz_client_to_packet_count[dst_hz_client] += 1


reactor.listenUDP(STAMPER_LISTEN_PORT, Stamper())
print(f'Listening on port {STAMPER_LISTEN_PORT}...')

reactor.run()
