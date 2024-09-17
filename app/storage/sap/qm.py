# pylint: disable = C0301, C0302, R0913, W0718, W1203

"""Mediates operations performed in SAP QM01/QM02 Transactions."""

import time
from copy import deepcopy
from typing import Union
from ... import logger
from . import rfc, Account, Delivery, Invoice

g_log = logger.get_global_logger()

"""Claim processing pririties."""
_PRIORITY_UNUSED = ""                        # blank
_PRIORITY_MOL_PRIORITY_HANDLING = "1"        # MOL: Prio handling
_PRIORITY_MOL_ACCEPT_REFUSAL = "2"            # MOL: Accept.refusal
_PRIORITY_MOL_BELOW_THRESHOLD = "3"          # MOL: < Threshold
_PRIORITY_MOL_RETURN_CUST = "4"              # MOL: Return cust.
_PRIORITY_MOL_RECURR_CLAIM = "5"             # MOL: Recurr. claim
_PRIORITY_MOL_DELIVERY_DATE_DEVIATION = "6"  # MOL: Del. date dev.
_PRIORITY_MOL_TRANSPORT_WAREHOUSE = "7"      # MOL: Transport/WH
_PRIORITY_DEBIT_NOTE_RETAIL_DE = "8"         # Debit note Retail DE
_PRIORITY_DEBIT_NOTE_RETAIL_AT = "9"         # Debit note Retail AT
_PRIORITY_MAD_PRIORITY_HANDLING = "A"        # MAD: Prio handling
_PRIORITY_MAD_ACCEPT_REFUSAL = "B"           # MAD: Accept.refusal
_PRIORITY_MAD_BELOW_THRESHOLD = "C"          # MAD: < Threshold
_PRIORITY_MAD_RETURN_CUST = "D"              # MAD: Return cust.
_PRIORITY_MAD_RECURR_CLAIM = "E"             # MAD: Recurr. claim
_PRIORITY_MAD_DELIVERY_DATE_DEVIATION = "F"  # MAD: Del. date dev.
_PRIORITY_MAD_TRANSPORT_WAREHOUSE = "G"      # MAD: Transport/WH
_PRIORITY_REFILLING_FROM_MAD = "M"           # Refilling from MAD
_PRIORITY_REFILLING_FROM_EUE = "P"           # Refilling from EUE
_PRIORITY_REFILLING_FROM_MOL = "M"           # Refilling from MOL
_PRIORITY_EUE_PRIORITY_HANDLING = "S"        # EUE: Prio handling
_PRIORITY_EUE_BELOW_THRESHOLD = "U"          # EUE: < Threshold
_PRIORITY_EUE_RETURN_CUST = "V"              # EUE: Return cust.
_PRIORITY_EUE_RECURR_CLAIM = "W"             # EUE: Recurr. claim
_PRIORITY_EUE_DELIVERY_DATE_DEVIATION = "X"  # EUE: Del. date dev.
_PRIORITY_EUE_TRANSPORT_WAREHOUSE = "Y"      # EUE: Transport/WH

"""Shipping warehouses"""
SHIPPING_POINT_UNDEFINED = ""                # blank (unknown)
SHIPPING_POINT_MOLSHEIM = "D401"             # Molsheim (France)
SHIPPING_POINT_WROCLAW = "E901"              # Wroclaw (Poland)

_claim_types = {

	"price": {
		"code": "001",
		"type": {
			"under_threshold": ("YZCT0020", "YZ60"),
			"over_threshold": ("", "")
		}

	},

	"invoice": {
		"code": "003",
		"type": {
			"under_threshold": ("YZCT0020", "YZ50"),
			"over_threshold": ("", "")
		}
	},

	"delivery": {
		"code": "004",
		"type": {
			"under_threshold": ("YZCT0020", "YZ40"),
			"over_threshold": ("", "")
		}
	},

	"finance": {
		"code": "008",
		"type": {
			"under_threshold": ("", ""),
			"over_threshold": ("", "")
		}
	},

	"penalty_general": {
		"code": "010",
		"type": {
			"under_threshold": ("YZCT0020", "YZ20"),
			"over_threshold": ("YZCT0030", "YZ10"),
		}

	},

	"penalty_quote": {
		"code": "011",
		"type": {
			"under_threshold": ("YZCT0020", "YZ20"),
			"over_threshold": ("YZCT0030", "YZ20")
		}
	},

	"penalty_delay": {
		"code": "012",
		"type": {
			"under_threshold": ("YZCT0020", "YZ20"),
			"over_threshold": ("YZCT0030", "YZ30")
		}
	},

	"return": {
		"code": "014",
		"type": {
			"under_threshold": ("YZCT0020", "YZ80"),
			"over_threshold": ("", "")
		}
	},

	"rebuild": {
		"code": "014",
		"type": {
			"under_threshold": ("", ""),
			"over_threshold": ("YZCT0040", "YZ20")
		}
	},

}

