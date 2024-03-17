from flask import Flask, request, Response
import json
import os
import requests
import time
import sys
import threading

app = Flask(__name__)


# ======== GLOBAL VARIABLES ==============

global HASH_SIZE 
HASH_SIZE = 64

global dataStore
# key-value store
dataStore = dict() 

global views
# dict of views (replicas that exist)
# type: <view, [VC, shardId]>
views = dict()

# set of all downed replicas
global downed
downed = set()

# dict of shards <shardId, [list of nodes, start, end]>
global shards
shards = dict()

#current shard
global currShard
currShard = None

global socketAddress
#IP:PORT of local 
socketAddress = os.environ.get("SOCKET_ADDRESS", None)

global shardCount
# number of shards
shardCount = os.environ.get("SHARD_COUNT", None)

# ======== HELPER FUNCTIONS ==============

# round robins all nodes into shards guarantee 2+ nodes in each
def roundRobin(listOfViews):
	global currShard
	# round robin sharding
	listOfViews.sort()
	counter = 1
	while len(listOfViews) > 0:
		if counter == shardCount + 1:
			counter = 1
		view = listOfViews.pop(0)
		# add view to shard
		shards[f"s{counter}"][0].append(view)
		# add shard ID to view
		views[view][1] = f"s{counter}"
		print(f"{view=}", file=sys.stderr)
		print(f"{socketAddress=}", file=sys.stderr)
		# setting current shard
		if view == socketAddress:
			print("in here!", file=sys.stderr)
			currShard = f"s{counter}"
			print(f"{currShard}", file=sys.stderr)
		counter += 1
	return

# helper function to determine if the causal dependency is accurate
# returns true if it is and false otherwise
def satisfyCausalDependency(req: dict) -> tuple[bool, str]:
	# If a message sent by P_1 is delievered at a process P_2, increment P_2's VC
	# in the P_1 position (the senders position)

	# If a message is sent by a process increment the sender's position in the
	# sender's VC, and include that VC along with the message

	# A message sent by a process P_1 only gets delivered at P_2 if for the
	# messages VC_m: 

	# VC_m[P_i] = VC_receiver[P_i] + 1
	# AND
	# VC_m[P_k] <= VC_receiver[P_k], for all k != i
	if 'causal-metadata' not in req:
		return (False, None)
	if req['causal-metadata'] == None:
		return (True, None)
	# this is VC_m
	if type(req['causal-metadata']) == str:
		req['causal-metadata'] = json.loads(req['causal-metadata'])
	#causal_metadata is entire views dict
	causal_metadata = req['causal-metadata']
	if set(causal_metadata.keys()) != set(views.keys()):
		return (False, None)
	more = False # tracks if we found a VC that is more than receiver
	sender = None
	# get all views in current shard and 
	# ONLY check causual dependency for views in current shard
	for view in shards[currShard][0]:
		if causal_metadata[view][0] > views[view][0] + 1:
			return (False, None) # breaks condition 1
		elif causal_metadata[view][0] == views[view][0] + 1:
			if more:
				return (False, None) # more than 1 positions are greater than
			more = True
			sender = view # this is who sent us the request
	return (True, sender)

# helper function: updates all the views given a vector clock
# passing in the entire views dict
def updateVC(vectorClock: dict):
	# global views
	for view in views:
		if view != socketAddress and views[view][0] < vectorClock[view][0]:
			views[view][0] = vectorClock[view][0]

def deleteViews(viewsToDelete: list, case=None):
	print(f"{viewsToDelete = }")
	newViewsToDelete = []
	if len(viewsToDelete) == 0:
		return
	for view in viewsToDelete:
		del views[view]
		downed.add(view)
	for view in views:
		if view != socketAddress:	
			for to_delete in viewsToDelete:
				try:
					res = requests.delete(url=f"http://{view}/view", json={'socket-address': to_delete})
					while res.status_code == 503:
						time.sleep(1)
						res = requests.delete(url=f"http://{view}/view", json={'socket-address': to_delete})
				except:
					print(f"found out {view} is down on line 132", file=sys.stderr)
					newViewsToDelete.append(view)
					continue
	deleteViews(newViewsToDelete, case="self")
	currentViews = views
	currentStore = dataStore
	t1 = threading.Thread(target=talkToDowned, args=[currentViews, currentStore])
	t1.start()


