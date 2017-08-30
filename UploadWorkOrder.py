import os
import logging

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import arcpy
try:
	import json
	import smtplib
	from email.mime.text import MIMEText
	from email.mime.multipart import MIMEMultipart
	from urllib import request, parse
	import requests
	from datetime import datetime, timedelta
	import pytz
	from config import MAINTENANCE_URL, FEATURES_URL, ASSIGNMENTS_URL, TOKEN_URL
	from config import PORTAL_USERNAME, PORTAL_PASSWORD
	from config import MAINTENANCE_QUERY, FEATURES_QUERY, ASSIGNMENTS_POST, ASSIGNMENTS_QUERY
	from config import TYPE_FIELD, DUEDATE_FIELD, IDENTIFIER_FIELD
	from config import EMAIL_FROM, EMAIL_TO, EMAIL_SUBJECT, EMAIL_TEMPLATE_URGENT, EMAIL_TEMPLATE_DIGEST, EMAIL_TEMPLATE_ERROR, EMAIL_TEMPLATE_LIST
	from config import PRIORITY_PAIRS, ASSIGNMENT_TYPE_PAIRS
except Exception as e:
	print(e)

TOKEN = None

URGENT_ASSIGNMENTS_PRESENT = False

priorityLookup = {}
for (code, text) in PRIORITY_PAIRS:
	priorityLookup[code] = text if text else 'N/A'
	priorityLookup[text] = code

assignmentTypeLookup = {}
for (code, text) in ASSIGNMENT_TYPE_PAIRS:
	assignmentTypeLookup[code] = text if text else 'N/A'
	assignmentTypeLookup[text] = code


def timestamp2ET(ts):
	return datetime.utcfromtimestamp(float(ts)/1000).replace(tzinfo=pytz.utc).astimezone(pytz.timezone('US/Eastern')).strftime('%#I:%M %p, %#m/%#d/%Y')

def getTimeRange(delta):
	now = datetime.utcnow()
	nearestHour = now - timedelta(minutes=now.minute%15, seconds=now.second, microseconds=now.microsecond)
	endTime = nearestHour.strftime('%Y-%m-%d %H:%M:%S')
	startTime = (nearestHour - timedelta(minutes=(int(60*delta)))).strftime('%Y-%m-%d %H:%M:%S')
	logging.debug('end UTC time: {}, start UTC time: {}'.format(endTime, startTime))
	return [startTime]

def getPortalToken(tokenUrl, username, password):
	params = {'username': username,
			  'password': password,
			  'client': 'referer',
			  'referer': tokenUrl,
			  'expiration': 60,
			  'f': 'json'}
	response = requests.post(tokenUrl + '/sharing/rest/generateToken?', data=params)
	response_json = json.loads(response.text)
	if not 'token' in response_json.keys():
		logging.debug(response_json)
		raise Exception
	logging.debug(response_json)
	logging.debug(response_json['token'])
	return response_json['token']

def uploadAttachments(base_from, base_to):
	# temporary folder for saving attachments locally
	tempdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp')
	if not os.path.exists(tempdir): os.mkdir(tempdir)

	# get information about attachments
	url_info = base_from + '?' + parse.urlencode({'f':'json', 'token': TOKEN})
	attachment_info = json.loads(request.urlopen(url_info).read().decode('utf-8'))['attachmentInfos']

	images = []
	for info in attachment_info:

		# get info about image
		img_id = info['id']
		img_name = info['name']
		img_type = info['contentType']

		# logging
		logging.info('Transferring attachment {}'.format(img_name))

		# request attachment file
		url_from = base_from + r'/{}/{}'.format(str(img_id), img_name) + '?' + parse.urlencode({'token': TOKEN})
		response = request.urlopen(url_from)

		# save file locally
		tempfile = os.path.join(tempdir, img_name)
		with open(tempfile, 'wb') as f:
			f.write(response.read())

		# upload file to assignment
		url_to = base_to + '/addAttachment'
		with open(tempfile, 'rb') as f:
			logging.debug(tempfile)
			logging.debug(url_to)
			response = requests.post(url_to, {'f': 'json', 'token': TOKEN}, files={'attachment': (img_name, f, img_type)})
			try:
				response_js = json.loads(response.text)
				logging.debug(response_js)
			except Exception as e:
				logging.debug(e)
				logging.debug(response.text)
			print(response)

		# delete temporary attachment file
		# if os.path.exists(tempfile): os.remove(tempfile)


	return 

