#!/bin/bash

# ************************************ Delete and Add bridges ************************************
sudo ovs-vsctl del-br ovs-br1
sudo ovs-vsctl add-br ovs-br1
sudo ovs-vsctl del-br ovs-br2
sudo ovs-vsctl add-br ovs-br2
sudo ovs-vsctl del-br ovs-br0
sudo ovs-vsctl add-br ovs-br0

HZ_CLIENT_CNT=$(grep HZ_CLIENT_CNT .env | cut -d '=' -f2)
HZ_CLIENT_CLUSTER_CNT=$(grep HZ_CLIENT_CLUSTER_CNT .env | cut -d '=' -f2)
HZ_CLIENT_IP_PATTERN_one=$(grep HZ_CLIENT_IP_PATTERN_one .env | cut -d '=' -f2)
HZ_CLIENT_IP_PATTERN_two=$(grep HZ_CLIENT_IP_PATTERN_two .env | cut -d '=' -f2)
HZ_CLIENT_IP_PATTERN_three=$(grep HZ_CLIENT_IP_PATTERN_three .env | cut -d '=' -f2)



# sudo ifconfig ovs-br1 173.16.1.1 netmask 255.255.255.0 up
# **************************** DON'T YOU EVER TRY TO CHANGE BRIDGE NUMBER SEQUENCE ****************************
# *********************************************** DANGER ZONE *************************************************
sudo ifconfig ovs-br1 "${HZ_CLIENT_IP_PATTERN_one/$/1}" netmask 255.255.255.0 up
sudo ifconfig ovs-br2 "${HZ_CLIENT_IP_PATTERN_two/$/1}" netmask 255.255.255.0 up
sudo ifconfig ovs-br0 "${HZ_CLIENT_IP_PATTERN_three/$/1}" netmask 255.255.255.0 up

j=1
for (((i=HZ_CLIENT_CNT*(j-1) + 1);i<=(HZ_CLIENT_CNT*j);i++)); 
do
    client_ip=${HZ_CLIENT_IP_PATTERN_one/$/$((i + 1))}/24
    client_name=txts_unit_hz_client_$i
    command="sudo ovs-docker add-port ovs-br1 eth1 $client_name --ipaddress=$client_ip"
    
    echo "$command"
    $command

    client_ip=${HZ_CLIENT_IP_PATTERN_one/$/$((i + HZ_CLIENT_CNT + 1))}/24
    client_name=txts_unit_hz_client_backup_$i
    command="sudo ovs-docker add-port ovs-br1 eth1 $client_name --ipaddress=$client_ip"
    
    echo "$command"
    $command
done


j=2
x=1
for (((i=HZ_CLIENT_CNT*(j-1) + 1);i<=(HZ_CLIENT_CNT*j);i++));
do
    client_ip=${HZ_CLIENT_IP_PATTERN_two/$/$((x + 1))}/24
    client_name=txts_unit_hz_client_$i
    command="sudo ovs-docker add-port ovs-br2 eth1 $client_name --ipaddress=$client_ip"
    
    echo "$command"
    $command

    client_ip=${HZ_CLIENT_IP_PATTERN_two/$/$((x + HZ_CLIENT_CNT + 1))}/24
    client_name=txts_unit_hz_client_backup_$i
    command="sudo ovs-docker add-port ovs-br2 eth1 $client_name --ipaddress=$client_ip"
    
    echo "$command"
    $command
    ((x++))
done


j=3
x=1
for (((i=HZ_CLIENT_CNT*(j-1) + 1);i<=(HZ_CLIENT_CNT*j);i++));
do
    client_ip=${HZ_CLIENT_IP_PATTERN_three/$/$((x + 1))}/24
    client_name=txts_unit_hz_client_$i
    command="sudo ovs-docker add-port ovs-br0 eth1 $client_name --ipaddress=$client_ip"
    
    echo "$command"
    $command

    client_ip=${HZ_CLIENT_IP_PATTERN_three/$/$((x + HZ_CLIENT_CNT + 1))}/24
    client_name=txts_unit_hz_client_backup_$i
    command="sudo ovs-docker add-port ovs-br0 eth1 $client_name --ipaddress=$client_ip"
    
    echo "$command"
    $command
    ((x++))
done


# sudo ovs-docker add-port ovs-br1 eth1 txts_unit_hz_client_1 --ipaddress=173.16.1.2/24
# sudo ovs-docker add-port ovs-br1 eth1 txts_unit_hz_client_2 --ipaddress=173.16.1.3/24
