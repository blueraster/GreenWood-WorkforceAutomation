import arcpy
import json
import smtplib
from email.mime.text import MIMEText
import urllib.request, urllib.parse, requests
from datetime import datetime, timedelta
import pytz
import logging
from config import PLANT_MAINTENANCE_URL, PLANT_CENTER_URL, ASSIGNMENTS_URL
from config import PLANT_MAINTENANCE_QUERY, PLANT_CENTER_QUERY, ASSIGNMENTS_POST, ASSIGNMENTS_QUERY
from config import EMAIL_FROM, EMAIL_TO, EMAIL_SUBJECT, EMAIL_TEMPLATE_URGENT, EMAIL_TEMPLATE_DIGEST, EMAIL_TEMPLATE_ERROR, EMAIL_TEMPLATE_LIST


URGENT_ASSIGNMENTS_PRESENT = False

def utc2eastern(timestamp):
	if not timestamp:
		return None
	dt = datetime.fromtimestamp(float(timestamp)/1000)
	eastern = pytz.timezone('US/Eastern')
	dt_local = dt.replace(tzinfo=pytz.utc).astimezone(eastern)
	zero_local = datetime.fromtimestamp(0)
	timestamp_local = (dt_local - zero_local).total_seconds()*1000
	return timestamp_local

def getTimeRange(delta):
	now = datetime.now()
	nearestHour = now - timedelta(minutes=now.minute, seconds=now.second, microseconds=now.microsecond)
	endTime = nearestHour.strftime('%Y-%m-%d %H:%M:%S')
	startTime = (nearestHour - timedelta(hours=delta)).strftime('%Y-%m-%d %H:%M:%S')
	# return [startTime, endTime]
	return [datetime.fromtimestamp(0).strftime('%Y-%m-%d %H:%M:%S'), endTime]

def uploadAttachments(base_from, base_to):
	# temporary folder for saving attachments locally
	tempdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp')
	if not os.path.exists(tempdir): os.mkdir(tempdir)

	# get information about attachments
	url_info = base_from + '?' + urllib.parse.urlencode({'f':'json'})
	attachment_info = json.dumps(urlopen(url_info).read().decode('utf-8'))['attachmentInfos']

	images = []
	for info in attachment_info:

		# get info about image
		img_id = info['id']
		img_name = info['name']
		img_type = info[0]['contentType']

		# request attachment file
		url_from = base_from + r'/{}/{}'.format(str(img_id), img_name)
		response = urllib.request.urlopen(url_from)

		# save file locally
		tempfile = os.path.join(tempdir, img_name)
		with open(tempfile, 'wb') as f:
			f.write(response.read())

		# upload file to assignment
		url_to = base_to + '/addAttachment'
		with open(tempfile, 'rb') as f:
			response = requests.post(addurl, files={'attachment': (img_name, f, img_type)})
			if not response.status_code == requests.codes.ok:
				logging.info('Unable to upload attachment {}'.format(img_name))

	return 

def defineAssignment(assignmentType=None, description=None, priority=None, dueDate=None, 
						plantID=None, workOrderId=None, x=0, y=0):
	assignment = {
		'attributes': {
			'status': 0,
			'assignmentType': assignmentType,
			'assignmentRead': 0,
			'location': plantID,
			'dispatcherId': None,
			'description': description,
			'priority': priority,
			'dueDate': dueDate,
			'workOrderId': workOrderId
			},
		'geometry': {'x': x, 'y': y}
		}

	return assignment

def getURL(base, queryDict, params):
	query = {key: value for key, value in queryDict.items()}
	for key, vals in params.items():
		query[key] = query[key].format(*vals)
	# logging.info(query)
	return base + urllib.parse.urlencode(query)

def validateAssignments(assignments):
	return True

def addAssignments(assignments):
	url = getURL(ASSIGNMENTS_URL + '/addFeatures?', ASSIGNMENTS_POST, {'features': [json.dumps(assignments)]})
	response = urllib.request.urlopen(url)
	# request = urllib2.Request(*url.split('?'))
	# response = urllib2.urlopen(request)
	return json.loads(response.read())

def sendEmail(text):
	# create message
	msg = MIMEText(text)
	msg['Subject'] = EMAIL_SUBJECT
	msg['From'] = EMAIL_FROM
	msg['To'] = EMAIL_TO

	# send email via SMTP server
	s = smtplib.SMTP('localhost')
	try:
		s.sendmail(EMAIL_FROM, [EMAIL_TO], msg.as_string())
	except SMTPException:
		logging.error('Unable to send mail')
	finally:
		s.quit()