_priorities = {

	"1001": {

		"D401": {
			"under_threshold": _PRIORITY_MOL_BELOW_THRESHOLD,
			"over_threshold": _PRIORITY_DEBIT_NOTE_RETAIL_DE
		},

		"E901": {
			"under_threshold": _PRIORITY_EUE_BELOW_THRESHOLD,
			"over_threshold": _PRIORITY_DEBIT_NOTE_RETAIL_DE
		}

	},

	"1072": {

		"D401": {
			"under_threshold": _PRIORITY_MOL_BELOW_THRESHOLD,
			"over_threshold": _PRIORITY_DEBIT_NOTE_RETAIL_AT
		},

		"E901": {
			"under_threshold": _PRIORITY_EUE_BELOW_THRESHOLD,
			"over_threshold": _PRIORITY_DEBIT_NOTE_RETAIL_AT
		}

	},

	"0074": {

		"D401": {
			"under_threshold": _PRIORITY_MOL_BELOW_THRESHOLD,
			"over_threshold": _PRIORITY_DEBIT_NOTE_RETAIL_AT
		},

		"E901": {
			"under_threshold": _PRIORITY_EUE_BELOW_THRESHOLD,
			"over_threshold": _PRIORITY_DEBIT_NOTE_RETAIL_AT
		}

	},

}

_task_responsible = {

	"Q25": {
		"8": "50019602",
		"9": "50019608"
	},

	"P25": {
		"8": "50019628",
		"9": "50019632"
	}

}

_currencies = {
	"1001": "EUR",
	"1072": "EUR",
	"0074": "CHF"
}

def _get_partners(doc: Union[Delivery, Invoice]) -> tuple:
	"""
	Reads business partners related to a shipment.

	Params:
	-------
	doc: Document that serves as a reference to the shipment.

	Returns:
	--------
	Sales doc - VBAK BSTNK (po-num) + KUNNR (sold-to) = VBELN (sales-doc)
	Invoice - VBRK KUNAG (sold-to) + ZUKRI (sales-doc) VBELN (bill-doc)
	Delivery - VBFA VBELV(sales-doc) + VBTYP_N

	Partners:
	---------
	KU (Kunde) = coordinator:
		Name of the person who coordinates the processsing of SN.

	WE (Warenempfänger) = ship-to-party:
		Account number of the branch that received the shipment.

	AG (Auftraggeber) = sold-to-party:
		Account number of the business unit under which the purchase agreement is registered

	SP (Spediteur) = spedition:
		the identifier of the transport company (Schenker/GLS)),
		that transported the goods from the stock to the sold-to-party location
	"""

	assert isinstance(doc, (Delivery, Invoice))

	ag_partner, we_partner, sp_partner = (None, None, None)
	doc_fmt = rfc.format_number(int(doc))

	params = {
		"SP": "LIFNR",
		"WE": "KUNNR",
		"AG": "KUNNR"
	}

	for ptr, fld in params.items():

		response = rfc.RFC_READ_TABLE(
			rfc.connection,
			query_table = 'VBPA',
			options = [
				{'TEXT': f"VBELN = '{doc_fmt}'"},
				{'TEXT': f"AND PARVW = '{ptr}'"}
			],
			fields = [{'FIELDNAME': fld}],
			data_format = "structured"
		)

		if ptr == "SP":
			sp_partner = response['DATA'][0][fld] if len(response['DATA']) != 0 else None
		elif  ptr == "WE":
			we_partner = response['DATA'][0][fld] if len(response['DATA']) != 0 else None
		elif ptr == "AG":
			ag_partner = response['DATA'][0][fld] if len(response['DATA']) != 0 else None

	assert ag_partner is not None, "AG partner not found! Creating a SN referened by an invoice or delivery requires a valid AG partner value!"
	assert we_partner is not None, "WE partner not found! Creating a SN referened by an invoice or delivery requires a valid WE partner value!"

	if sp_partner is None:
		g_log.warning(
			"SP partner not found. Some invoices represent "
			"backbilling and are not directly linked to a "
			"supplier. Further investigation is recommended.")

	return (ag_partner, we_partner, sp_partner)

def _get_sales_document(doc: Union[Delivery, Invoice]) -> dict:
	"""Retrieves sales document data from SAP."""

	g_log.info("Retrieving sales document data ...")

	doc_fmt = rfc.format_number(int(doc))

	response = rfc.RFC_READ_TABLE(
		rfc.connection,
		query_table = 'VBFA',
		data_format = 'structured',
		fields = [
			{'FIELDNAME': "VBELV"}
		],
		options = [
			{'TEXT': f"VBELN = '{doc_fmt}'"},
			{'TEXT': "AND VBELV LIKE '02%'"}
		]
	)

	sales_docs = [entry["VBELV"] for entry in response['DATA']]
	sales_docs = list(set(sales_docs))

	if len(sales_docs) == 0 and isinstance(doc, Invoice):
		g_log.warning(
			"No sales document exists for the invoice. Some invoices "
			"represent backbilling and are not directly linked to a "
			"sales process. Further investigation is recommended.")
		return {}

	if len(sales_docs) > 1:
		g_log.warning(f"Found {len(sales_docs)} sales documents.")

	sales_docs = list(set(sales_docs))
	records = []

	for sales_doc in sales_docs:

		response = rfc.RFC_READ_TABLE(
			rfc.connection,
			query_table = 'VBAK',
			data_format = 'structured',
			options = [
				{'TEXT': f"VBELN = '{sales_doc}'"}
			],
			fields = [
				{'FIELDNAME': 'VKORG'},
				{'FIELDNAME': 'VTWEG'},
				{'FIELDNAME': 'SPART'},
				{'FIELDNAME': 'VKGRP'},
				{'FIELDNAME': 'VKBUR'}
			],
		)

		data = {
			'VTWEG': response['DATA'][0]['VTWEG'],
			'SPART': response['DATA'][0]['SPART'],
			'VKBUR': response['DATA'][0]['VKBUR'],
			'VKGRP': response['DATA'][0]['VKGRP']
		}

		records.append(data)

	deduped = [dict(t) for t in {tuple(d.items()) for d in records}]
	assert len(deduped) == 1, "A unique data record expected!"
	data = deduped[0]

	g_log.info("Data successfully retrieved.")
	logger.print_data(data, desc = "Sales document:", top_brackets = False)

	return data

