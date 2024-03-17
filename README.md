# Key-Value-Store
This is a distributed, sharded, fault-tolerant key-value store.

## Installation and Usage Guide

### Installation
Make sure you have Docker installed. 

To create instances of the application, first build the image with 

```bash
$ docker build -t keyvaluestore .
```
 and create a docker network

 ```bash
$ docker network create --subnet=10.10.0.0/16 storenet
```

To run individual instances in the network (default values are already set but you are welcome to change any of the environment variables)

Alice
```
$ docker run --rm -p 8082:8090 --net=asg4net --ip=10.10.0.2 --name=alice -e=SHARD_COUNT=2 -e=SOCKET_ADDRESS=10.10.0.2:8090 -e=VIEW=10.10.0.2:8090,10.10.0.3:8090,10.10.0.4:8090,10.10.0.5:8090,10.10.0.6:8090,10.10.0.7:8090,10.10.0.8:8090 asg4img
```

Bob
```bash
$ docker run --rm -p 8083:8090 --net=asg4net --ip=10.10.0.3 --name=bob -e=SHARD_COUNT=2 -e=SOCKET_ADDRESS=10.10.0.3:8090 -e=VIEW=10.10.0.2:8090,10.10.0.3:8090,10.10.0.4:8090,10.10.0.5:8090,10.10.0.6:8090,10.10.0.7:8090,10.10.0.8:8090 asg4img
```

Carol
```bash
$ docker run --rm -p 8084:8090 --net=asg4net --ip=10.10.0.4 --name=carol -e=SHARD_COUNT=2 -e=SOCKET_ADDRESS=10.10.0.4:8090 -e=VIEW=10.10.0.2:8090,10.10.0.3:8090,10.10.0.4:8090,10.10.0.5:8090,10.10.0.6:8090,10.10.0.7:8090,10.10.0.8:8090 asg4img
```

Dave
```bash
$ docker run --rm -p 8085:8090 --net=asg4net --ip=10.10.0.5 --name=dave -e=SHARD_COUNT=2 -e=SOCKET_ADDRESS=10.10.0.5:8090 -e=VIEW=10.10.0.2:8090,10.10.0.3:8090,10.10.0.4:8090,10.10.0.5:8090,10.10.0.6:8090,10.10.0.7:8090,10.10.0.8:8090 asg4img
```

Erin
```bash
$ docker run --rm -p 8086:8090 --net=asg4net --ip=10.10.0.6 --name=erin -e=SHARD_COUNT=2 -e=SOCKET_ADDRESS=10.10.0.6:8090 -e=VIEW=10.10.0.2:8090,10.10.0.3:8090,10.10.0.4:8090,10.10.0.5:8090,10.10.0.6:8090,10.10.0.7:8090,10.10.0.8:8090 asg4img
```

Frank
```bash
$ docker run --rm -p 8087:8090 --net=asg4net --ip=10.10.0.7 --name=frank -e=SHARD_COUNT=2 -e=SOCKET_ADDRESS=10.10.0.7:8090
-e=VIEW=10.10.0.2:8090,10.10.0.3:8090,10.10.0.4:8090,10.10.0.5:8090,10.10.0.6:8090,10.10.0.7:8090,10.10.0.8:8090 asg4img
```

Grace
```bash
$ docker run --rm -p 8088:8090 --net=asg4net --ip=10.10.0.8 --name=grace -e=SHARD_COUNT=2 -e=SOCKET_ADDRESS=10.10.0.8:8090
-e=VIEW=10.10.0.2:8090,10.10.0.3:8090,10.10.0.4:8090,10.10.0.5:8090,10.10.0.6:8090,10.10.0.7:8090,10.10.0.8:8090 asg4img
```

## View Operations

### /view PUT

To add a view,

```bash
$ curl --request PUT --header "Content-Type: application/json" --data '{"socket-address":<NEW-REPLICA>}' http://<EXISTING-REPLICA>/view
```

### /view GET

```bash
$ curl --request GET --header "Content-Type: application/json" --write-out "\n%{http_code}\n" --data '{"socket-address":<NEW REPLICA>}' http://<REPLICA>/view
```

### /view DELETE

```bash
$ curl --request DELETE --header "Content-Type: application/json" --data '{"socket-address":<NEW-REPLICA>}' http://<EXISTING-REPLICA>/view
```

## Key-Value Operations

### /kvs/[key] PUT

In this case, you want to put {'x':1} into the store:

```bash
$ curl --request PUT --header "Content-Type: application/json" --write-out "\n%{http_code}\n" --data '{"value":1,"causal-metadata":null}' http://<REPLICA>/kvs/x
```

Now any subsequent requests must carry the most recent "causal-metadata" that you get back as a response from the store.

### /kvs/[key] GET

In this case, you want to get 'x':

```bash
$ curl --request GET --header "Content-Type: application/json" --write-out "\n%{http_code}\n" --data '{"causal-metadata":null}' http://<REPLICA>/kvs/x {"result": "found", "value":2, "causal-metadata": <V1>}
```

### /kvs/[key] DELETE

To delete 'x' from the store:

```bash
$ curl --request DELETE --header "Content-Type: application/json" --write-out "\n%{http_code}\n" --data '{"causal-metadata":<V1>}' http://<REPLICA>/kvs/x
```

## Shard Operations

### /shard/ids GET

Get all the shard-ids

```bash
$ curl --request GET --header "Content-Type: application/json" --write-out "\n%{http_code}\n" http://<REPLICA>/shard/ids
```
### /shard/node-shard-id GET

Get shard identifier for a given node

```bash
curl --request GET http://<IP:PORT>/shard/<IP>:<PORT>
```

### /shard/members/[ID] GET 

Get all the members of a shard-id ID

```bash
curl --request GET http://<IP:PORT>/shard/members/<ID>
```

### /shard/key-count/[ID] GET

Get the number of keys in a shard-id ID

```bash
curl --request GET http://<IP:PORT>/shard/key-count/<ID>
```

### /shard/add-member/[ID] PUT 

Put a node into shard-id ID

```bash
$ curl --request PUT --header "Content-Type: application/json" --write-out "\n%{http_code}\n" --data '{"socket-address": "10.10.0.5:8085"}' http://localhost:8082/shard/add-member/<ID>
```

### /shard/reshard PUT

Reshard the replicas into shard-count number of shards

```bash
$ curl --request PUT --header "Content-Type: application/json" --write-out "\n%{http_code}\n" --data '{"shard-count": <INTEGER>}' http://localhost:8082/shard/reshard
```
