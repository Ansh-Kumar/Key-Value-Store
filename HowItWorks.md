# CSE138_Assignment4

A repository for CSE 138 Assignment 4 work.

## Acknowledgement

We consulted Zuilip for help three times. Thank you to Animesh, Camden, and Yan Tong for clearing up some confusion that we had on the assignment. 

We went to Yan Tong's office hours to get help with our resharding function. He helped us realize that we were hashing and placing our replicas on the consistent hasing circle instead of the the shards. We had to redo how we structured the whole assignment. We changed the consistent hashing circle to be populated by shards instead. He also told us there are easier ways to compute which shard each key needs to go through. Honestly, without him, we probably would not be able to finish this assignment.

## Citations
We used these resources to help create the heartbeat for our down detection. Anytime a node detects that a replica is down, it starts a thread that periodicaly send a request to the downed node to see if its up. This runs while other requests are being done in the system, hence the application of threading

[Threading in Python](https://realpython.com/intro-to-python-threading/)

[Geeks for Geeks: Threading in Python](https://www.geeksforgeeks.org/multithreading-python-set-1/)

[Python Threading Documentation](https://docs.python.org/3/library/threading.html)

We used flask as our web server for the lab, none of us have a lot of experience in Flask so we used the documentation to learn more about the different objects and function available. We went through the tutorial and get started guide to gain a bassic understanding of what Flask has to offer. We also used the documentation to help debug several bugs since the documentation helped us understand function parameters and what they return. 

[Flask Documentation](https://flask.palletsprojects.com/en/3.0.x/)
## Team Contribution

We all worked on this lab together either in person or remotely using Visual Studio Code Liveshare. As for our contributions, we  all work together however each of us specialized in different areas in the code. 

Ansh: I worked on the shard endpoints (specifically resharding). I worked with the team to get it working with the kvs functions because our code depended on those working.

Abhay: I ended up adapting the key endpoint functionality to the sharding mechanism by hashing keys and setting their corresponding attributes.

Kaushal: I worked on the view endpoint altering it from assignment 3, adding the functionality needed for sharding. I also contributed to introducing the different threads used throughout the program such as the heartbeat and the initial broadcast for a brand new replica.

Even through this each of our specializations, we always worked together and collabarated. If only one person was writing the code, others were helping debug and providing advice. 

## Mechanism Descriptions

This where where we explain some of our deicsion choices in how we completed this assignment.

### Causal Dependencies

We use vector clocks to track all the message sends from processes. This way we know if there are any messages that require a happens-before relationship. We use the causal broadcast protocol. We can use this because we made sure all our messages get sent to every correct process. We essentially give every replica thier own vector clock so for example, in this assignment we have a global view dictionary structured as `<view, [VectorClock, ShardID]>`, where any time a replica sent a PUT request, we increment the counter in the VectorClock position by 1. We then have a helper function called `satisfyCausalDependency()` where we take in the Vector Clock array and run it through some specific conditions to determine whether or not causal dependency is satisfied or not.

These checks include:

	VC_m[P_i] = VC_receiver[P_i] + 1
	AND
	VC_m[P_k] <= VC_receiver[P_k], for all k != i

as well as if causal metadata event exists and is defined properly. Anytime a request is sent, the system always runs through this function to determine if causal dependency is satisfied and if it isnt, we return a 503 error.

### Replica Down Detection

To detect if a replica is down, we take advantage of Flasks Internal Server Error 500 and Python's "try-except" statement. When we send a PUT or DELETE request, we iterate through the views and try to broadcast a PUT via the "try-except". If this doesnt go through, in other words, if the program hits the except, we know that this replica we are sending to is down and that we should remove it from the views. We then have a new function called `deleteViews()`, which take in a list of the views that are down to be deleted and send requests to the other replicas to delete the view.

### Sharding Keys Across Nodes

When we first initialize all the nodes, we split up the `shard-count` across the entire consistent hasing circle (we decreed as size 64). We then put each shard in charge of a specific area of that circle. So if there were `shard-count = 3`, we made each shard in charge of 21 hash values. We used dictionary `shards: <shardId, [[nodes], startRange, endRange]>`. After that we used Round Robin to assign each node to a shard. We ordered the list of nodes so that it is consistent among all the nodes by using the python `sort()` function. 

We then checked if the key given to our node is a part of our range when hashed with `hash(key) % 64`. If it is, we handle as usual. If it is not we give it to a random node in the shard that the key does belong to. Each node was responsible for coming up with all these values on their own but we set up a way that the hashes would be consistent throughout all of them.

For resharding, we realized that adding new shards or deleting shards were all done the same way. We first made sure it was possible for 2 nodes to be in each shard. We first recalculated all the shard ranges with the updated shard count. Then we once again used Round Robin to assign all the nodes to the shards. Each node then asks the other nodes in the new shard it is assigned to for their entire datastore and combines it with their own. Then each node looks through their whole datastore. If there is a key that does not belong, we send it as a PUT request to the appropiate shard and delete it from our datastore. (We bypass certain standards to make sure VCs aren't changed through this.) Since every node does this, it appropiately sends all the data to the correct shards.