def _exists_active_task(notif_id: str) -> bool:
	"""Check if a notification contains any active task."""

	notif = rfc.IQS4_GET_NOTIFICATION(rfc.connection, notif_id)

	for task in notif['E_IVIQMSM_T']:
		if task["STTXT"] == "TSOS":
			return True

	return False

def _complete_task(notif_id: str, task_key: str, n_attempts: int = 10) -> None:
	"""Completes a task."""

	nth = 0
	wait_to_complete_secs = 1
	coeff = 1

	while nth < n_attempts:

		time.sleep(wait_to_complete_secs * coeff)
		coeff *= 2

		rfc.BAPI_QUALNOT_CHANGETSKSTAT(
			rfc.connection,
			number = notif_id,
			task_key = task_key,
			task_code = '01',
			carried_out_by = 'G.ROBOT_RFC',
			carried_out_date = rfc.get_current_time("%Y%m%d"),
			carried_out_time = rfc.get_current_time("%H%M%S")
		)

		notif_data = rfc.BAPI_QUALNOT_GETDETAIL(rfc.connection, notif_id)
		notif_task = notif_data['NOTIFTASK']

		if len(notif_task) == 0 or notif_task[0]['STATUS'] != "TSCO":
			nth += 1
			g_log.warning(f"Could not complete the task. Reattempt {nth} / {n_attempts} ...")
		else:
			nth = 0 # reset attempt counter
			break

	if nth > 0: # all attempts to complete the task exhausted without success
		raise RuntimeError(f"Could not complete the task with key: '{task_key}'!")

def _create_task(notif_id: str, params: dict, n_attempts: int = 10) -> str:
	"""Creates a new task for a notification."""

	notif = rfc.IQS4_GET_NOTIFICATION(rfc.connection, notif_id)
	new_task_key = len(notif['E_IVIQMSM_T']) + 1
	new_task_key = rfc.format_number(new_task_key, n_digits = 4)

	if len(notif['E_IVIQMSM_T']) == 0:
		new_task_sortno = "0001"
	else:
		new_task_sortno = notif['E_IVIQMSM_T'][-1]['QSMNUM']
		new_task_sortno = rfc.format_number(int(new_task_sortno) + 1, n_digits = 4)

	# Sort number for task; field attrib. QSMNUM = No. in QM02
	params.update({'TASK_SORT_NO': new_task_sortno})
	logger.print_data(params, "RFC Parameters:", top_brackets = False)

	wait_to_complete_secs = 4
	nth = 0

	while nth < n_attempts:
		time.sleep(wait_to_complete_secs)
		try:
			response = rfc.BAPI_QUALNOT_ADD_DATA(
				rfc.connection,
				number = notif_id,
				notiftask = [params]
			)
		except (rfc.NotificationLockedError, rfc.NotificationDoesNotExistError) as exc:
			g_log.error(exc)
			nth += 1
			g_log.debug(f"Attempt # {nth} to handle the '{type(exc)}' exception ...")
		except Exception as exc:
			raise RuntimeError(str(exc)) from exc
		else:
			if nth != 0:
				g_log.debug("Exception successfully handled.")
			nth = 0 # reset attempt counter
			break

	# Check for errors occured while creating QM
	if nth != 0:
		raise RuntimeError(response['RETURN'][0]['MESSAGE'])

	return new_task_key

def _create_dispute_task(notif_id: str, object_no: str, case_id: str) -> None:
	"""Create FSCM dispute."""

	params = {
		'REFOBJECTKEY': object_no,
		'TASK_TEXT': case_id,
		'TASK_CODEGRP': 'YZ000010',
		'TASK_CODE': 'YZ19',
		'PARTN_ROLE': 'VU',
		'PARTNER': 'G.ROBOT_RFC',
		'PLND_START_DATE': rfc.get_current_time("%Y%m%d"),   # '20220308'
		'PLND_START_TIME': rfc.get_current_time("%H%M%S"),   # '120000'
		'PLND_END_DATE': rfc.get_current_time("%Y%m%d"),     # '20220308' 	PETER
		'PLND_END_TIME': rfc.get_current_time("%H%M%S"),     # '120000'
		'CARRIED_OUT_BY': 'G.ROBOT_RFC'
	}

	g_log.info("Creating dispute task ...")
	task_id = _create_task(notif_id, params)
	g_log.info(f"Task with ID: '{task_id}' successfully created.")

	g_log.info(f"Completing the dispute task with ID: '{task_id}' ...")
	_complete_task(notif_id, task_id)
	g_log.info(f"Task with ID: '{task_id}' successfully completed.")

