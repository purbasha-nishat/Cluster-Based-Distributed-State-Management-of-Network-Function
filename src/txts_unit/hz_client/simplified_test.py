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
    PKTS_NEED_TO_PROCESS = 250
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
    def __init__(self):
        self.flow_to_pkt_cnt = {}
        self.all_flow_info = {}
        self.pending_pkt_map = {}       # (flow_id -> pq of pkt cnt) 
        self.flow_id_pkt_id_to_pkt = {}
        self.next_expected_stamp_id = {}
        self.own_ip = ''
    
    def get_flow_id(self, pkt):
        pkt_info = str(pkt).split("#")
        flow_id = (pkt_info[2], pkt_info[3], pkt_info[4], pkt_info[5])
        return flow_id

    def update_flow_pkt_count(self, flow):
        
        if self.flow_to_pkt_cnt.get(flow) is not None:
            self.flow_to_pkt_cnt[flow] +=1    
        else:
            self.flow_to_pkt_cnt[flow] = 1
        
        if self.all_flow_info.get(flow) is not None:
            self.all_flow_info[flow] +=1    
        else:
            self.all_flow_info[flow] = 1
        
            # print(f'updated pkt count for {flow} is {self.flow_to_pkt_cnt[flow]}')

    def update_all_flow(self,pkt):
        # print('all flow\n\n')
        # print(f'update pkt:    {pkt}')
        pkt_info = str(pkt).split("#")
        flow = (pkt_info[1], pkt_info[2], pkt_info[3], pkt_info[4])
        pkt_cnt = pkt_info[5]
        if self.all_flow_info.get(flow) is not None:
            self.all_flow_info[flow] = pkt_cnt    
        else:
            self.all_flow_info[flow] = pkt_cnt
        print(f'all info dict: {self.all_flow_info}')

    def process_a_packet(self,pkt, pkt_id):
        Statistics.processed_pkts += 1
        Statistics.total_packet_size += len(pkt)
        # print(f'Length of packet is {len(packet)}')
        print(f'Processed pkts: {Statistics.processed_pkts}')

        # index 0: b'data 
        # index 1: local pkt_id
        # index 2: src_ip
        # index 3: src_port
        # index 4: dst_ip
        # index 5: dst_port (hazelcast client addr)
        pkt_info = str(pkt).split("#")
        local_pkt_id = pkt_info[1]
        flow_id = self.get_flow_id(pkt)

        self.update_flow_pkt_count(flow_id)

        Statistics.total_delay_time += Helpers.get_current_time_in_ms() - BufferTimeMaps.input_in[pkt_id]

        Buffers.output_buffer.put((pkt, pkt_id))
        BufferTimeMaps.output_in[pkt_id] = Helpers.get_current_time_in_ms()

    def should_process_pkt(self, pkt):
        # print("-------------should process pkt\n\n-----------------")
        pkt_info = str(pkt).split("#")
        
        pkt_id = int(pkt_info[1])
        flow_id = self.get_flow_id(pkt)
        
        if flow_id not in self.next_expected_stamp_id:
            self.next_expected_stamp_id[flow_id] = 1

        if pkt_id == self.next_expected_stamp_id[flow_id]:
            self.next_expected_stamp_id[flow_id] += 1
            return True

        return False

    def should_pop_from_pending_map (self,flow_id):
        # print('-----------------should pop from pending list-----------------\n\n')

        # print(self.pending_pkt_map[flow_id])

        if self.pending_pkt_map.get(flow_id) is not None:
            if not self.pending_pkt_map[flow_id].empty():
                pkt_id = self.pending_pkt_map[flow_id].queue[0]
                if pkt_id == self.next_expected_stamp_id[flow_id]:
                    self.next_expected_stamp_id[flow_id] += 1
                    return True
                else:
                    return False
            else:
                return False
        else:
            return False

    def insert_in_pending_map (self,pkt):

        # print('-----------------pending list-----------------\n\n')
        pkt_info = str(pkt).split("#")
        pkt_cnt = int(pkt_info[1])
        flow_id = self.get_flow_id(pkt)

        if self.pending_pkt_map.get(flow_id) is not None:
            self.pending_pkt_map[flow_id].put(pkt_cnt)
        else:
            self.pending_pkt_map[flow_id] = queue.PriorityQueue()
            self.pending_pkt_map[flow_id].put(pkt_cnt)

        # print(f'pending list: {self.pending_pkt_map[flow_id].queue} size: {self.pending_pkt_map[flow_id].qsize()}')
        self.flow_id_pkt_id_to_pkt[(flow_id, pkt_cnt)] = pkt


    def process_packet_with_hazelcast(self):
        pkt_num_of_cur_batch = 0
        uniform_global_distance = Limit.BATCH_SIZE // Limit.GLOBAL_UPDATE_FREQUENCY

        while True:
            pkt, pkt_id = Buffers.input_buffer.get()

            print(f'packet in process pkt with hz: {pkt}')

            if not self.should_process_pkt(pkt):
                print(f'---------------------------waiting list e ------ {pkt_id}')
                self.insert_in_pending_map(pkt)
            else: 
                self.process_a_packet(pkt, pkt_id)       
                pkt_num_of_cur_batch += 1

            flow_id = self.get_flow_id(pkt)
            while self.should_pop_from_pending_map(flow_id):
                pkt_id = self.pending_pkt_map[flow_id].get()
                pkt = self.flow_id_pkt_id_to_pkt[(flow_id, pkt_id)]
                self.process_a_packet(pkt, int(pkt_id))
                pkt_num_of_cur_batch += 1
            
            if Buffers.output_buffer.qsize() == Limit.BATCH_SIZE:
                pkt_num_of_cur_batch = 0
                self.empty_output_buffer()
                self.local_state_update()

            if pkt_num_of_cur_batch % uniform_global_distance == 0 or pkt_num_of_cur_batch == Limit.BATCH_SIZE:
                self.global_state_update(10)

            if Statistics.processed_pkts + Statistics.packet_dropped >= Limit.PKTS_NEED_TO_PROCESS:
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


    def empty_output_buffer(self):
        print("----------Inside empty output buffer-----------")

        # sending info to all members of a cluster // flow_id and pkt_cnt
        for f in self.flow_to_pkt_cnt:
            src_ip , src_port , dst_ip , dst_port = f
            pkt = f'update#{src_ip}#{src_port}#{dst_ip}#{dst_port}#{self.flow_to_pkt_cnt[f]}'
            
            for i in range(HZ_CLIENT_CNT):
                ip_breakdown = dst_ip.split('.')
                sending_ip = ip_breakdown[0] + '.' + ip_breakdown[1] + '.' + ip_breakdown[2] + '.' + str(i+2)
                if sending_ip != dst_ip:
                    # print(f'asholei going from dest_ip: {dst_ip} and sending_ip in cluster: {sending_ip} -----------------')
                    self.transport.write(bytes(pkt, 'utf-8'), (sending_ip, HZ_CLIENT_LISTEN_PORT))

        # sending info to its own backup
        while not Buffers.output_buffer.empty():

            pkt, pkt_id = Buffers.output_buffer.get()
            # print(f'data: {pkt} \n')
            pkt_info = str(pkt).split("#")
            print(f'{pkt_info}')
            print(f'{pkt_info[3]}')
            src_ip , dst_port = pkt_info[4] , pkt_info[5] # from hz_client's perspective (sending to backup)
            x = src_ip.split(".")
            dst_ip = x[0] + "." + x[1] + "." + x[2] + "." + str(int(x[3]) + HZ_CLIENT_CNT)
            # print(f'need to send to ---------- {dst_ip}')

            self.transport.write(bytes(pkt, 'utf-8'), (dst_ip, HZ_CLIENT_LISTEN_PORT))
            # print(f'current pkt {pkt_id}')
            Statistics.total_delay_time += Helpers.get_current_time_in_ms() - BufferTimeMaps.output_in[pkt_id]


    def local_state_update(self):
        # local state update
        # print("------------------------------------------------------------------------------------------------------")
        # print(f'replicating on backup as per batch.\n cur_batch: {State.per_flow_cnt}')
        cur_time = Helpers.get_current_time_in_ms()
        global_state = per_flow_packet_counter.get("global")
        master.replicate(global_state)
        Statistics.total_three_pc_time += Helpers.get_current_time_in_ms() - cur_time


    def global_state_update(self,batches_processed: int):
        # global state update
        # print(f'Global state update')
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
        print(f'received pkts: {Statistics.received_packets} and pkt: {pkt}')
        # redis_client.incr("packet_count " + host_var)
        # print(f' received pkt ashol: {pkt}')
        modified_pkt = str(pkt)[2:-1]
        # print(f' received pkt modified: {modified_pkt}')

        x = modified_pkt.split("#")
        if x[0] == "update":
            self.update_all_flow(modified_pkt)
            return


        if Statistics.received_packets == 1:
            x = modified_pkt.split("#")
            self.own_ip = x[4]
            print(f'own ip: {self.own_ip}')

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