# when called it will send requests to all the downed
# replicas to see if they back up
def talkToDowned(currentViews, currentStore):
	global downed # might be useful
	while len(downed) > 0:
		removedFromDown = set()
		for view in downed:
			try:
				print(f"I'm talking to {view}", file=sys.stderr)
				requests.put(url=f"http://{view}/view", json={'socket-address': socketAddress,'heartbeat': True ,'data-store': json.dumps(currentStore), 'views': json.dumps(currentViews)})
			except: 
				continue
			# if the try did work
			views[view] = [0, None]
			removedFromDown.add(view)
			print(f"added {view} back to views", file=sys.stderr)
		print(f"{removedFromDown=}", file=sys.stderr)
		downed -= removedFromDown
		time.sleep(1)

def broadcastAlive(views, socketAddress):
	for view in views:
		if view != socketAddress:
			try:
				print(f"sending broadcastAlive to {view} from {socketAddress}", file=sys.stderr)
				res = requests.put(url=f"http://{view}/view", json={"socket-address": socketAddress})
				break
			except:
				print(f"init broadcast failed", file=sys.stderr)
				continue

def getShardThread(views, socketAddress):
	global shards
	for view in views:
		if view != socketAddress:
			try:
				print(f"sending getShardThreads to {view} from {socketAddress}", file=sys.stderr)
				res = requests.get(url=f"http://{view}/shard/getShards")
				print(f"{res.json()=}", file=sys.stderr)
				r = res.json()
				shards = r['shards']
				break
			except:
				print(f"init shard get failed", file=sys.stderr)
				continue
# ======= STARTUP ============================================================ 
print("start up code", file=sys.stderr)
listOfViews = os.environ.get("VIEW", None)
if listOfViews is not None:
	listOfViews = listOfViews.split(',')
	for view in listOfViews:
		views[view] = [0, None]
print(f"populated views as {views}", file=sys.stderr)


# we need to define the ranges for shards
if shardCount:
	shardCount = int(shardCount)
	#set up ranges
	lenOfRange = HASH_SIZE // shardCount
	counter = 0
	for s in range(shardCount):
		if counter+lenOfRange > HASH_SIZE:
			shards[f"s{s+1}"] = [[], int(counter), HASH_SIZE-1]
		else:
			shards[f"s{s+1}"] = [[], int(counter), int(counter+lenOfRange)]
		counter += lenOfRange + 1
	print(f"{shards=}", file=sys.stderr)
	print('round robin starting', file=sys.stderr)
	# we now distribute all the nodes to shards
	roundRobin(listOfViews)
else: # if a node is started by sys admin after system is running
	print('broadcasting im alive', file=sys.stderr)
	#send put to view
	t1 = threading.Thread(target=broadcastAlive, args=[views, socketAddress])
	t1.start()
	t2 = threading.Thread(target=getShardThread, args=[views, socketAddress])
	t2.start()
	print("i have broadcasted", file=sys.stderr)