def _create_cs_task(notif_id: str, object_no: str, case_id: str, resp_ptr: str) -> None:
	"""Creates a task serving as an info to corresponding CS group."""

	params = {
		'REFOBJECTKEY': object_no,
		'TASK_TEXT': case_id,
		'TASK_CODEGRP': "YZ000020",
		'TASK_CODE': "YZ90",
		'PARTN_ROLE': 'AB',
		'PARTNER': resp_ptr,                                # 'YZ_CS Slovakia'
		'PLND_START_DATE': rfc.get_current_time("%Y%m%d"),  # '20220308'
		'PLND_START_TIME': rfc.get_current_time("%H%M%S"),  # '120000'
	}

	g_log.info("Creating CS task ...")
	task_id = _create_task(notif_id, params)
	g_log.info(f"Task with ID: '{task_id}' successfully created.")

def _activate_notification(notif_id: str) -> None:
	"""Puts a notification in process."""

	time.sleep(2)

	try:
		rfc.BAPI_QUALNOT_RELSTAT(rfc.connection, notif_id)
	except rfc.NotificationInProcessWarning as wng:
		g_log.warning(wng)

	time.sleep(4)

def _complete_notification(notif_id: str) -> None:
	"""
	Completes a service notification.

	Params:
	-------
	notif_id: Identification number of the service notification.
	"""

	g_log.info("Completing service notification ...")
	rfc.BAPI_QUALNOT_COMPLSTAT(rfc.connection, notif_id)
	g_log.info("Notification successfully completed.")

