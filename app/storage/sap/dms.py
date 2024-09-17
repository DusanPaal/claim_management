# pylint: disable = W1203

"""Mediates operations performed in SAP UDM_DISPUTE Transaction."""

import re
import time
from math import isclose
from os.path import isfile, splitext

from ... import logger
from ..files import FilePath
from . import rfc

g_log = logger.get_global_logger()

_field_map = {
	"processor": "PROCESSOR",
	"status_sales": "ZZ_STAT_SL",
	"status": "STAT_ORDERNO",
	"case_type": "CASE_TYPE",
	"root_cause_code": "FIN_ROOT_CCODE",
	"status_ac": "ZZ_STAT_AC",
	"coordinator": "FIN_COORDINATOR",
	"responsible": "RESPONSIBLE",
	"company_code": "FIN_BUKRS",
	"external_reference": "EXT_REF",
	"disputed_amount": "FIN_CUSTDISP_AMT",
	"case_id": "EXT_KEY",
	"created_by": "CREATED_BY",
	"created_on": "CREATE_TIME",
	"changed_by": "CHANGED_BY",
	"changed_on": "CHANGE_TIME",
	"closed_by": "CLOSED_BY",
	"closed_on": "CLOSING_TIME",
	"title": "CASE_TITLE",
	"category": "CATEGORY",
	"reason": "REASON_CODE",
	"customer_disputed": "FIN_DISPUTED_AMT",
	"currency": "FIN_CUSTDISP_CUR",
	"customer_account": "FIN_KUNNR",
	"notification": "ZZ_QMNUM",
	"head_office": "ZZ_ZENTRALE",
	"assignment": "ZZ_ZUONR",
	"branch": "ZZ_FILIALE",
}

ROOT_CAUSE_CODE_UNUSED = None   # No root cause code is written/an existing value remains unchanged.
ROOT_CAUSE_CODE_ERASE = ""      # Erase any existing value.
ROOT_CAUSE_CODE_L00 = "L00"     # Unjustified dispute.
ROOT_CAUSE_CODE_L01 = "L01"     # Payment agreement.
ROOT_CAUSE_CODE_L06 = "L06"     # Creditnote issued.
ROOT_CAUSE_CODE_L08 = "L08"     # Charge-Off.
ROOT_CAUSE_CODE_L14 = "L14"     # Closed while under threshold.