def main():
	# record set containing maintenance records from past full hour
	logging.info('Getting data from feature service...')
	rsURL = getURL(PLANT_MAINTENANCE_URL + '/query?', PLANT_MAINTENANCE_QUERY, {'where': getTimeRange(1)})
	rs = arcpy.RecordSet()
	logging.info('Feature service url: {}'.format(rsURL))
	rs.load(rsURL)

	# reorganize records into list of field dicts
	records = [record['attributes'] for record in json.loads(rs.JSON)['features']]
	logging.info('Found {} records'.format(len(records)))

	# define new assignments
	if len(records) > 0: logging.info('Defining new workforce assignments...')
	assignments = []
	for i, record in enumerate(records):
		logging.info('{}/{} Processing record {}'.format(i+1, len(records), record['FeatureID']))

		# get the plant feature related to this work order
		fsURL = getURL(PLANT_CENTER_URL + '/query?', PLANT_CENTER_QUERY, {'where': [record['FeatureID']]})
		fs = arcpy.FeatureSet()
		fs.load(fsURL)
		geom = json.loads(fs.JSON)['features'][0]['geometry']
		plantID = json.loads(fs.JSON)['features'][0]['attributes']['PlantCenterID']
		# desc = 'PlantCenterID: {}. '.format(json.loads(fs.JSON)['features'][0]['attributes']['PlantCenterID'])
		# if record['WorkOrderDescription']: desc += record['WorkOrderDescription']

		logging.info(record['MaintainanceDueDate'])
		logging.info(utc2eastern(record['MaintainanceDueDate']))

		# define assignment
		assignments.append(defineAssignment(assignmentType=record['PlantMaintenanceType'],
											priority=record['MaintenancePriority'],
											dueDate=utc2eastern(record['MaintainanceDueDate']),
											description=record['WorkOrderDescription'],
											plantID=plantID,
											x=geom['x'],
											y=geom['y']))

		if record['MaintenancePriority'] in ['High', 'Critical']:
			URGENT_ASSIGNMENTS_PRESENT = True

	return

	# add new assignments
	if assignments:
		logging.info('Validating assignments...')
		if validateAssignments(assignments):
			logging.info('Uploading assignments...')
			response = addAssignments(assignments)
			# logging.info(response)
			return
			if 'error' in response.keys():
				logging.warning(response['error']['message'])
				for detail in response['error']['details']:
					logging.warning(detail)
				sendEmail('Could not upload assignments:\n' + '\n'.join([detail for detail in response['error']['details']]))
			else:
				# add attachments
				logging.info('Adding attachments...')
				for record in records:
					url_from = PLANT_MAINTENANCE_URL + '/' + record['OBJECTID'] + '/attachments'
					uploadAttachments(url_from, ASSIGNMENTS_URL, '')


				logging.info('Finished uploading assignments')

				# send email about urgent assignments if present
				if URGENT_ASSIGNMENTS_PRESENT:
					logging.info('Sending urgent assignment alert')
					email_text = EMAIL_TEMPLATE_URGENT.format(len(assignments)) + 
									'\n'.join([EMAIL_TEMPLATE_LIST.format(a['attributes']['location'], a['attributes']['priority'],
																			a['attributes']['dueDate']) for a in assignments])
					sendEmail(email_text)

				# if it's the end of the day, send daily digest
				if datetime.now().hour == 17:
					logging.info('Sending daily digest')

					# get information about assignments uploaded in last 24 hours
					fsURL = getURL(ASSIGNMENTS_URL + '/query?', ASSIGNMENTS_QUERY, {'where': getTimeRange(24)})
					fs = arcpy.FeatureSet()
					fs.load(fsURL)
					records = [record['attributes'] for record in json.loads(fs.JSON)['features']]
					logging.info('Found {} records'.format(len(records)))

					email_text = EMAIL_TEMPLATE_DIGEST.format(len(records)) + 
									'\n'.join([EMAIL_TEMPLATE_LIST.format(r['location'], r['priority'], r['dueDate']) for r in records])
					sendEmail(email_text)

		else:
			logging.warning('Invalid assignment detected')
	else:
		logging.info('No assignments to upload')


if __name__ == '__main__':
	logging.basicConfig(filename='UploadWorkOrder.log', level=logging.DEBUG)
	logging.info('New session started at {}'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

	main()