def defineAssignment(assignmentType=0, description='', priority=0, dueDate=0, 
						location='', workOrderId='', x=0, y=0):
	logging.debug('Assignment type in defineAssignment(): {}'.format(assignmentType))
	assignment = {
		'attributes': {
			'status': 0,
			'assignmenttype': assignmentType,
			'assignmentread': 0,
			'location': location,
			'dispatcherid': 0
			},
		'geometry': {'x': x, 'y': y}
		}

	# optional attributes:
	if description:
		assignment['attributes']['description'] = description
	if priority:
		assignment['attributes']['priority'] = priority
	if dueDate:
		assignment['attributes']['duedate'] = dueDate
	if workOrderId:
		assignment['attributes']['workorderid'] = workOrderId

	return assignment

def getURL(base, queryDict, params):
	query = {key: value for key, value in queryDict.items()}
	for key, vals in params.items():
		query[key] = query[key].format(*vals)
	logging.debug(query)
	return base + parse.urlencode(query)

def validateAssignment(assignment):
	response = {'success': True, 'errors': []}
	requiredFields = set(['status', 'assignmenttype', 'location', 'assignmentread', 'dispatcherid'])
	allFields = requiredFields.union(set(['description', 'priority', 'workorderid', 'duedate', 'workerid', 'assigneddate']))
	geomFields = set(['x', 'y'])

	# check attribute fields
	if not requiredFields.issubset(assignment['attributes'].keys()):
		response['errors'].append('Assignment does not have all required attribute fields')
	if (set(assignment['attributes'].keys()) - allFields):
		response['errors'].append('Assignment has invalid attribute fields')

	# check geometry fields
	if not geomFields.issubset(assignment['geometry'].keys()):
		response['errors'].append('Assignment does not have x and y coordinates')
	if (set(assignment['geometry'].keys()) - geomFields):
		response['errors'].append('Assignment has invalid geometry fields')

	if len(response['errors']) > 0: response['success'] = False

	return response

def addAssignments(assignments):
	url = getURL(ASSIGNMENTS_URL + '/addFeatures?', ASSIGNMENTS_POST, {'features': [assignments], 'token': [TOKEN]})
	try:
		resource = request.urlopen(url.split('?')[0], url.split('?')[1].encode('utf-8'))
		response = json.loads(resource.read().decode('utf-8'))
	except Exception as e:
		logging.error('Could not upload assignments. Exiting.')
		logging.error(e)
		logging.error('Feature upload url: {}'.format(url))
		exit(2)
	return response

def getEmailTemplateList(template_list, feats):
	email_template_list = []
	for f in feats:
		email_template_list.append(template_list[0].format(f['location']))
		if 'assignmenttype' in f.keys(): email_template_list[-1] += template_list[1].format(assignmentTypeLookup[f['assignmenttype']])
		if 'description' in f.keys(): email_template_list[-1] += template_list[2].format(f['description'])
		if 'priority' in f.keys(): email_template_list[-1] += template_list[3].format(priorityLookup[f['priority']])
		if 'duedate' in f.keys(): email_template_list[-1] += template_list[4].format(timestamp2ET(f['duedate']))
	return email_template_list