def find_cases(
		title: str, comp_code: str, amount: float = None,
		tolerance = 0.0, states: list = None) -> list:
	"""Search DMS for a case based on defined criteria.

	Parameters:
	-----------
	title:
		Case title.

	comp_code:
		Company code represented by a 4-digit string.

	amount:
		Customer-disputed amount.

	tolerance:
		Maximum difference for amounts being considered "equal",
		regardless of the magnitude of the compared values

	states:
		List of `int` values from 1 to 4 representing case states:
		- 1: open
		- 2: solved
		- 3: closed
		- 4: devaluated

		If `None` is used, then all states will be used.

	Returns:
	--------
	List of dictionaries: {'case_id': an `int`, 'case_guid': a `str`}
	that represent the records found.
	"""

	if not isinstance(title, str):
		raise TypeError(f"Title of type 'str' expected, but got '{type(title)}'!")

	if title in ("%", "%%", ""):
		raise ValueError(f"Invalid title value: '{title}'!")

	if not (comp_code.isnumeric() and len(comp_code) == 4):
		raise ValueError(f"Incorrect company code used: '{comp_code}'!")

	if amount is not None:
		if not isinstance(amount, float):
			raise TypeError(f"Amount of type 'float' expected, but got '{type(amount)}'!")
		if amount <= 0:
			raise ValueError(f"Incorrect amount used: {amount}!")

	logger.print_data(
		desc = "Case search criteria:",
		row_list = True,
		top_brackets = False,
		data = {
			"title": title,
			"amount": amount,
			"tolerance": tolerance,
			"company_code": comp_code,
			"status": states
		}
	)

	if isinstance(states, int):
		states = [states]

	valid_states = range(5)

	for state in states or []:

		if not isinstance(state, int):
			raise TypeError(f"State of type 'int' expected, but got '{type(state)}'!")

		if state not in valid_states:
			raise ValueError(f"Incorrect state used: {state}!")

	# Table SCMG_T_CASE_ATTR doesn't contain amount
	# values. Therefore, table UDMCASEATTR00 needs
	# to be queried in the next step to obtain this
	# information. Then, the data from both tables
	# need to be joined and evaluated for duplicates.
	queries = []
	cases = []

	# sanitize title by repacing an asterisk
	# for the rfc-equivalent operator
	title = title.replace("*", "%")

	operator = "LIKE" if "%" in title else "="
	query = f"CASE_TITLE {operator} '{title}'"
	queries.append({'TEXT': query})

	case_type = rfc.get_case_type(comp_code)
	query = f"AND CASE_TYPE = '{case_type}'"
	queries.append({'TEXT': query})

	case_states = valid_states if states is None else states
	case_states = [f"'{cs}'" for cs in case_states]
	case_states = ", ".join(map(str, case_states))

	query = f"AND STAT_ORDERNO in ({case_states})"
	queries.append({'TEXT': query})

	resp_a = rfc.RFC_READ_TABLE(
		rfc.connection,
		query_table = 'SCMG_T_CASE_ATTR',
		options = queries,
		data_format = 'structured'
	)

	# get customer disputed amounts
	for item in resp_a['DATA']:

		case_guid = item['CASE_GUID']
		case_id = int(item['EXT_KEY'])
		query = f"CASE_GUID = '{case_guid}'"

		resp_b = rfc.RFC_READ_TABLE(
			rfc.connection,
			query_table = 'UDMCASEATTR00',
			options = [{'TEXT': query}],
			fields = [{'FIELDNAME': 'FIN_CUSTDISP_AMT'}],
			data_format = 'structured'
		)

		if amount is None:
			cases.append({"case_id": int(item['EXT_KEY']), "case_guid": case_guid})
			continue

		# Record the case ID only if the found and searched amounts
		# are equal. Such records are considered duplicated
		if len(resp_b['DATA']) == 0:
			# handle situation, when an already archived case is matched
			g_log.warning(
				f"Archived or invalid data found in DMS under case ID: {case_id}; "
				f"case GUID: '{case_guid}' and therefore don't represent a match.")
			return []

		found_amount = resp_b['DATA'][0]['FIN_CUSTDISP_AMT']
		found_amount = float(found_amount)

		if isclose(found_amount, amount, abs_tol = tolerance):
			cases.append({"case_id": int(item['EXT_KEY']), "case_guid": case_guid})

	return cases

