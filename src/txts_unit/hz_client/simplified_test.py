import hazelcast
import threading
import queue
from queue import PriorityQueue
from twisted.internet import reactor
from twisted.internet.protocol import Factory, Protocol, DatagramProtocol
import sys
import os
from dotenv import load_dotenv

load_dotenv()

HZ_CLIENT_CNT = int(os.getenv('HZ_CLIENT_CNT'))
HZ_CLIENT_IP_PATTERN = os.getenv('HZ_CLIENT_IP_PATTERN')

HZ_CLIENT_LISTEN_PORT = int(os.getenv('HZ_CLIENT_LISTEN_PORT'))

sys.path.append('..')
from exp_package import  Hazelcast, Helpers
from exp_package.Two_phase_commit.primary_2pc import Primary

import socket

per_flow_packet_counter = None
master: Primary = None


class Buffers:
    input_buffer = queue.Queue(maxsize=100000)  # (pkts, pkts_id) tuples
    output_buffer = queue.Queue(maxsize=100000)  # (pkts, pkts_id) tuples


class BufferTimeMaps:
    input_in = {}
    input_out = {}
    output_in = {}
    output_out = {}


class Timestamps:
    start_times, end_times = None, None


class Limit:
    BATCH_SIZE = int(os.getenv('BATCH_SIZE'))
    PKTS_NEED_TO_PROCESS = 1000
    GLOBAL_UPDATE_FREQUENCY = 1
    BUFFER_LIMIT = 1 * BATCH_SIZE


class Statistics:
    processed_pkts = 0
    received_packets = 0
    total_packet_size = 0
    total_delay_time = 0
    total_three_pc_time = 0
    packet_dropped = 0


# (st_time, en_time) - processing time

class State:
    per_flow_cnt = {}


