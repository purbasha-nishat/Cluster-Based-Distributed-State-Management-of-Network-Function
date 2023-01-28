#!/bin/bash

for ((i=1;i<=3;i++));
do
    command='packetsender --num 334 --usdelay 500 -A  127.0.0.1 8080 "hello"'
    # command='packetsender --num 334 --usdelay 100 -A  127.0.0.1 8080 "hello"'
    # command='packetsender --num 334 --usdelay 1000 -A  127.0.0.1 8080 "hello"'
    
    echo "$command"
    $command
    ((x++))
done