def find_cases2(
		title: str, comp_code: str, amount: float = None,
		states: list = None, acc: int = None) -> list:
	"""Search DMS for a case based on defined criteria.

	Parameters:
	-----------
	title:
		Case title.

	comp_code:
		Company code represented by a 4-digit string.

	amount:
		Customer-disputed amount.

	states:
		List of `int` values from 1 to 4 representing case states:
		- 1: open
		- 2: solved
		- 3: closed
		- 4: devaluated

		If `None` is used, then all states will be used.

	acc:
		Customer account number.

	Returns:
	--------
	List of dictionaries: {'case_id': an `int`, 'case_guid': a `str`}
	that represent the records found.
	"""

	if not isinstance(title, str):
		raise TypeError(f"Title of type 'str' expected, but got '{type(title)}'!")

	if title == "":
		raise ValueError("Title is an empty string!")

	if not (comp_code.isnumeric() and len(comp_code) == 4):
		raise ValueError(f"Incorrect company code used: '{comp_code}'!")

	if amount is not None:
		if not isinstance(amount, float):
			raise TypeError(f"Amount of type 'float' expected, but got '{type(amount)}'!")
		if amount <= 0:
			raise ValueError(f"Incorrect amount used: {amount}!")

	logger.print_data(
		desc = "Case search criteria:",
		data = {
			"title": title,
			"amount": amount,
			"company_code": comp_code,
			"status": states
		}
	)

	if isinstance(states, int):
		states = [states]

	valid_states = range(5)

	for state in states or []:

		if not isinstance(state, int):
			raise TypeError(f"State of type 'int' expected, but got '{type(state)}'!")

		if state not in valid_states:
			raise ValueError(f"Incorrect state used: {state}!")

	# Table SCMG_T_CASE_ATTR doesn't contain amount
	# values. Therefore, table UDMCASEATTR00 needs
	# to be queried in the next step to obtain this
	# information. Then, the data from both tables
	# need to be joined and evaluated for duplicates.
	queries = []
	cases = []

	# sanitize title by repacing an asterisk
	# for the rfc-equivalent operator
	title = title.replace("*", "%")

	operator = "LIKE" if "%" in title else "="
	query = f"CASE_TITLE {operator} '{title}'"
	queries.append({'TEXT': query})

	case_type = rfc.get_case_type(comp_code)
	query = f"AND CASE_TYPE = '{case_type}'"
	queries.append({'TEXT': query})

	if acc is not None:
		query = f"AND FIN_KUNNR = '{acc}'"
		queries.append({'TEXT': query})

	case_states = valid_states if states is None else states
	case_states = [f"'{cs}'" for cs in case_states]
	case_states = ", ".join(map(str, case_states))

	query = f"AND STAT_ORDERNO in ({case_states})"
	queries.append({'TEXT': query})

	resp_a = rfc.RFC_READ_TABLE(
		rfc.connection,
		query_table = 'SCMG_T_CASE_ATTR',
		options = queries,
		data_format = 'structured'
	)

	# get customer disputed amounts
	for item in resp_a['DATA']:

		case_guid = item['CASE_GUID']
		case_id = int(item['EXT_KEY'])
		query = f"CASE_GUID = '{case_guid}'"

		resp_b = rfc.RFC_READ_TABLE(
			rfc.connection,
			query_table = 'UDMCASEATTR00',
			options = [{'TEXT': query}],
			fields = [{'FIELDNAME': 'FIN_CUSTDISP_AMT'}],
			data_format = 'structured'
		)

		if amount is None:
			cases.append({"case_id": int(item['EXT_KEY']), "case_guid": case_guid})
			continue

		# Record the case ID only if the found and searched amounts
		# are equal. Such records are considered duplicated
		if len(resp_b['DATA']) == 0:
			# handle situation, when an already archived case is matched
			g_log.warning(
				f"Archived or invalid data found in DMS under case ID: {case_id}; "
				f"case GUID: '{case_guid}' and therefore don't represent a match.")
			return []

		found_amount = resp_b['DATA'][0]['FIN_CUSTDISP_AMT']

		if float(found_amount) == float(amount):
			cases.append({"case_id": int(item['EXT_KEY']), "case_guid": case_guid})

	return cases

def list_attachments(case_guid: str, patts: list = None) -> list:
	"""Create a list of files attached to a case.

	Parameters:
	-----------
	case_guid: 
		ID string of the case.

	patts: 
		Regex patterns to search in file names.
		By default, all file names are listed.

	Returns:
	--------
	List of attachment names.
	"""

	response = rfc.GOS_API_GET_ATTA_LIST(
		rfc.connection,
		is_object = {
			'INSTID': case_guid,
			'TYPEID': 'SCASE',
			'CATID': 'BO'
		}
	)

	atts = []

	for line in response['ET_ATTA']:

		file_name = line['FILENAME']

		if patts is None:
			atts.append(file_name)
			continue

		for patt in patts:
			if re.search(patt, file_name) is not None:
				atts.append(file_name)

	return atts