@app.route('/view', methods=['GET', 'PUT', 'DELETE'])
def view():
	global views
	global dataStore 
	global socketAddress 
	global shards
	if (request.method == 'GET'):
		# view - GET
		# get the list of views which are all the keys of views
		return Response(response=json.dumps({"view": list(views.keys())}), status=200, content_type="application/json")
	
	elif (request.method == 'PUT'):
		print("got PUT /view", file=sys.stderr)
		if type(request.json) != dict:
			j = json.loads(request.json)
		else:
			j = request.json
		new_view = j['socket-address']
		if 'data-store' in j:
			print("recieved a put with extra metadata", file=sys.stderr)
			#are there any vcs saved?
			is_network_fail = False
			print(f"{views=}", file=sys.stderr)
			for view in views:
				if views[view][0] != 0:
					is_network_fail = True
					print("is network failure", file=sys.stderr)
					
			#if crashed
			if not is_network_fail and 'heartbeat' in j:
				print("crashed node", file=sys.stderr)
				dataStore = json.loads(j['data-store'])
				views = json.loads(j['views'])
				views[socketAddress][0] = 0
				shards = json.loads(j['shards'])

			#if brand new node
			if not is_network_fail:
				print("new node, copying shards", file=sys.stderr)
				shards = json.loads(j['shards'])

		if new_view not in views:
			print("this is a new view thats not in views", file=sys.stderr)
			# add new view to views
			views[new_view] = [0, None]
			# iterate through all the views 
			# the views that we try to send to might be dead so keep track to delete
			viewsToDelete = []
			for view in views:
				try:
					if view != socketAddress and view != new_view:
						print(f"sendin PUT /view to {view=}", file=sys.stderr)
						res = requests.put(url=f"http://{view}/view", json={'socket-address': new_view})
						while res.status_code == 503:
							print(f"did not work...sending PUT /view to {view=} again", file=sys.stderr)
							time.sleep(1)
							res = requests.put(url=f"http://{view}/view", json={'socket-address': new_view})
				except:
					# if view is not alive, we add to list of views to delete
					print(f"found out {view} is down on line 257", file=sys.stderr)
					viewsToDelete.append(view)
					continue
			# delete all views that we know are not alive
			print(f"broadcasted, heres views to delete: {viewsToDelete}", file=sys.stderr)
			deleteViews(viewsToDelete)
			# send full list of information to new node
			print("going to send response", file=sys.stderr)
			time.sleep(15)
			res = requests.put(url=f"http://{new_view}/view", json={'socket-address': socketAddress,'shards': json.dumps(shards) ,'data-store': json.dumps(dataStore), 'views': json.dumps(views)})
			return Response(response=json.dumps({"result": 'added'}), status=201, content_type="application/json")
		# view is already in views
		print("error response: already present", file=sys.stderr)
		return Response(response=json.dumps({"result": 'already present'}), status=200, content_type="application/json")
	
	elif (request.method == 'DELETE'):
		if type(request.json) != dict:
			req = json.loads(request.json)
		else:
			req = request.json

		to_delete = req['socket-address']
		
		if to_delete in views:
			# remove to_delete from views
			deleteViews([to_delete])
			return Response(response=json.dumps({"result": 'deleted'}), status=200, content_type="application/json")
		return Response(response=json.dumps({"error": 'View has no such replica'}), status=404, content_type="application/json")

# Shard endpoint - untested but should work
@app.route('/shard/ids', methods = ['GET'])
def shardIds():
	return Response(response=json.dumps({"shard-ids": list(shards.keys())}), status=200, content_type="application/json")


@app.route('/shard/node-shard-id', methods = ['GET'])
def shardId():
	return Response(response=json.dumps({"node-shard-id": currShard}), status=200, content_type="application/json")

# get list of all nodes in this shard
@app.route('/shard/members/<ID>', methods = ['GET'])
def shardMembers(ID):
	if ID in shards:
		return Response(response=json.dumps({"shard-members": shards[ID][0]}), status=200, content_type="application/json")
	return Response(response=json.dumps({"error": "Shard ID does not exist"}), status=404, content_type="application/json")

# counts the keys in this datastore
@app.route('/shard/key-count/<ID>', methods = ['GET'])
def shardKeyCount(ID):
	if ID in shards:
		if ID == currShard:
			return Response(response=json.dumps({"shard-key-count": len(dataStore)}), status=200, content_type="application/json")
		# ask a node in the appropiate shard
		# get first node in first node
		firstViewInShard = shards[ID][0][0]
		res = requests.get(url=f"http://{firstViewInShard}/shard/key-count/{ID}")
		return Response(response=json.dumps(res.json()), status=res.status_code, content_type="application/json")
	return Response(response=json.dumps({"error": "Shard ID does not exist"}), status=404, content_type="application/json") 

