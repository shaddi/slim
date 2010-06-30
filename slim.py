''' 
slim.py: A schema-less, indexed, MySQL-based datastore inspired by FriendFeed [1].

Assumes that all values are stored in a homogenous table "entries" with
a format similar to the following:
 
 CREATE TABLE entities (
    added_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    id VARCHAR(36) NOT NULL,
    updated TIMESTAMP NOT NULL,
    body MEDIUMBLOB,
    UNIQUE KEY (id),
    KEY (updated)
 ) ENGINE=InnoDB;
 
The "body" field stores pickled, zlib-compressed, standard Python dictionaries with arbitrary contents.

Indexes to this table are stored in seperate tables with a schema like the below:

CREATE TABLE index_user_id (
    user_id VARCHAR(36) NOT NULL,
    entity_id VARCHAR(36) NOT NULL UNIQUE,
    PRIMARY KEY (user_id, entity_id)
) ENGINE=InnoDB;

In this example, the referenced entity would refer to a dictionary with a key "user_id".

[1]: http://bret.appspot.com/entry/how-friendfeed-uses-mysql

'''
import MySQLdb as db
import MySQLdb.cursors
import uuid
import zlib

try:
   import cPickle as pickle
except:
   import pickle


class Index:
	def __init__(self,table,properties):
		self.table = table
		self.properties = properties

	# returns entity or entities that match specific 
	def get_all(self,datastore, **item):
		key = str(item.keys()[0])
		value = item[key]
		c = datastore.conn.cursor()
		q = "SELECT `entity_id` FROM `%s` WHERE `%s`='%s'" % (self.table,key,value)
		c.execute(q)
		
		rows = c.fetchall()
		if len(rows) > 1:
			# get a list of all the referenced entitites
			entities = []
			for r in rows:
				entities.append(datastore.get(r["entity_id"]))
			return entities	
		elif len(rows) == 1:
			# return single entity
			return datastore.get(rows[0]["entity_id"])
		else:
			return None
	
	# always deletes first then adds
	def put(self,datastore, entity):
		c = datastore.conn.cursor()
		#print entity
		for key in entity:
			if key in self.properties:
				q = "DELETE FROM %s WHERE entity_id='%s'" % (self.table,entity["id"])
				c.execute(q)
				q = "INSERT INTO %s (%s,entity_id) VALUES('%s', '%s')" % (self.table,key,entity[key],entity["id"])
				c.execute(q)

	
# todo: implement sanitization
class DataStore:
	def __init__(self,indexes=[],host="localhost",user="default",passwd="default",db_name="default"):
		self.conn = db.connect(host,user,passwd,db_name,cursorclass=db.cursors.DictCursor)
		self.indexes=indexes
		self.conn.autocommit(True)
	
	def add_index(self,index):
		self.indexes.append(index)	
	
	# adds an entity to the datastore, updating if already existing
	def put(self,entity):
		c = self.conn.cursor()	
			
		# if we have an id already, delete existing record from db and proceed. 
		# if we do not, create an id and proceed with insert.
		if "id" in entity:
			q = "DELETE FROM entities WHERE id='%s'" % (entity["id"])
			c.execute(q)
		else:
			entity["id"] = str(uuid.uuid4())

		# insert record
		pickled = db.escape_string(zlib.compress(pickle.dumps(entity)))
		q = "INSERT INTO entities (id,body) VALUES('%s','%s')" % (entity["id"], pickled)
		c.execute(q)
		

		# check indexes to see if any entity properties need to be indexed
		for i in self.indexes:
			for p in i.properties:
				# add to each of the index tables w/ entity id
				if p in entity:
					i.put(self,entity)
					break
		
	def get(self,entity_id):
		c = self.conn.cursor()
		q = "SELECT body FROM entities WHERE id='%s'" % (entity_id)
		c.execute(q)

		try:
			entity = c.fetchone()["body"]
		except:
			print "error"
			return None
			
		return pickle.loads(zlib.decompress(entity))
		
