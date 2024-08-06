# Cluster Based Distributed State Management of Network Function

This is the official repository containing all the codes used to generate the results of our undergraduate thesis named "Cluster Based Distributed State Management of Network Function". We propose a cluster based distributed state management system for network function that supports dynamic and efficient flow and state migration information from one network function to another. We hereby present three novel mechanisms to ensure the efficient functioning of stateful NFs. Firstly, multithreaded network functions are introduced for faster packet processing and efficient utilization of resources. Secondly, we propose a cluster-based NF state replication scheme to reduce bandwidth requirements during flow migration. States are replicated among all cluster members continually, which results in efficient state migration when a flow migration takes place without overloading the network. Finally, an enhanced cluster-based load balancing approach is presented to improve the system’s load distribution. This approach makes sure that no node is being over-utilized, preventing a single node from becoming a bottleneck.

## Table of Contents
- [Cluster Based Distributed State Management of Network Function](#cluster-based-distributed-state-management-of-network-function)
- [Table of Contents](#table-of-contents)
- [Setup](#setup)
- [Design Goals](#design-goals)
- [Methodology](#methodology)
- [Experiments and Results](#experiments-and-results)
- [Future Work](#future-work)

## Setup
We have used [Docker](https://docs.docker.com/engine/release-notes/23.0/) for easy deplyment of the application, [Hazelcast](https://github.com/hazelcast/hazelcast) for our consensus module and [Packet Sender](https://packetsender.com/) to generate UDP packets and run the experiments.

To run the codes smoothly, please follow the given steps carefully:
- Go to directory `src/txts_unit`

- Run the docker-compose
```
sudo docker-compose up -d --build
```

- Make the `net_setup.sh` file executable
```
sudo chmod +x net_setup.sh
```

- Add the Open vSwitch network
```
./net_setup.sh
```

- To check log of a service
```
sudo docker-compose logs -f <service_name>
```
`<service_name>` can be `hazelcast`, `hz_client`, `hz_client_backup`, `stamper` or `nginx`


- Send UDP packets on localhost port 8080
```
packetsender --num 10 -A  127.0.0.1 8080 "hello"
```
## Design Goals

We want to design a distributed state management system that
 - Ensures faster processing of packets through multithreading.
 - Ensures reduced overhead during state migration by implementing clustering.
 - Uses an enhanced cluster-based load balancing algorithm that prevents NF
overload, causing reduced latency.

So we gave three design goals- 
 - Multithreading Goals
   - Packets of different flows will be processed in different threads.
   - Multiple flows can be processed in parallel.
   - Output buffer will be filled up much faster.
   - Overall latency is decreased. 
 - Clustering Goals
   - Network function instances will be grouped in clusters.
   - After each batch process, an NF instance will share its state info with the other members of the cluster.
   - State migration will require only the migration of the information of the latest processed batch.
   - State migration overhead will be reduced significantly.
 - Load Balancing Goals
   - An enhanced cluster-based load balancing algorithm to prevent NFs from being overloaded.
   - Whenever an NF instance is overloaded, a flow is redirected to another NF instance.
   - Decreased load will allow the NF to process faster.
   - Overall latency is decreased.


## Methodology

### Architecture and Components

#### Network Topology
Our network topology is given below:

<img src="Figures\Components\topology.JPG">

The SDN controller is connected to the two switches
and the load balancing unit. All the input packets from the client come through switch-1 and then go through the stamper unit. The stamper unit assigns a packet number to each packet from each flow and forwards them to the load balancing unit(LBU). The LBU then forwards them to switch 2. After that switch 2 forwards the packets to designated primary Network Function (NF) and its secondary NF.

#### Primary Network Function

 Here's the high-level design of our architecture of the primary network function:

<img src="Figures\Components\Primary NF.JPG">

#### Failure Detection Unit(FDU)
Our system has a failure detection unit(FDU) which detects the primary NF failure. We have inherited this concept from DEFT.

### Operations

We have proposed three operations while processing the network packets.

 - Normal Operation

    In normal operation until any flow migration events happen, packets from the same flow will always be delivered to the same NF. Different flows will be distributed among multiple NFs.

    Strict consistency is ensured between primary and secondary network functions (NFs) by processing packets in the same order across both NFs. Initially, packets are forwarded to a stamper and then to a load balancing unit (LBU) for routing and duplication. Each packet receives a unique identifier from the stamper to track and order packet processing. Primary NFs maintain an input buffer to handle out-of-order packets and process them sequentially based on their identifiers. Processed packets are held in an output buffer until a batch of consecutively numbered packets is formed. Once a batch is complete, updated state information is broadcasted to secondary NFs and other primary NFs in the cluster, ensuring consistency across all NFs.

 - Flow Migration Operation
    
    The flow migration situation occurs when any primary NF becomes overloaded. In that case, we have developed an enhanced cluster based load balancing algorithm to tackle this situation. Here's the flow chart of the Cluster-Based Load Balancing Algorithm:

    <img src="Figures\Components\LB algo.JPG">

    When the destination NF is in the same cluster, the overloaded NF buffers packets and sends updated state information to the selected NF. The SDN controller updates the flow rule, and the buffered packets are then forwarded to the destination NF. For destinations in different clusters, the overloaded NF must send complete state information for all packets up to the migration event, due to the lack of pre-existing state information at the new cluster. The subsequent steps remain similar to those for same-cluster destinations.

 - Failover Operation
    
    In the event of a Network Function (NF) failure, Failure Detection Unit (FDU) identifies the failure and notifies the relevant secondary NF and the secondary NF now becomes the primary NF. A new secondary NF is designated, and state information is migrated to ensure consistency. Buffered packets are processed by the new primary NF, and the SDN controller updates the flow rules to redirect packets to the new primary NF and duplicate packets to the new secondary NF. This approach ensures no packet loss and maintains operational continuity.

    <p align="center">
    <img src="Figures\Components\fail1.JPG" width="45%" height="195px" alt="S1">
    <img src="Figures\Components\fail2.JPG" width="45%" height="195px" alt="S2">
    </p>



## Experiments and Results

### Results of Multithreading

#### Latency vs Number of Threads

<!-- | Parameter                     |          Value     |
|-------------------------------|--------------------|
| Total Packets Processed       | 4000               | 
| Packet Rate                   | 100 pkt/second     | 
| Batch Size                    | 30                 | 
| Number of Network Functions   | 1                  |  -->

<img src="Figures\Experiments\Latency vs. Number of Threads.png" width="100%">

#### Throughput vs Number of Threads

<img src="Figures\Experiments\Throughput vs. Number of Threads.png" width="100%">

### Effects of Clustering

#### Throughput vs Batch Size

<img src="Figures\Experiments\Throughput vs. Batch Size.png" width="100%">

#### Throughput vs Packet Rate

<img src="Figures\Experiments\Throughput vs. Packet Rate.png" width="100%">

### Results of State Migration Overhead in Clustering

For this experiment, we consider a 2-cluster system where each cluster contains 2 NFs. NF-1 and NF-2 are located in Cluster-1 and NF-3 and NF-4 are located in Cluster-2. The flow first migrates to NF-2 of Cluster-1, then to NF-3 of Cluster-2.

<p align="center">
    <img src="Figures\Experiments\State Info (bytes) vs. Packet Count_1.png" width="32%" alt="S1">
    <img src="Figures\Experiments\State Info (bytes) vs. Packet Count_2.png" width="32%" alt="S2">
    <img src="Figures\Experiments\State Info (bytes) vs. Packet Count_3.png" width="32%" alt="S3">
</p>


### Results of Load Balancing

#### Latency vs Packet Rate

<img src="Figures\Experiments\Effect of Load Balancing for 3 Clusters.png" width="100%">


## Future Work


Future research could enhance the system's capabilities in several ways. One direction is exploring cluster-based global states, which could reduce synchronization costs and improve scalability by managing states within localized clusters. Another area involves comparing the custom load balancer with other methods to identify performance and scalability benefits. Additionally, investigating various consensus algorithms could improve global state updates and fault tolerance. Ensuring strict consistency of global states without a centralized controller is another critical area, requiring new protocols for synchronized updates. Lastly, a comparative analysis of system performance against existing solutions will be crucial to validate and refine its effectiveness.