@app.route('/shard/add-member/<ID>', methods = ['PUT'])
def shardAddMembers(ID):
	global views
	global shards
	global socketAddress
	global currShard
	global dataStore
	req = request.json
	if (type(req) != dict):
		print("line 353", file = sys.stderr)
		req = json.loads(req)
	# req is now a dict
	print(f"{req=}", file=sys.stderr)
	print(f"{shards=}", file=sys.stderr)
	print(f"{ID=}", file = sys.stderr)
	print(f"{views=}", file=sys.stderr)
	# the node to be added to shard ID is new view
	new_view = req['socket-address']
	if ID in shards and new_view in views:
		print("line 266", file = sys.stderr)
		shards[ID][0].append(new_view)
		views[new_view][1] = ID
		# the new node gets all the data
		if socketAddress == new_view:
			currShard = ID 
			#grab datastore from someone in same shard
			for node in shards[ID][0]:
				if node != socketAddress:
					try:
						res = requests.get(url=f"http://{node}/shard/getDataStore")
						r = res.json()
						dataStore = r['data-store']
						print(f"datastore was updated by {node} to be {dataStore}", file=sys.stderr)
						break
					except:
						print(f"failed to grab datastore from {node}", file=sys.stderr)
						continue
			print(f"set {currShard=} to {ID}", file=sys.stderr)
		# this means it was client that sent so we need to broadcast
		if 'sender' not in req: 
			print('this is a PUT add-member from client', file=sys.stderr)
			viewsToDelete = []
			for view in views:
				if view != socketAddress:
					try: 
						print(f"sending put to {view} with sender as {socketAddress}", file=sys.stderr)
						res = requests.put(url=f"http://{view}/shard/add-member/{ID}", json={'socket-address': new_view, 'sender': socketAddress})
					except:
						print(f"found out {view} is down in line 392", file=sys.stderr)
						viewsToDelete.append(view)
						continue
			deleteViews(viewsToDelete)
			print("broadcasted shard member add", file=sys.stderr)
		return Response(response=json.dumps({"result": "node added to shard"}), status=200, content_type="application/json")
	print("line 270", file = sys.stderr)
	return Response(response=json.dumps({"error": "Shard ID does not exist"}), status=404, content_type="application/json") 

# TODO: come back to
@app.route('/shard/reshard', methods = ['PUT'])
def reshard():
	global views
	global dataStore
	global currShard
	global shards
	global shardCount
	global HASH_SIZE
	req = request.json
	if (type(req) != dict):
		req = json.loads(req)
	# req is a dict
	if len(views) / req['shard-count'] < 2:
		return Response(response=json.dumps({"error": "Not enough nodes to provide fault tolerance with requested shard count"}), status=400, content_type="application/json")
	shardCount = req['shard-count']

	# broadcast reshard to everyone
	if 'sender' not in req:
		for view in views:
			if view != socketAddress:
				try:
					res = requests.put(url=f"http://{view}/shard/reshard", json=json.dumps({'shard-count': shardCount, 'sender': True}))
				except:
					print("failed sending reshard", file=sys.stderr)
	#set up ranges with new shard count
	lenOfRange = HASH_SIZE // shardCount
	counter = 0
	shards.clear() # clear all the shards
	for s in range(shardCount):
		if counter+lenOfRange > HASH_SIZE:
			shards[f"s{s+1}"] = [[], int(counter), HASH_SIZE-1]
		else:
			shards[f"s{s+1}"] = [[], int(counter), int(counter+lenOfRange)]
		counter += lenOfRange + 1
	print(f"{shards=}", file=sys.stderr)
	print('round robin starting', file=sys.stderr)
	# we now distribute all the nodes to shards
	roundRobin(list(views.keys()))

	# make everyone have the same data across shards 
	# even if incorrect
	for node in shards[currShard][0]:
		# get everyone's data
		try:
			res = requests.get(url=f"http://{node}/shard/getDataStore")
			r = res.json()
			dataStore.update(r['data-store'])
		except:
			print("getting datastore failed", file=sys.stderr)
	# once we get all the data, we check if it should be with us
	to_delete = set()
	print(f"{dataStore=}", file=sys.stderr)
	for key in dataStore:
		keyHash = hash(key) % HASH_SIZE
		for shard in shards:
			print(f"shard {shard} range: {shards[shard][1]-shards[shard][2]}", file=sys.stderr)
			print(f"{keyHash=}", sys.stderr)
			if keyHash >= shards[shard][1] and keyHash <= shards[shard][2]:
				if shard != currShard:
					for node in shards[shard][0]:
						try:
							res = requests.put(url=f"http://{node}/kvs/{key}", json={'value': dataStore[key], 'internal': True})
							to_delete.add(key)
							print(f"added {key}", file=sys.stderr)
							break
						except:
							print(f"failed sending data to {shard}", file=sys.stderr)
					break
		
		
	for key in to_delete:
		del dataStore[key]
	print(f"{dataStore = } {shards = }", file=sys.stderr)
	return Response(response=json.dumps({"result": "resharded"}), status=200, content_type="application/json")