def create_notification(
	reference_by: Union[Account, Invoice, Delivery], reference_no: str,
	description: str, category_name: str, amount: float, threshold: float,
	company_code: str, coordinator: str, shipping_point: str = None) -> tuple:
	"""
	Creates a new YZ-type service notification.

	Params:
	-------
	ref:
		Reference to create the service notification:
		- Invoice: Represents an invoice.
		- Delivery: Represents a delivery number.
		- Account: Represents a customer account number.

	reference_no:
		Text entered into the field 'Reference no.' located in a QM transaction.

	desc:
		Text entered into the field 'Description' located in a QM transaction.

	category_name:
		Name of the document category:
		- delivery
		- price
		- invoice
		- penalty_general
		- penalty_delay
		- penalty_quote
		- return
		- rebuild_without_return

	amount:
		Totol customer-disputed amount of a debit note.

	thresh:
		Monetary value that represent the evel for writing off customer-disputed amounts.

	company_code:
		An internal 4-digit code thet represents the central organizational unit of
		external accounting  under which the customer is registered within the SAP System:
		- '1001': Germany
		- '1072': Austria
		- '0074': Switzerland

	coordinator:
		User name of the claim coordinating person at the CS department.
		The value is entered into the field 'Coordinator (user)' located in a QM transaction.

	Returns:
	--------
	A tuple of the notification ID (`int`), case ID (`int`) and case GUID (`str`).
	"""

	if not isinstance(reference_by, (Account, Invoice, Delivery)):
		raise TypeError(f"Argument 'ref' has incorrect type: '{type(reference_by)}'!")

	if amount <= 0.0:
		raise ValueError(f"Invalid amount value: {amount}!")

	if threshold < 0.0:
		raise ValueError(f"Invalid threshold value: {threshold}!")

	if not isinstance(reference_no, str):
		raise TypeError(f"Argument 'reference_no' has incorrect type: '{reference_no}'!")

	if len(reference_no) > 20:
		raise ValueError("Text length for field 'Description' exceeded!")

	if reference_no == "":
		raise ValueError("Text to write into field 'Reference No.' is an empty string!")

	if not isinstance(description, str):
		raise TypeError(f"Argument 'desc' has incorrect type: '{reference_no}'!")

	if len(description) > 40:
		raise ValueError("Text length for field 'Description' exceeded!")

	if description == "":
		raise ValueError("Field 'Description' text is empty!")

	if category_name not in _claim_types:
		raise ValueError(f"Unrecognized category name: '{category_name}'!")

	if company_code not in ("1001", "1072", "0074"):
		raise ValueError(f"Unrecognized company code: '{company_code}'!")


	case_type = rfc.get_case_type(company_code)
	sales_org = rfc.get_sales_organization(company_code)

	if isinstance(reference_by, Account):
		# use Molsheim as default value, since the shipping point
		# cannot be identified when referencing by account
		shipping_point = SHIPPING_POINT_MOLSHEIM
	elif isinstance(reference_by, Delivery) and shipping_point is None:
		raise ValueError(
			"Shipping point should be specified if a notification "
			"to create is referenced by delivery note!")
	elif isinstance(reference_by, Invoice) and shipping_point is None:
		g_log.warning("A notification will be created using an invoice as reference without shipping point.")
		shipping_point = SHIPPING_POINT_MOLSHEIM
	elif shipping_point not in (SHIPPING_POINT_MOLSHEIM, SHIPPING_POINT_WROCLAW):
		raise ValueError(f"Unrecognzed Shipping point '{shipping_point}' used!")

	category = _claim_types[category_name]["code"]
	prior_key = "under_threshold" if amount < threshold else "over_threshold"
	priority = _priorities[company_code][shipping_point][prior_key]
	coding = _claim_types[category_name]["type"][prior_key]
	curr = _currencies[company_code]

	ref_by = {}
	ref_fmt = rfc.format_number(int(reference_by))

	if isinstance(reference_by, Account):
		ref_by.update({'KUNUM': ref_fmt})
	elif isinstance(reference_by, Delivery):
		ref_by.update({'LS_VBELN': ref_fmt})
	elif isinstance(reference_by, Invoice):
		ref_by.update({'ZZ_VBELN_VF': ref_fmt})

	# Notification header data
	i_riqs5 = {
		'QMART': 'YZ',              # Notification type
		'REFNUM': reference_no,     # External reference number
		'QMTXT': description,       # Description
		'PRIOK': priority,          # Priority
		'FIN_CUSTDISP_AMT': amount, # Customer disputed amount
		'VKORG': sales_org,         # Sales Org.
		'VTWEG': '01',              # Distribution channel
		'SPART': '00',              # Division
		'QMGRP': coding[0],         # Claim type field # 1
		'QMCOD': coding[1]          # Claim type field # 2
	}

	i_riqs5.update(ref_by)

	# Partners:
	# KU (Kunde) = coordinator,
	# WE (Warenempfänger) = ship-to-party,
	# AG (Auftraggeber) = sold-to-party,
	# SP (Spediteur) = spedition (Schenker/GLS))
	i_ihpa_t = [{
		'PARVW': 'KU',
		'PARNR': coordinator,
		'ADRNR': '',
		'REFOBJKEY': '',
	}]

	ag_partner = None
	we_partner = None
	sp_partner = None

	if isinstance(reference_by, (Delivery, Invoice)):
		g_log.info("Identifying business partners ...")
		ag_partner, we_partner, sp_partner = _get_partners(reference_by)
		g_log.info(
			f"Partners identified. AG partner: '{ag_partner}'; "
			f"WE partner: '{we_partner}'; SP partner: '{sp_partner}'.")

		i_ihpa_t.append({
			'PARVW': 'WE',  # Ship-to
			'PARNR': we_partner,
			'ADRNR': '',
			'REFOBJKEY': '',
		})

		i_ihpa_t.append({
			'PARVW': 'AG',
			'PARNR': ag_partner,
			'ADRNR': '',
			'REFOBJKEY': '',
		})

	elif isinstance(reference_by, Account):
		i_ihpa_t.append({
			'PARVW': 'AG',
			'PARNR': rfc.format_number(int(reference_by)),
			'ADRNR': '',
			'REFOBJKEY': '',
		})

	g_log.info("Creating service notification ...")
	response1 = rfc.IQS4_CREATE_NOTIFICATION(
		rfc.connection,
		i_commit = 'X',      # Commit
		i_ihpa_t = i_ihpa_t,
		i_riqs5 = i_riqs5,   # Notification header
	)

	# Check for errors occured while creating QM
	if len(response1['RETURN']) != 0:
		if response1['RETURN'][0]['TYPE'] == 'E':
			raise RuntimeError(response1['RETURN'][0]['MESSAGE'])

	notif_id = response1['E_VIQMEL']['QMNUM']
	obj_no = response1['E_VIQMEL']['OBJNR']
	handle = response1['E_VIQMEL']['HANDLE']
	cust_acc = response1['E_VIQMEL']['KUNUM']

	g_log.info(f"Notification with ID: {int(notif_id)} successfully created.")

	is_viqmel = {
		'MANDT': '050',                           # Client
		'QMNUM': notif_id,                        # Notification No
		'MAUEH': 'H',                             # Unit for Breakdown Duration
		'SCREENTY': 'O500',                       # Scenario or Subscreen Category
		'QMART': 'YZ',                            # Notification Type
		'QMTXT': description,                     # Short Text
		'ARTPR': 'YZ',                            # Priority Type
		'PRIOK': priority,                        # Priority
		'ERNAM': 'G.ROBOT_RFC',                   # Name of Person Who Created the Object
		'AENAM': 'G.ROBOT_RFC',                   # Name of person who changed object
		'ERDAT': rfc.get_current_time("%Y%m%d"),  # Date on Which Record Was Created
		'MZEIT': rfc.get_current_time("%H%M%S"),  # Time of Notification
		'QMDAT': rfc.get_current_time("%Y%m%d"),  # Date of Notification
		'STRMN': rfc.get_current_time("%Y%m%d"),  # Required start date
		'STRUR': rfc.get_current_time("%H%M%S"),  # Required Start Time
		'LTRMN': rfc.get_current_time("%Y%m%d"),  # Required End Date
		'LTRUR': rfc.get_current_time("%H%M%S"),  # Requested End Time
		'BEZDT': rfc.get_current_time("%Y%m%d"),  # Notification Reference Date
		'BEZUR': rfc.get_current_time("%H%M%S"),  # Notification Reference Time
		'ERZEIT': rfc.get_current_time("%H%M%S"), # Time, at Which Record Was Added
		'WAERS': curr,                            # Currency Key
		'KUNUM': cust_acc,                        # Account Number of Customer
		'MAKNZ': 'X',                             # Task Records Exist
		'OBJNR': obj_no,                          # Object Number for Status Management
		'RBNR': 'YZQM00001',                      # Catalog Profile
		'RBNRI': '0',                             # Origin of Notifications Catalog Profile
		'KZMLA': 'E',                             # Primary language indicator for text segment
		'HERKZ': 'Q1',                            # Origin of Notification
		'VKORG': sales_org,                       # Sales Organization
		'BUKRS': company_code,                    # Sales Organization
		'MAWERK': 'D004',                         # Plant for Material
		'QMKAT': 'Y',                             # Catalog Type - Coding
		'REFNUM': reference_no,                   # External Reference Number
		'HANDLE': handle,                         # Globally unique identifier (linked to time segment, etc)
		'TZONSO': 'CET',                          # Time Zone for Notification
		'FUNKTION': '0090',                       # Key for Function in Action Box
		'ZZ_WERK': 'D004',                        # Plant
		'CASE_TYPE': case_type,                   # Case Type
		'FIN_CUSTDISP_AMT': amount,               # Customer-Disputed Amount
		'FIN_CUSTDISP_CUR': curr,                 # Currency of Customer-Disputed Amount
		'PHASE': '3',                             # Notification Processing Phase
		'CATEGORY': category,                     # Category
		'REASON_CODE': "XXX",                     # reason code
		'OWNER': '4',                             # Object reference indicator
		'QMGRP': coding[0],                       # Claim type field # 1
		'QMCOD': coding[1]                        # Claim type field # 2
	}

	is_viqmel.update(ref_by)

	# Add organization data from sales-doc
	# NOTE: an option would be to use KNB1 to assing the company code
	# based on a customer account, however, there are multiple entries
	# per acc in ome cases, so it would be difficult to identify the
	# correct company code.
	if isinstance(reference_by, (Invoice, Delivery)):
		sales_doc = _get_sales_document(reference_by)
		is_viqmel.update(sales_doc)

	if isinstance(reference_by, (Delivery, Invoice)):
		if sp_partner is not None:
			is_viqmel.update({'ZZ_PARTNER_SP': sp_partner})
		is_viqmel.update({'ZZ_PARTNER_WE': we_partner})
	elif isinstance(reference_by, (Account)):
		is_viqmel.update({'ZZ_PARTNER_WE': cust_acc})

	# Create FSCM Dispute
	response2 = rfc.ZQM25_CLAIM_DISPUTE_POST(rfc.connection, is_viqmel)
	case_id = response2['EX_CASE_ID']

	# Read newly created FSCM Dispute
	# Conversion table to get INSTID (SRGBTBREL)
	response3 = rfc.RFC_READ_TABLE(
		rfc.connection,
		query_table = 'SCMG_T_CASE_ATTR',
		options = [{'TEXT': f"EXT_KEY = '{case_id}'"}],
		fields = [{'FIELDNAME': 'CASE_GUID'}],
		rowcount = 10
	)

	case_guid = response3['DATA'][0]['WA']

	# Ensure the correct reason code an customer account appears in DMS
	attributes = [
		{'ATTR_ID': 'REASON_CODE', 'ATTR_VALUE': "XXX"},
		{'ATTR_ID': 'FIN_KUNNR', 'ATTR_VALUE': cust_acc},
		{'ATTR_ID': 'ZZ_FILIALE', 'ATTR_VALUE': cust_acc}
	]

	g_log.info("Changing dispute parameters ...")
	logger.print_data(attributes, desc = "Parameters and values to write:", top_brackets = False, compact = True)
	rfc.BAPI_DISPUTE_ATTRIBUTES_CHANGE(rfc.connection, case_guid, attributes)
	g_log.info("Dispute parameters successfully changed.")

	# Add Tasks and complete SN if below thresh
	_create_dispute_task(notif_id, obj_no, case_id)

	if amount < threshold:
		_complete_notification(notif_id)
	else:
		conn_info = rfc.connection.get_connection_attributes()
		responsible = _task_responsible[conn_info["sysId"]][priority]
		_create_cs_task(notif_id, obj_no, case_id, responsible)

	return (int(notif_id), int(case_id), case_guid)