def attach(case_guid: str, file: FilePath, att_name: str) -> None:
	"""Attach file to an existing case.

	Parameters:
	-----------
	case_guid:
		ID string of the case in DMS.

	file:
		Path to the file to attach.
	"""

	if not isfile(file):
		raise FileNotFoundError(f"The file doesn't exist: '{file}'!")

	ext = splitext(file)[1]
	att_name.rstrip(ext.upper())
	att_name.rstrip(ext.lower())

	# Upload as corresponding object type
	response = rfc.SO_DOCUMENT_INSERT_API1(
		rfc.connection,
		file_path = file,
		obj_descr = att_name
	)

	rfc.BINARY_RELATION_CREATE_COMMIT(

		rfc.connection,
		relationtype = 'ATTA',

		obj_rolea = {
			'OBJKEY': case_guid,
			'OBJTYPE': 'SCASE',
			'LOGSYS': ''
		},

		obj_roleb = {
			'OBJKEY': response['DOCUMENT_INFO']['DOC_ID'],
			'OBJTYPE': 'MESSAGE',
			'LOGSYS': ''
		},

	)

def get_case_parameters(case_guid: str) -> dict:
	"""Return params of a disputed case.

	Parameters:
	-----------
	case_guid: 
		Case GUID identification string.

	Returns:
	--------
	A dict of case parameters and the respective
	values as recorded in UDM_DISPUE (DMS) transaction:
		- 'processor' : Name of the case processign person at the CS department.
		- 'status_sales': Status sales text.
		- 'status': Case status
		- 'root_cause_code': Code of the case root cause.
		- 'status_ac': Status AC (accounting) text.
		- 'coordinator': Name of the person coordinnating the case processign at CS department
		- 'responsible': Name of the key account manager responsible for the ....
		- 'company_code': Internal accounting country code of the case.
		- 'external_reference': External reference field.
		- 'disputed_amount': Disputed amount field.
		- 'case_id': Identifiacation number of the case in DMS.
		- 'created_by': Name of the user who created the case.
		- 'created_on': Date when the case was created.
		- 'changed_by': User who changed the case.
		- 'changed_on': Date when the case was changed.
		- 'closed_by': User who closed the case.
		- 'closed_on': Date when the case was closed.
		- 'title': Case 'Title' text.
		- 'category': Case 'Category' name.
		- 'reason': Case 'Reason' code.
		- 'customer_disputed': Total case disputed amount.
		- 'currency': Currency of teh disputed case.
		- 'customer_account': Internal account number of the customer who issued the debit note.
		- 'notification': Identification number of service notification related to the case.
		- 'head_office': Internal head office account number of the customer who issued the debit note.
		- 'assignment': Case 'Assignment' field text.
		- 'branch': Internal account number of the customer who issued the debit
					note (usually identical with 'customer_account' parameter.)
	"""

	response = rfc.BAPI_DISPUTE_GETDETAIL_MULTI(rfc.connection, case_guid)
	reversed_field_map = {val:key for key, val in _field_map.items()}
	params = {}

	for rec in response["CASE_DETAIL"]:

		key = rec["ATTR_ID"]
		val = rec["ATTR_VALUE"]

		if key not in reversed_field_map:
			continue

		rev_key = reversed_field_map[key]

		params.update({rev_key: val.strip()})

	return params