@app.route('/shard/getShards', methods=['GET'])
def getShards():
	global shards
	print(f"getShards(): {shards}")
	return Response(response=json.dumps({"shards": shards}), status=200, content_type="application/json")

@app.route('/shard/getDataStore', methods=['GET'])
def getDataStore():
	global dataStore
	print(f"getDataStore()")
	return Response(response=json.dumps({"data-store": dataStore}), status=200, content_type="application/json")

@app.route('/causal', methods=['PUT'])
def updateCausal():
	global views
	req = request.json
	if type(req) != dict:
		req = json.loads(req)
	# now req is type dict
	views = req['new-causal-metadata']
	return Response(response=json.dumps({"status": "OK"}), status=200, content_type="application/json")

@app.route('/kvs/<key>', methods = ['GET', 'PUT', 'DELETE'])
def kvs(key):
	global dataStore
	global shards
	global views
	global socketAddress
	# GET
	if (request.method == 'GET'):
		# check if this key belongs to us
		keyHash = hash(key) % HASH_SIZE
		for shard in shards:
			if keyHash >= shards[shard][1] and keyHash <= shards[shard][2]:
				# this shard is equipped to handle it
				if shard == currShard:
					break
				else:
					print("line 465 - false", file=sys.stderr)
					viewsToDelete = []
					# loop through all the nodes in the shard
					for otherNode in shards[shard][0]:
						print("line 330", file=sys.stderr)
						try:
							print("line 338", file=sys.stderr)
							res = requests.get(url=f"http://{otherNode}/kvs/{key}", json=request.json)
							while res.status_code == 503:
								time.sleep(1)
								res = requests.get(url=f"http://{otherNode}/kvs/{key}", json=request.json)
							break
						except:
							print(f"found out {view} is down on line 434", file=sys.stderr)
							viewsToDelete.append(otherNode)
					deleteViews(viewsToDelete)
					print("line 347", file=sys.stderr)
					# returns what the appropiate node said to return
					return Response(response=json.dumps(res.json()), status=res.status_code, content_type="application/json")
		# key exists in this shard
		# we have to first check that the causal dependencies are accurate
		print("line 351", file=sys.stderr)
		if type(request.json) != dict:
			req = json.loads(request.json)
		else:
			req = request.json
		# req is always a dict
		#if local < meta: fail
		print("line 358", file=sys.stderr)
		for view in views:
			if view in req['causal-metadata']:
				if views[view][0] < req['causal-metadata'][view][0]:
					res = json.dumps({'error': 'Causal dependencies not satisfied; try again later'})
					print("line 354", file=sys.stderr)
					return Response(response=res, status=503, content_type='application/json')
		if key in dataStore:
			# we need to include the causal metadata which is just the views dictionary
			print("line 367", file=sys.stderr)
			res = json.dumps({'result': 'found', 'value': dataStore[key], 'causal-metadata': req['causal-metadata']})
			return Response(response=res, status=200, content_type="application/json")
		res = Response(response=json.dumps({"error": "Key does not exist"}), status=404, content_type="application/json")
		print("line 362", file=sys.stderr)
		return res

	# PUT
	elif (request.method == 'PUT'):
		if type(request.json) != dict:
			req = json.loads(request.json)
		else:
			req = request.json
		if 'internal' in req:
			dataStore[key] = req['value']
			response = Response(response=json.dumps({"result": "created"}), status=201, content_type="application/json")
			return response
		# check if key is in this shard
		print("in PUT", file=sys.stderr)
		keyHash = hash(key) % HASH_SIZE
		for shard in shards:
			if keyHash >= shards[shard][1] and keyHash <= shards[shard][2]:
				# this shard is equipped to handle it
				if shard == currShard:
					break
				# find the node responsible for this
				else:
					print("line 465 - false", file=sys.stderr)
					viewsToDelete = []
					# loop through all the nodes in the shard
					for otherNode in shards[shard][0]:
						print("line 330", file=sys.stderr)
						try:
							print("line 338", file=sys.stderr)
							res = requests.put(url=f"http://{otherNode}/kvs/{key}", json=request.json)
							while res.status_code == 503:
								time.sleep(1)
								res = requests.put(url=f"http://{otherNode}/kvs/{key}", json=request.json)
							break
						except:
							print(f"found out {otherNode} is down on line 434", file=sys.stderr)
							viewsToDelete.append(otherNode)
					deleteViews(viewsToDelete)
					print("line 534", file=sys.stderr)
					# returns what the appropiate node said to return
					return Response(response=json.dumps(res.json()), status=res.status_code, content_type="application/json")
				
		# the key should be added in this shard
		
		# req is always a dictionary
		status, sender = satisfyCausalDependency(req)
		if not status:
			print("line 409", file=sys.stderr)
			res = json.dumps({'error': 'Causal dependencies not satisfied; try again later'})
			return Response(response=res, status=503, content_type='application/json')
		# json or value is not given to us
		if not req or "value" not in req:
			print("line 414", file=sys.stderr)
			response = Response(response=json.dumps({"error": "PUT request does not specify a value"}), status=400, content_type="application/json")
			return response
		# key length is greater than 50, reject
		if len(key) > 50:
			print("line 419", file=sys.stderr)
			response = Response(response=json.dumps({"error": "Key is too long"}), status=400, content_type="application/json")
			return response
		# increment current causal metadata for current vector clock
		# if we don't know who the sender is, client is the sender
		if not sender:
			views[socketAddress][0] += 1
		value = req['value']
		# given new VC data, update our own VC data
		if req['causal-metadata']:
			updateVC(req['causal-metadata'])
		# create new key
		if key not in dataStore:
			dataStore[key] = value
			# if we know the sender we don't want to broadcast
			# if we know that there is a sender, we don't need to broadcast
			if not sender:
				# send this PUT request to everyone else (except ourselves and sender)
				viewsToDelete = []
				for view in views:
					# make sure don't send to self
					# make sure don't send to sender
					if view != socketAddress and view != sender:
						# if you are sending to a node in same shard, include value and send to
						# /kvs
						if views[view][1] == currShard:
							try:
								print("line 446", file=sys.stderr)
								res = requests.put(url=f"http://{view}/kvs/{key}", json={'value': value, 'causal-metadata': json.dumps(views)})
								while res.status_code == 503:
									time.sleep(1)
									res = requests.put(url=f"http://{view}/kvs/{key}", json={'value': value, 'causal-metadata': json.dumps(views)})
							except:
								# add views to be deleted (and moved to downed)
								print(f"found out {view} is down on line 562", file=sys.stderr)
								viewsToDelete.append(view)
								continue
						# if you are sending updated causal metadata, send views to /causal
						else:
							try:
								print("line 458", file=sys.stderr)
								res = requests.put(url=f"http://{view}/causal", json=json.dumps({'new-causal-metadata': views}))
								while res.status_code == 503:
									time.sleep(1)
									res = requests.put(url=f"http://{view}/causal", json=json.dumps({'new-causal-metadata': views}))
							except:
								print(f"found out {view} is down on line 573", file=sys.stderr)
								viewsToDelete.append(view)
								continue
				# delete views that are unresponsive (moved to downed)
				deleteViews(viewsToDelete)
			print("line 468", file=sys.stderr)
			response = Response(response=json.dumps({"result": "created", "causal-metadata": views}), status=201, content_type="application/json")
			return response
		# update existing key
		else:
			dataStore[key] = value
			# if we know the sender we don't want to broadcast
			# if we know that there is a sender, we don't want to broadcast
			if not sender:
				# send this PUT request to everyone else (except ourselves and sender)
				viewsToDelete = []
				for view in views:
					if view != socketAddress and view != sender:
						if views[view][1] == currShard:
							try:
								print("line 483", file=sys.stderr)
								res = requests.put(url=f"http://{view}/kvs/{key}", json={'value': value, 'causal-metadata': json.dumps(views)})
								while res.status_code == 503:
									time.sleep(1)
									res = requests.put(url=f"http://{view}/kvs/{key}", json={'value': value, 'causal-metadata': json.dumps(views)})
							except:
								# add views to be deleted (and moved to downed)
								print(f"found out {view} is down on line 600", file=sys.stderr)
								viewsToDelete.append(view)
								continue
						else: 
							try:
								print("line 494", file=sys.stderr)
								res = requests.put(url=f"http://{view}/causal", json=json.dumps({'new-causal-metadata': views}))
								while res.status_code == 503:
									time.sleep(1)
									res = requests.put(url=f"http://{view}/causal", json=json.dumps({'new-causal-metadata': views}))
							except:
								print(f"found out {view} is down on line 611", file=sys.stderr)
								viewsToDelete.append(view)
								continue
				# delete views that are unresponsive (moved to downed)
				deleteViews(viewsToDelete)
			response = Response(response=json.dumps({"result": "replaced", "causal-metadata": views}), status=200, content_type="application/json")
			return response
		
	# DELETE
	elif (request.method == 'DELETE'):
		# check if key is in this shard
		keyHash = hash(key) % HASH_SIZE
		for shard in shards:
			if keyHash >= shards[shard][1] and keyHash <= shards[shard][2]:
				# this shard is equipped to handle it
				if shard == currShard:
					break
				# find someone who can handle this
				else:
					print("line 660 - false", file=sys.stderr)
					viewsToDelete = []
					# loop through all the nodes in the shard
					for otherNode in shards[shard][0]:
						print("line 330", file=sys.stderr)
						try:
							print("line 338", file=sys.stderr)
							res = requests.delete(url=f"http://{otherNode}/kvs/{key}", json=request.json)
							while res.status_code == 503:
								time.sleep(1)
								res = requests.delete(url=f"http://{otherNode}/kvs/{key}", json=request.json)
							break
						except:
							print(f"found out {view} is down on line 434", file=sys.stderr)
							viewsToDelete.append(otherNode)
					deleteViews(viewsToDelete)
					print("line 347", file=sys.stderr)
					# returns what the appropiate node said to return
					return Response(response=json.dumps(res.json()), status=res.status_code, content_type="application/json")
		# key is in here to delete
		if type(request.json) != dict:
			req = json.loads(request.json)
		else:
			req = request.json
		# req is always a dict
		status, sender = satisfyCausalDependency(req)
		if not status:
			print("line 548", file=sys.stderr)
			res = json.dumps({'error': 'Causal dependencies not satisfied; try again later'})
			return Response(response=res, status=503, content_type='application/json')
		if key in dataStore:
			del dataStore[key]
			# if there is a sender, we don't want to broadcast
			# if we know that there is a sender, we don't need to broadcast
			if not sender:
				views[socketAddress][0] += 1
				viewsToDelete = []
				for view in views:
					if views[view][1] == currShard:
						try: 
							if view != socketAddress and view != sender:
								res = requests.delete(url=f"http://{view}/kvs/{key}", json={'causal-metadata': json.dumps(views)})
								while res.status_code == 503:
									time.sleep(1)
									res = requests.delete(url=f"http://{view}/kvs/{key}", json={'causal-metadata': json.dumps(views)})
						except:
							# add views to be deleted (and moved to downed)
							print(f"found out {view} is down on line 683", file=sys.stderr)
							viewsToDelete.append(view)
							continue
					else:
						try:
							res = requests.put(url=f"http://{view}/causal", json=json.dumps({'new-causal-metadata': views}))
							while res.status_code == 503:
								time.sleep(1)
								res = requests.put(url=f"http://{view}/causal", json=json.dumps({'new-causal-metadata': views}))
						except:
							print(f"found out {view} is down on line 693", file=sys.stderr)
							viewsToDelete.append(view)
							continue
				# delete views that are unresponsive (moved to downed)
				deleteViews(viewsToDelete)
			print("line 581", file=sys.stderr)
			res = Response(response=json.dumps({"result": "deleted", "causal-metadata": views}), status=200, content_type="application/json")
			return res
		# Out of fear, I don't want to delete this
		# But I also have absolutely no idea what this does
		# Or what it is for
		updateVC(req['causal-metadata'])
		curr = views[socketAddress][0]
		for view in views:
			if views[view][0] != curr:
				return Response(response=json.dumps({"error": "Key does not exist"}), status=404, content_type="application/json")
		return



if __name__ == "__main__":
	print("in main", file=sys.stderr)

	app.run(host='0.0.0.0', port=8090)