def _assign_sales_order(notif: dict, is_viqmel: dict) -> dict:
	"""Checks notification tasks for sales order number and, if found, 
	updates the notification header with the sales order number."""

	result = deepcopy(is_viqmel)

	# Define strings that, when found in the 'Order Code Text' field,
	# indicate the presence of a sales order number in the 'Task text' field.
	identifiers = [
		"change sales order",
		"create return order",
		"create adjustment change"
	]

	# If any task contains one of the identifiers in its text, then
	# retrieve the sales order number from the 'Task text' field
	# of the task, and update the notification header data accordingly.
	for task in notif['E_IVIQMSM_T']:
		for identifier in identifiers:
			if identifier in task['TXTCD'].lower():
				sales_order = rfc.format_number(task['MATXT'])
				result.update({"VBELN": sales_order})
				break

	return result

def add_case(
		notif_id: int, category_name: str, amount: float,
		threshold: float, title: str, company_code: str,
		reference_no: str = None) -> tuple:
	"""Creates a new YZ-type service notification.

	Params:
	-------
	notif_id:
		Notification identification number.

	category_name:
		Name of the document category:
		- delivery
		- price
		- invoice
		- penalty_general
		- penalty_delay
		- penalty_quote
		- return
		- rebuild_without_return

	amount:
		Totol customer-disputed amount of a debit note.

	threshold:
		Monetary value that represent the evel for writing off customer-disputed amounts.

	title:
		Text entered into the "Title" field in DMS.

	company_code:
		An internal 4-digit code thet represents the central organizational unit of
		external accounting  under which the customer is registered within the SAP System:
		- '1001': Germany
		- '1072': Austria
		- '0074': Switzerland

	reference_no:
		Text entred in the "Reference no." field in QM.
		By default, no text is entered.

	Returns:
	--------
	A tuple of resulting Case ID (`int`) and Case GUID (`str`).
	"""

	notif_id = rfc.format_number(notif_id, n_digits = 12)
	notif_data = rfc.IQS4_GET_NOTIFICATION(rfc.connection, notif_id)

	cust_acc = notif_data['E_VIQMEL']['KUNUM']
	obj_no = notif_data['E_VIQMEL']['OBJNR']
	handle = notif_data['E_VIQMEL']['HANDLE']
	sales_org = notif_data['E_VIQMEL']['VKORG']
	sales_off = notif_data['E_VIQMEL']['VKBUR']
	sales_group = notif_data['E_VIQMEL']['VKGRP']
	case_type = notif_data['E_VIQMEL']['CASE_TYPE']
	dist_channel = notif_data['E_VIQMEL']['VTWEG']
	division = notif_data['E_VIQMEL']['SPART']
	desc = notif_data['E_VIQMEL']['QMTXT']
	orig_priority = notif_data['E_VIQMEL']['PRIOK']
	shipping_point = notif_data['E_VIQMEL']['ZZ_VERSANDSTELLE']
	orig_reference_no = notif_data['E_VIQMEL']['REFNUM']
	curr = notif_data['E_VIQMEL']['WAERS']
	category = _claim_types[category_name]["code"]
	group_coding = notif_data['E_VIQMEL']['QMGRP']      # coding sa nemeni pri pridavani disputu
	subgroup_coding = notif_data['E_VIQMEL']['QMCOD']   # coding sa nemeni pri pridavani disputu

	deliv_num = notif_data['E_VIQMEL']['LS_VBELN']
	invc_num = notif_data['E_VIQMEL']['ZZ_VBELN_VF']

	if deliv_num != "" and invc_num != "":
		g_log.warning(
			"The notification contains reference "
			"to both a delivery and an invoice.")

	# change the priority only if the amount is greather than
	# the thresholding amount and the original priority has the
	# "< Threshold" value otehrwise keep the original priority.
	# In case when no priority is selected by mistake, an empty
	# string is returned instead of a concrete number. In this
	# situation select a priority from the _priorities[] list.
	prior_key = "under_threshold" if amount < threshold else "over_threshold"

	if shipping_point == SHIPPING_POINT_MOLSHEIM:
		if orig_priority == _PRIORITY_UNUSED or (prior_key == "over_threshold" and orig_priority in (_PRIORITY_MOL_BELOW_THRESHOLD, _PRIORITY_EUE_BELOW_THRESHOLD)):
			priority = _priorities[company_code][shipping_point][prior_key]
			g_log.debug(f"The original notification priority '{orig_priority}' will be changed to: '{priority}'.")
		else:
			priority = orig_priority
			g_log.debug(f"The original notification priority '{orig_priority}' won't be changed.")
	elif shipping_point == SHIPPING_POINT_WROCLAW:
		if orig_priority == _PRIORITY_UNUSED or (prior_key == "over_threshold" and orig_priority in (_PRIORITY_MOL_BELOW_THRESHOLD, _PRIORITY_EUE_BELOW_THRESHOLD)):
			priority = _priorities[company_code][shipping_point][prior_key]
			g_log.debug(f"The original notification priority '{orig_priority}' will be changed to: '{priority}'.")
		else:
			priority = orig_priority
			g_log.debug(f"The original notification priority '{orig_priority}' won't be changed.")
	elif shipping_point == SHIPPING_POINT_UNDEFINED:
		if orig_priority ==_PRIORITY_UNUSED or (prior_key == "over_threshold" and orig_priority in (_PRIORITY_MOL_BELOW_THRESHOLD, _PRIORITY_EUE_BELOW_THRESHOLD)):
			priority = _priorities[company_code][SHIPPING_POINT_MOLSHEIM][prior_key]
			g_log.debug(f"The original notification priority '{orig_priority}' will be changed to: '{priority}'.")
		else:
			priority = orig_priority
			g_log.debug(f"The original notification priority '{orig_priority}' won't be changed.")
	else:
		raise RuntimeError(f"Unrecognized shipping point '{shipping_point}' in the original notification!")

	g_log.debug(f"The new case will have the priority: '{priority}'.")
	ref_no = orig_reference_no if reference_no is None else reference_no

	is_viqmel = {
		'MANDT': '050',
		'QMNUM': notif_id,
		'MAUEH': 'H',
		'SCREENTY': 'O500',
		'QMART': 'YZ',
		'QMTXT': desc,
		'ARTPR': 'YZ',
		'PRIOK': priority,
		'ERNAM': 'G.ROBOT_RFC',
		'AENAM': 'G.ROBOT_RFC',
		'ERDAT': rfc.get_current_time("%Y%m%d"),
		'MZEIT': rfc.get_current_time("%H%M%S"),
		'QMDAT': rfc.get_current_time("%Y%m%d"),
		'STRMN': rfc.get_current_time("%Y%m%d"),
		'STRUR': rfc.get_current_time("%H%M%S"),
		'LTRMN': rfc.get_current_time("%Y%m%d"),
		'LTRUR': rfc.get_current_time("%H%M%S"),
		'BEZDT': rfc.get_current_time("%Y%m%d"),
		'BEZUR': rfc.get_current_time("%H%M%S"),
		'ERZEIT': rfc.get_current_time("%H%M%S"),
		'WAERS': curr,
		'KUNUM': cust_acc,
		'MAKNZ': 'X',
		'OBJNR': obj_no,
		'RBNR': 'YZQM00001',
		'RBNRI': '0',
		'KZMLA': 'E',
		'HERKZ': 'Q1',
		'VKORG': sales_org,
		'BUKRS': company_code,
		'MAWERK': 'D004',
		'QMKAT': 'Y',
		'REFNUM': ref_no,
		'HANDLE': handle,
		'TZONSO': 'CET',
		'FUNKTION': '0090',
		'ZZ_WERK': 'D004',
		'CASE_TYPE': case_type,
		'FIN_CUSTDISP_AMT': amount,
		'FIN_CUSTDISP_CUR': curr,
		'PHASE': '3',
		'CATEGORY': category,
		'REASON_CODE': "XXX",
		'OWNER': '4',
		'QMGRP': group_coding,      # Claim type field # 1
		'QMCOD': subgroup_coding,   # Claim type field # 2
		'SPART': division,
		'VTWEG': dist_channel,
		'VKBUR': sales_off,
		'VKGRP': sales_group,
		'LS_VBELN': deliv_num,
		'ZZ_VBELN_VF': invc_num
	}

	is_viqmel = _assign_sales_order(notif_data, is_viqmel)

	partners = {
		"ZZ_PARTNER_WE": notif_data['E_VIQMEL']['ZZ_PARTNER_WE'],
		'ZZ_PARTNER_SP': notif_data['E_VIQMEL']['ZZ_PARTNER_SP'],
		'ZZ_LIKP_ANZPK': notif_data['E_VIQMEL']['ZZ_LIKP_ANZPK'],
		'ZZ_VERSANDSTELLE': notif_data['E_VIQMEL']['ZZ_VERSANDSTELLE'],
		'ZZ_LIKP_ROUTE': notif_data['E_VIQMEL']['ZZ_LIKP_ROUTE']
	}

	logger.print_data(partners, desc = "Partners:", top_brackets = False)
	is_viqmel.update(partners)

	g_log.info("Putting the notification again in process ...")
	_activate_notification(notif_id)

	post_result = rfc.ZQM25_CLAIM_DISPUTE_POST(rfc.connection, is_viqmel)
	case_id = post_result['EX_CASE_ID']

	try:
		_create_dispute_task(notif_id, obj_no, case_id)
	except Exception as exc:
		logger.print_data(is_viqmel, desc = "is_viqmel:", top_brackets = False)
		raise RuntimeError(str(exc)) from exc

	if amount >= threshold:

		g_log.info("Creating CS task ...")
		conn_info = rfc.connection.get_connection_attributes()

		# cap the priority if the original one is other than 9 or 8
		system = conn_info["sysId"]

		if system == "Q25":
			priority = "9"
		elif system == "P25":
			priority = "8"
		else:
			raise RuntimeError(f"Unrecognized system '{system}' used!")

		responsible = _task_responsible[system][priority]
		_create_cs_task(notif_id, obj_no, case_id, responsible)
		g_log.info("Task successfully created.")

	# Read the data of the newly created dispute
	case_data = rfc.RFC_READ_TABLE(
		rfc.connection,
		query_table = 'SCMG_T_CASE_ATTR',
		options = [{'TEXT': f"EXT_KEY = '{case_id}'"}],
		fields = [{'FIELDNAME': 'CASE_GUID'}],
		rowcount = 10
	)

	# Ensure the correct reason code an customer account appears in DMS
	case_guid =  case_data['DATA'][0]['WA']

	attributes = [
		{'ATTR_ID': 'FIN_KUNNR', 'ATTR_VALUE': cust_acc},
		{'ATTR_ID': 'ZZ_FILIALE', 'ATTR_VALUE': cust_acc},
		{'ATTR_ID': 'CASE_TITLE', 'ATTR_VALUE': title}
	]

	g_log.info("Changing dispute parameters ...")
	logger.print_data(attributes, desc = "Parameters and values to write:", top_brackets = False, compact = True)
	rfc.BAPI_DISPUTE_ATTRIBUTES_CHANGE(rfc.connection, case_guid, attributes)
	g_log.info("Dispute parameters successfully changed.")

	if not _exists_active_task(notif_id):
		_complete_notification(notif_id)

	return (int(case_id), case_guid)

def list_products(notif_id: int, tech_names: bool = True) -> list:
	"""Creates a list of products associated with a service notification.

	Parameters:
	-----------
	notif_id:
		Identification number of the notification.
	
	tech_names:
		If True, the resulting data contain records with technical names as field names.
		Otherwise, the technical field names of records are translated into English.

	Returns:
	--------
	retrieved data ...
	"""

	# get notificaton
	notif_id = rfc.format_number(notif_id, n_digits = 12)
	notif_data = rfc.IQS4_GET_NOTIFICATION(rfc.connection, notif_id)

	# get outbound delivery
	delivery_num = notif_data["E_VIQMEL"]["LS_VBELN"]

	# from the outbound delivery get the list of items
	query = f"VBELN = '{delivery_num}'"

	response = rfc.RFC_READ_TABLE(
        rfc.connection,
        query_table = 'LIPS',
		fields = ["MATNR", "ARKTX"],
        options = [{'TEXT': query}],
		data_format = "structured"
    )

	if tech_names:
		return response ["DATA"]

	result = []

	for rec in response ["DATA"]:
		result.append({
			"Material": rec["MATNR"],
			"Description": rec["ARKTX"],
		})

	return result
