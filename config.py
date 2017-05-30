# URLs for getting/posting data from/to feature services
PLANT_MAINTENANCE_URL = "http://gardens.green-wood.com:6080/arcgis/rest/services/OperationalLayers/PlantCenter/FeatureServer/2"
PLANT_CENTER_URL = "http://gardens.green-wood.com:6080/arcgis/rest/services/OperationalLayers/PlantCenter/FeatureServer/0"
ASSIGNMENTS_URL = "https://services2.arcgis.com/gqwmVcOGxkspxBLa/ArcGIS/rest/services/assignments_c6e017a7b466487788d6ec51ce6609d7/FeatureServer/0"

# queries for getting/posting data from/to feature services
PLANT_MAINTENANCE_QUERY = {
	'where': "MaintenanceRecordType = 2 AND CreationDate > date '{}' AND CreationDate <= date '{}'", 
	'f': 'json', 
	'returnGeometry': False, 
	'outFields': 'OBJECTID,FeatureID,CreationDate,PlantMaintenanceType,MaintenancePriority,MaintainanceDueDate,WorkOrderDescription'
	}
PLANT_CENTER_QUERY = {
	'where': "GlobalID = '{}'", 
	'returnGeometry': True,
	'outFields': 'PlantCenterID',
	'f': 'json'
	}
ATTACHMENTS_QUERY = {
	'f': 'json', 
	'layers': [2],
	'layerQueries': {
		'2': {
			'where': "MaintenanceRecordType = 2 AND CreationDate > date '{}' AND CreationDate <= date '{}'",
			'includeRelated': 'false'
			}
		},
	'geometry': '0,0',
	'geometryType': 'esriGeometryPoint',
	'returnAttachments': 'true'
	}
ASSIGNMENTS_POST = {
	'f': 'json', 
	'features': '{}'
	}
ASSIGNMENTS_QUERY = {
	'where': "CreationDate > date '{}' AND CreationDate <= date '{}'",
	'outFields': 'priority,location,dueDate',
	'returnGeometry': False,
	'f': 'json'
}

# email templates
EMAIL_FROM = 'workforce@green-wood.com'
EMAIL_TO = 'fwest@blueraster.com'
EMAIL_SUBJECT = 'Collector to Workforce Update'
EMAIL_TEMPLATE_URGENT = '{} High or Critical priority assignments were created in the past hour.\n'
EMAIL_TEMPLATE_DIGEST = '{} assignments total were created today.\n'
EMAIL_TEMPLATE_ERROR = 'Could not upload assignments.\n'
EMAIL_TEMPLATE_LIST = '\tPlant: {PlantID}\n\t\t{Priority} priority\n\t\tDue {DueDate}'