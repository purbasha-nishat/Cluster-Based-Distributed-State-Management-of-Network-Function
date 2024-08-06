# Cluster Based Distributed State Management of Network Function

This is the official repository containing all the codes used to generate the results of our undergraduate thesis named "Cluster Based Distributed State Management of Network Function". We propose a cluster based distributed state management system for network function that supports dynamic and efficient flow and state migration information from one network function to another. We hereby present three novel mechanisms to ensure the efficient functioning of stateful NFs. Firstly, multithreaded network functions are introduced for faster packet processing and efficient utilization of resources. Secondly, we propose a cluster-based NF state replication scheme to reduce bandwidth requirements during flow migration. States are replicated among all cluster members continually, which results in efficient state migration when a flow migration takes place without overloading the network. Finally, an enhanced cluster-based load balancing approach is presented to improve the system’s load distribution. This approach makes sure that no node is being over-utilized, preventing a single node from becoming a bottleneck.

## Table of Contents
- [Cluster Based Distributed State Management of Network Function](#cluster-based-distributed-state-management-of-network-function)
- [Table of Contents](#table-of-contents)
- [Setup](#setup)


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

## Methotogoly
### Architecture and Components