def sendEmail(text):
	# create message
	# msg = MIMEText(text)
	msg = MIMEMultipart()
	msg['Subject'] = EMAIL_SUBJECT
	msg['From'] = EMAIL_FROM
	msg['To'] = ', '.join(EMAIL_TO)
	msg.attach(MIMEText(text, ('plain')))

	# send email via SMTP server
	s = smtplib.SMTP('localhost')
	try:
		# s.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
		s.send_message(msg)
	except SMTPException:
		logging.error('Unable to send mail')
	finally:
		s.quit()


def main():
	global URGENT_ASSIGNMENTS_PRESENT

	# generate TOKEN
	global TOKEN
	TOKEN = getPortalToken(TOKEN_URL, PORTAL_USERNAME, PORTAL_PASSWORD)
	logging.debug(TOKEN)

	# record set containing maintenance records from past full hour
	logging.info('Getting data from feature service...')
	rsURL = getURL(MAINTENANCE_URL + '/query?', MAINTENANCE_QUERY, {'where': getTimeRange(0.25), 'token': [TOKEN]})
	rs = arcpy.RecordSet()
	logging.debug('Maintenance record feature service url: {}'.format(rsURL))
	rs.load(rsURL)

	# reorganize records into list of field dicts
	records = [record['attributes'] for record in json.loads(rs.JSON)['features']]
	logging.info('Found {} records'.format(len(records)))

	# define new assignments
	if len(records) > 0: logging.info('Defining new workforce assignments...')
	assignments = []
	for i, record in enumerate(records):
		logging.info('{}/{} Processing record {}'.format(i+1, len(records), record['FeatureID']))

		# get the feature related to this work order
		fsURL = getURL(FEATURES_URL + '/query?', FEATURES_QUERY, {'where': [record['FeatureID']], 'token': [TOKEN]})
		fs = arcpy.FeatureSet()
		fs.load(fsURL)
		logging.debug('Plant feature service url: {}'.format(fsURL))
		fs_json = json.loads(fs.JSON)

		# geometry of feature (find centroid if not a point)
		geom = fs_json['features'][0]['geometry']
		if fs_json['geometryType'] == 'esriGeometryPoint':
			x = geom['x']
			y = geom['y']
		else:
			if fs_json['geometryType'] == 'esriGeometryPolygon':
				X = [coords[0] for ring in geom['rings'] for coords in ring]
				Y = [coords[1] for ring in geom['rings'] for coords in ring]
			elif fs_json['geometryType'] == 'esriGeometryPolyline':
				X = [coords[0] for path in geom['paths'] for coords in path]
				Y = [coords[1] for path in geom['paths'] for coords in path]
			x = sum(X)/len(X)
			y = sum(Y)/len(Y)

		# ID of feature
		ID = json.loads(fs.JSON)['features'][0]['attributes'][IDENTIFIER_FIELD]

		# fill assignment parameters
		logging.debug('Assignment type from collector: {}'.format(record[TYPE_FIELD]))
		logging.debug('Intended assignment type from description: {}'.format(record['WorkOrderDescription']))
		try:
			params = {
				'assignmentType': assignmentTypeLookup[record[TYPE_FIELD]] if record[TYPE_FIELD] else 5,
				'location': ID if ID else '',
				'x': x,
				'y': y,
				'description': record['WorkOrderDescription'] if record['WorkOrderDescription'] else '',
				'priority': priorityLookup[record['MaintenancePriority']],
				'dueDate': record[DUEDATE_FIELD] if record[DUEDATE_FIELD] else 0
			}

			# define assignment
			assignment = defineAssignment(**params)
			validation = validateAssignment(assignment)
			if validation['success']:
				assignments.append(assignment)
			else:
				logging.error('Could not define assignment. ID: {}, maintenance record objectID: {}'.format(ID, record['OBJECTID']))
				for error in validation['errors']:
					logging.warning(error)
		except Exception as e:
			logging.error('Could not define assignment. ID: {}, maintenance record objectID: {}'.format(ID, record['OBJECTID']))
			logging.error(e)


		logging.debug('Assignment: {}'.format(assignments[-1]))

		# if any assignments are high or critical priority, will have to send extra email
		if record['MaintenancePriority'] in ['High', 'Critical']:
			logging.info('Work order is high or critical priority')
			URGENT_ASSIGNMENTS_PRESENT = True


	# add new assignments
	if assignments:
		logging.debug('All assignments: {}'.format(assignments))
		response = addAssignments(assignments)
		if 'error' in response.keys():
			logging.warning(response['error']['message'])
			for detail in response['error']['details']:
				logging.warning(detail)
			sendEmail('Could not upload assignments:\n' + '\n'.join([detail for detail in response['error']['details']]))
		else:
			logging.info('Response: {}'.format(response))

			# check for bad uploads / add attachments
			failedUploads = {}
			for (result, record) in zip(response['addResults'], records):
				if result['success'] == False:
					failedUploads[record['OBJECTID']] = result['error']
					logging.warning('Maintenance record {} could not be uploaded: {}'.format(record['OBJECTID'], result['error']['description']))
				else:
					logging.info('Looking for attachments in maintenance record {} to transfer to assignment {}'.format(record['OBJECTID'], result['objectId']))
					url_from = MAINTENANCE_URL + '/' + str(record['OBJECTID']) + '/attachments'
					url_to = ASSIGNMENTS_URL + '/' + str(result['objectId'])
					uploadAttachments(url_from, url_to)

			logging.info('Finished uploading assignments')

			# send email about bad uploads in present
			if failedUploads:
				sendEmail('The following assignments could not be uploaded: \n' + '\n'.join(['Object ID {}: {}'.format(key, failedUploads[key]) for key in failedUploads.keys()]))

			# send email about urgent assignments if present
			if URGENT_ASSIGNMENTS_PRESENT:
				logging.info('Sending urgent assignment alert')

				# filter assignments
				urgent_assignments = [a['attributes'] for a in assignments if 'priority' in a['attributes'].keys() and a['attributes']['priority'] > 2]

				# send email
				email_template_list = getEmailTemplateList(EMAIL_TEMPLATE_LIST, urgent_assignments)
				email_text = EMAIL_TEMPLATE_URGENT.format(len(urgent_assignments)) + '\n'.join(email_template_list)
				logging.info(email_text)
				sendEmail(email_text)
	else:
		logging.info('No assignments to upload')

	# if it's the end of the day, send daily digest
	if datetime.now().hour == 17 and datetime.now().minute < 15:
		logging.info('Sending daily digest')

		# get information about assignments uploaded in last 24 hours
		rsURL = getURL(ASSIGNMENTS_URL + '/query?', ASSIGNMENTS_QUERY, {'where': getTimeRange(24), 'token': [TOKEN]})
		logging.info('Daily digest url: {}'.format(rsURL))
		rs = arcpy.RecordSet()
		rs.load(rsURL)
		all_records = [{key:record['attributes'][key] for key in record['attributes'].keys() if not record['attributes'][key] is None} for record in json.loads(rs.JSON)['features']]
		logging.info('Found {} records'.format(len(all_records)))
		logging.info(all_records[-1])

		# send email
		email_template_list = getEmailTemplateList(EMAIL_TEMPLATE_LIST, all_records)
		email_text = EMAIL_TEMPLATE_DIGEST.format(len(all_records)) + '\n'.join(email_template_list)
		logging.info(email_text)
		sendEmail(email_text)



if __name__ == '__main__':
	# create file for logging information and errors
	logfilename = 'UploadWorkOrder_{}.log'.format(datetime.now().strftime('%Y-%m-%d'))
	logging.basicConfig(filename=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs', logfilename), level=logging.DEBUG)
	logging.info('###################################################################')
	logging.info('New session started at {}'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

	try:
		main()
	except Exception as e:
		logging.critical(e)