def modify_case_params(case_guid: str, **kwargs) -> None:
	"""Updates params of a disputed case.

	Parameters:
	-----------
	Parameters where value is `None` are skipped.

	case_guid:
		Case GUID identification string.

	kwargs:
		processor:
			User name of the case processing
			person at CS Nearshore department.

		currency:
			Currency of the case.

		branch:
			The 'Branch' parameter of a case.

		disputed_amount:
			The 'Cust.-Disputed' parameter of a case.

		customer_account:
			The 'Customer' parameter of a case.

		status_sales:
			The "Status Sales" parameter of the case.
			The text limit is 50 chars.

		case_type:
			A 4-digit string tha represents type of the case.

		root_cause_code:
			Root Cause Code of the case.

			The following constants can be used instead of passing values directly:
			- ROOT_CAUSE_CODE_UNUSED: Root cause code won't be changed (corresponds to value: None)
			- ROOT_CAUSE_CODE_ERASE: Any existing root cause code will be erased (corresponds to value: "").
			- ROOT_CAUSE_CODE_L00: Unjustified dispute (corresponds to value: "L00").
			- ROOT_CAUSE_CODE_L01: Payment agreement (corresponds to value: "L01").
			- ROOT_CAUSE_CODE_L06: Creditnote issued (corresponds to value: "L06").
			- ROOT_CAUSE_CODE_L08: Charge-Off (corresponds to value: "L08").
			- ROOT_CAUSE_CODE_L14: Closed while under threshold (corresponds to value: "L14").

		status_ac: 
			Status AC

		status: 
			The value of the 'Status' field of the DMS case.
			

		coordinator:
			Coordinator of the case

		responsible: Person Responsible

		company_code: Company Code

		external_reference: External Reference
	"""

	logger.print_data(
		desc = "New case parameters:",
		row_list = True,
		top_brackets = False,
		data = {k:v for k, v in kwargs.items() if v is not None}
	)

	root_cause_updated = False
	n_attempts = 20     # number of attamts to try handling the "notfication locked by user" error before giving up
	n_secs = 3          # time interval in seconds to pass between attempts to retry updating case params
	nth_attempt = 0     # attempt counter

	if kwargs.get("root_cause_code") not in (None, "L00","L01", "L06", "L08", "L14"):
		raise ValueError("Invalid root cause code!")

	if kwargs.get("status", None) is not None:

		status = kwargs["status"]

		if status not in (1, 2, 3, 4):
			raise ValueError(f"Invalid 'status' value {status}! Status value must be in range 1-4!")

		if status > 1 and "root_cause_code" not in kwargs:
			raise ValueError(f"Status change to {status} is requested but root cause code is not provided!")

		if status == 4:
			g_log.warning(
				"Case status is about to be changed to: 4 "
				"and the case will be devaluated.")

		curr_status = 1

		while curr_status < status:

			g_log.debug(f"Changing case status from {curr_status} to {curr_status + 1} ...")

			new_status = curr_status + 1
			attribs_a = [{'ATTR_ID': _field_map["status"], 'ATTR_VALUE': str(new_status)}]

			if new_status == 2:
				root_cause_code = "" if kwargs["root_cause_code"] is None else kwargs["root_cause_code"]
				attribs_a.append({'ATTR_ID': _field_map["root_cause_code"], 'ATTR_VALUE': root_cause_code})
				root_cause_updated = True

			while nth_attempt < n_attempts:
				time.sleep(n_secs)
				try:
					rfc.BAPI_DISPUTE_ATTRIBUTES_CHANGE(
						rfc.connection, case_guid,
						attributes = attribs_a,
					)
				except rfc.CaseLockedError as exc:
					g_log.debug(str(exc))
					nth_attempt += 1
					g_log.debug(f"Attempt # {nth_attempt} to handle the 'CaseLockedError' exception ...")
				else:
					if nth_attempt != 0:
						g_log.debug("Exception successfully handled.")
					nth_attempt = 0 # reset attempt counter
					break

			if nth_attempt == n_attempts:
				raise RuntimeError("Attempts to handle the 'CaseLockedError' failed!")

			g_log.debug(f"Status changed to {new_status}.")

			curr_status += 1

	attribs_b = []

	for key, val in kwargs.items():

		if key == "status":
			continue

		if key == "root_cause_code":
			if root_cause_updated:
				continue

		if val is None:
			continue

		attribs_b.append({'ATTR_ID': _field_map[key], 'ATTR_VALUE': val})

	while nth_attempt < n_attempts:
		time.sleep(n_secs)
		try:
			rfc.BAPI_DISPUTE_ATTRIBUTES_CHANGE(
				rfc.connection, case_guid,
				attributes = attribs_b,
			)
		except rfc.CaseLockedError as exc:
			g_log.debug(str(exc))
			nth_attempt += 1
			g_log.debug(f"Attempt # {nth_attempt} to handle the 'CaseLockedError' exception ...")
		else:
			if nth_attempt != 0:
				g_log.debug("Exception successfully handled.")
			nth_attempt = 0 # reset attempt counter
			break

	if nth_attempt == n_attempts:
		raise RuntimeError("Attempts to handle the 'CaseLockedError' failed!")