class EchoUDP(DatagramProtocol):

    def process_a_packet(self,packet, packet_id):
        Statistics.processed_pkts += 1
        Statistics.total_packet_size += len(packet)
        print(f'Length of packet is {len(packet)}')
        print(f'Processed pkts: {Statistics.processed_pkts}')

        # index 0: b'data 
        # index 1: local pkt_id
        # index 2: src_ip
        # index 3: src_port
        # index 4: dst_ip
        # index 5: dst_port (hazelcast client addr)
        pkt_info = str(packet).split("#")
        print(f'packet info index 0 :    {pkt_info[0]}')
        print(f'pura packet arr :    {pkt_info}')
        local_pkt_id = pkt_info[1]

        Statistics.total_delay_time += Helpers.get_current_time_in_ms() - BufferTimeMaps.input_in[packet_id]

        Buffers.output_buffer.put((packet, packet_id))
        BufferTimeMaps.output_in[packet_id] = Helpers.get_current_time_in_ms()


    def process_packet_with_hazelcast(self):
        pkt_num_of_cur_batch = 0
        uniform_global_distance = Limit.BATCH_SIZE // Limit.GLOBAL_UPDATE_FREQUENCY

        while True:
            pkt, pkt_id = Buffers.input_buffer.get()

            print(f'packet is {pkt}')
            self.process_a_packet(pkt, pkt_id)       

            pkt_num_of_cur_batch += 1

            if Buffers.output_buffer.qsize() == Limit.BATCH_SIZE:
                pkt_num_of_cur_batch = 0
                self.empty_output_buffer()
                self.local_state_update()

            if pkt_num_of_cur_batch % uniform_global_distance == 0 or pkt_num_of_cur_batch == Limit.BATCH_SIZE:
                self.global_state_update(10)

            if Statistics.processed_pkts + Statistics.packet_dropped == Limit.PKTS_NEED_TO_PROCESS:
                time_delta = Helpers.get_current_time_in_ms() - Timestamps.start_time
                process_time = time_delta / 1000.0 + Statistics.total_three_pc_time

                self.generate_statistics()
                break


    def generate_statistics(self):
        time_delta = Helpers.get_current_time_in_ms() - Timestamps.start_time
        total_process_time = time_delta / 1000.0
        throughput = Statistics.total_packet_size / total_process_time
        latency = Statistics.total_delay_time / Statistics.processed_pkts


        batch_size = int(os.getenv('BATCH_SIZE'))
        buffer_size = int(os.getenv('BUFFER_SIZE'))
        packet_rate = int(os.getenv('PACKET_RATE'))
        
        filename = f'results/batch_{batch_size}-buf_{buffer_size}-pktrate_{packet_rate}.csv'

        with open(filename, 'a') as f:
            # f.write('Latency(ms), Throughput(byte/s), Packets Dropped\n')
            f.write(f'{latency},{throughput},{Statistics.packet_dropped}\n')

    # def send_packet(self,pkt, pkt_id, src_ip, src_port, dst_ip, dst_port):
    #     print("inside send pkt to backup")
    #     s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    #     server_address = (src_ip, src_port)
    #     address = (dst_ip, 5000)
    #     s.connect(address)
    #     print(f' sending to ----- {address}')
    #     s.send(pkt.encode('utf-8'))
    #     print("data gese-----------------------")
    #     s.close()


    def empty_output_buffer(self):
        print("----------Inside empty output buffer-----------")
        
        while not Buffers.output_buffer.empty():

            pkt, pkt_id = Buffers.output_buffer.get()
            print(f'data: {pkt} \n')
            pkt_info = str(pkt).split("#")
            print(f'{pkt_info}')
            print(f'{pkt_info[3]}')
            src_ip , dst_port = pkt_info[4] , pkt_info[5] # from hz_client's perspective (sending to backup)
            x = src_ip.split(".")
            dst_ip = x[0] + "." + x[1] + "." + x[2] + "." + str(int(x[3]) + HZ_CLIENT_CNT)
            print(f'need to send to ---------- {dst_ip}')

            # src_port = 5000
            self.transport.write(bytes(pkt, 'utf-8'), (dst_ip, HZ_CLIENT_LISTEN_PORT))
            # print(f'current pkt {pkt_id}')
            Statistics.total_delay_time += Helpers.get_current_time_in_ms() - BufferTimeMaps.output_in[pkt_id]


    def local_state_update(self):
        # local state update
        # print("------------------------------------------------------------------------------------------------------")
        print(f'replicating on backup as per batch.\n cur_batch: {State.per_flow_cnt}')
        cur_time = Helpers.get_current_time_in_ms()
        global_state = per_flow_packet_counter.get("global")
        master.replicate(global_state)
        Statistics.total_three_pc_time += Helpers.get_current_time_in_ms() - cur_time


    def global_state_update(self,batches_processed: int):
        # global state update
        print(f'Global state update')
        map_key = "global"
        per_flow_packet_counter.lock(map_key)
        value = per_flow_packet_counter.get(map_key)
        per_flow_packet_counter.set(map_key, batches_processed if value is None else value + batches_processed)
        per_flow_packet_counter.unlock(map_key)
        print(per_flow_packet_counter.get(map_key))

    def receive_a_pkt(self,pkt):
        if Statistics.received_packets == 0:
            Timestamps.start_time = Helpers.get_current_time_in_ms()

        Statistics.received_packets += 1
        print(f'received pkts: {Statistics.received_packets}')
        # redis_client.incr("packet_count " + host_var)
        print(f' received pkt ashol: {pkt}')
        modified_pkt = str(pkt)[2:-1]
        print(f' received pkt modified: {modified_pkt}')

        if Buffers.input_buffer.qsize() < Limit.BUFFER_LIMIT:
            Buffers.input_buffer.put((modified_pkt, Statistics.received_packets))
            BufferTimeMaps.input_in[Statistics.received_packets] = Helpers.get_current_time_in_ms()
        else:
            Statistics.packet_dropped += 1
    def datagramReceived(self, datagram, address):
        # print(str(datagram))  
        # print(str(address))   
        # self.transport.write(datagram, address)   
        self.receive_a_pkt(datagram)
        # global_state_update(address)


CLUSTER_NAME = "deft-cluster"
LISTENING_PORT = 8000

def main():
    global master
    addresses = []  # todo: add replica
    if master is None:
        master = Primary(addresses)

    global per_flow_packet_counter

    batch_size = int(os.getenv('BATCH_SIZE'))
    buffer_size = int(os.getenv('BUFFER_SIZE'))
    packet_rate = int(os.getenv('PACKET_RATE'))
    
    filename = f'results/batch_{batch_size}-buf_{buffer_size}-pktrate_{packet_rate}.csv'

    print(f'will open file {filename}')

    print(f"Trying to connect to cluster {CLUSTER_NAME}....")

    hazelcast_client = hazelcast.HazelcastClient(cluster_members=["hazelcast:5701"],
                                                 cluster_name=CLUSTER_NAME)
    # hazelcast_client = hazelcast.HazelcastClient(cluster_members=["172.17.0.2:5701"],
    #                                             cluster_name=CLUSTER_NAME)
    print("Connected!")

    per_flow_packet_counter = Hazelcast.create_per_flow_packet_counter(hazelcast_client)

    udp = EchoUDP()

    hazelcast_thread = threading.Thread(target=udp.process_packet_with_hazelcast)
    hazelcast_thread.start()

    print(f"Listening for packets on port {LISTENING_PORT}")
    reactor.listenUDP(LISTENING_PORT, udp)
    reactor.run()


if __name__ == '__main__':
    main()
