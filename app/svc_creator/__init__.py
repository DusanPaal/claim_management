# pylint: disable = W1203, C0301, W0718, C0302

"""Core of the claim creation and updating component."""

from os.path import join
from math import isclose

from ... import logger
from ...base import Manager
from ...controller import ClaimLocks, Lock
from ...parsers import PrimitiveParser
from ...resources import database as db
from ...resources import mails
from ...resources.files import (
	APP_ROOT, CaseID, Directory,
	DirPath, File, FileManager,
	FileNameFormatError, Reader,
	RecordID)

from . import accmaps
from .compiler import Claim

try:
	from ...resources.sap import dms, qm, rfc, se16, zqm
except ImportError as imperr:
	print(f"Error importing module: {str(imperr)}")

g_log = logger.get_global_logger()


class ClaimManager(Manager):
	"""Manage processing of customer claims."""

	_cfg = None
	_table = None
	_account = None
	_country = None
	_rules_map = None
	_acc_maps = None
	_task_lock = None

	_countries = ("germany", "austria", "switzerland")

	def __init__(self, order_str: str) -> None:
		"""
		Create the claim control manager.

		Params:
		-------
		order_str:
			Order string of the task
			started by the Task Manager.
		"""

		log_path = logger.get_log_path(
			order_str, subdir = "claims", task = "claims")
		log_cfg = join(APP_ROOT, "log_config.yaml")
		logger.initialize(log_path, log_cfg)

		g_log.info("=== Initializing claim control manager ===")
		self._task_lock = Lock(ClaimLocks.MANAGER)

		if self._task_lock.exists():
			g_log.info("Releasing task lock...")
			self._task_lock.release()
			g_log.info("Task lock released.")

		g_log.info("Loading application configuration ...")
		cfg_path = join(APP_ROOT, "app_config.yaml")
		self._cfg = Reader(cfg_path).read()
		g_log.info("Configuration loaded.")

		g_log.info("Loading SAP processing rules ...")
		self._rules_map = self._load_processing_rules()
		g_log.info("Rules loaded.")

		g_log.info("Loading account maps ...")
		self._acc_maps = accmaps.MapLoader().load()
		g_log.info("Maps loaded.")

		g_log.info("Connecting to database ...")
		db.connect(
			self._cfg["database"]["host"],
			self._cfg["database"]["port"],
			self._cfg["database"]["name"],
			self._cfg["database"]["user"],
			self._cfg["database"]["password"],
			self._cfg["database"]["debug"]
		)
		g_log.info("Connection created.")

		g_log.info("Fetching data table ...")
		self._table = db.get_table(
			self._cfg["database"]["table"],
			self._cfg["database"]["schema"]
		)
		g_log.info("Table fetched.")

		g_log.info("Connecting to email account ...")
		self._account = mails.get_account(
			self._cfg["mails"]["connection"]["mailbox"],
			self._cfg["mails"]["connection"]["user_account"],
			self._cfg["mails"]["connection"]["server"]
		)
		g_log.info("Connection created.")

		g_log.info("Connecting to SAP backend system ...")
		system = self._cfg["sap"]["active_system"]
		rfc_cfg = self._cfg["sap"]["connections"][system]

		rfc.connect(
			user = rfc_cfg["user"],
			passwd = rfc_cfg["passwd"],
			ashost = rfc_cfg["ashost"],
			sysnr = rfc_cfg["sysnr"],
			client = rfc_cfg["client"]
		)
		g_log.info("Connection created.")

		g_log.info("=== Claim control manager initialized ===")

	def __del__(self) -> None:
		"""Release resources allocated by the service."""

		g_log.info("=== Releasing claim control manager ===")

		g_log.info("Closing connection to database ...")
		db.disconnect()
		g_log.info("Connection closed.")

		g_log.info("Closing connection to SAP ...")
		rfc.disconnect()
		g_log.info("Connection closed.")

		g_log.info("=== Claim control manager released ===")

	def _reset_sap_connection(self) -> None:
		"""Reset the connection to SAP."""

		g_log.info("Resetting connection to SAP ...")
		rfc.disconnect()

		system = self._cfg["sap"]["active_system"]
		rfc_cfg = self._cfg["sap"]["connections"][system]

		rfc.connect(
			user = rfc_cfg["user"],
			passwd = rfc_cfg["passwd"],
			ashost = rfc_cfg["ashost"],
			sysnr = rfc_cfg["sysnr"],
			client = rfc_cfg["client"]
		)
		g_log.info("Connection reset.")

	def _load_processing_rules(self) -> dict:
		"""
		Loads parameters required for
		processing of document data in SAP.

		Returns:
		--------
		A dict of customer names and the
		respective processing parameters.
		"""
		rules = {}
		rules_dir = Directory(join(APP_ROOT, "engine", "claim", "core", "rules"))
		file_paths = rules_dir.list_dir(ext = ".yaml", recursive = True)

		# customer specific rules
		for file_path in file_paths:

			rule_file = File(file_path)
			cust_name = rule_file.dir_name
			rule_name = rule_file.fullname

			g_log.info(f"Loading processng rule: '{rule_name}' ...")
			data: dict = rule_file.read()

			if "template_id" not in data:
				g_log.error(f"Parameter 'template_id' missing from rules: '{rule_name}'!")
				continue

			if "kind" not in data:
				g_log.error(f"Parameter 'kind' missing from rules: '{rule_name}'!")
				continue

			if "category" not in data and data["kind"] == "debit":
				g_log.error(f"Parameter 'category' missing from rules: '{rule_name}'!")
				continue

			if "company_code" not in data:
				g_log.error(f"Parameter 'company_code' missing from rules: '{rule_name}'!")
				continue

			if "threshold" not in data:
				g_log.error(f"Parameter 'threshold' missing from rules: '{rule_name}'!")
				continue

			if "tolerance" not in data:
				g_log.error(f"Parameter 'tolerance' missing from rules: '{rule_name}'!")
				continue

			if data.get("category") in ("bonus", "promo", "quality"):

				if "case_add" in data:
					g_log.error(
						"The processing rules '%s' contain action 'case_add' which is not valid "
						"for documents of category '%s'!", rule_name, data["category"])
					g_log.warning("The action 'case_add' will be therefore removed from the rules.")
					del data["case_add"]

				if "user" in data["claim_create"]:
					g_log.error(
						"Action 'claim_create' in processing rules '%s' contains parameter 'user' which "
						"is not valid for documents of category '%s'!", rule_name, data["category"])
					g_log.warning("The parameter 'user' will be therefore removed from the 'claim_create' action.")
					del data["claim_create"]["user"]

			if cust_name not in rules:
				rules.update({cust_name: []})

			data.update({"name": rule_name})
			rules[cust_name].append(data)

		return rules

	def _get_user_control(self, rec_id: int) -> str:
		"""
		Return the name of a user control
		category applied to a message.
		"""

		ctrl = db.get_value(
			self._table, int(rec_id),
			col = "control_category"
		)

		return ctrl

	def _refers_to_account(self, claim: Claim) -> bool:
		"""
		Check if a service notification should be
		created with reference to a customer account.
		"""
		return claim.notification["create"]["reference_by"] in ("account_number", "head_office_number")

	def _exists_qm_notification(self, claim: Claim) -> list:
		"""
		Check if any YZ-type service notification exists
		referring to the document invoice or delivery note.

		Assumes that any reference documents such as invoice or delivery
		numbers were wither available in the data or gathered form SAP.

		If a notification for the given document data already exists,
		then the ID number of the notification is returned. Otherwise,
		None is returned.
		"""

		inv_nums = claim.notification["create"].get("invoice_number", [])
		deliv_nums = claim.notification["create"].get("delivery_number", [])

		if len(inv_nums) + len(deliv_nums) == 0:
			# if invoice and delivery numners is not available,
			# there's no other way to verify the existence of an SN
			g_log.info(
				"No invoice or delivery note number is available to verify "
				"that the corresponding service notification(s) exists.")
			return []

		inv_notifs = []
		deliv_notifs = []

		for inv_num in inv_nums:
			g_log.info(
				"Searching for any existing service notifications "
				f"using invoice number: {inv_num} ...")
			inv_notifs += se16.find_notifications(se16.Invoice(inv_num))

		for deliv_num in deliv_nums:
			g_log.info(
				"Searching for any existing service notifications "
				f"using delivery note number: {deliv_num} ...")
			deliv_notifs += se16.find_notifications(se16.Delivery(deliv_num))

		if len(inv_notifs + deliv_notifs) == 0:
			g_log.info(
				"No previous YZ-type (QM) service notification "
				"was found for the delivery note or the invoice.")
			return []

		if len(inv_notifs) > 0:
			g_log.info(
				f"Found {len(inv_notifs)} YZ-type (QM) service notification(s): "
				f"{inv_notifs} associated with invoice(s): {inv_nums}"
			)

		if len(deliv_notifs) > 0:
			g_log.info(
				f"Found {len(deliv_notifs)} YZ-type (QM) service notification(s): "
				f"{deliv_notifs} associated with the delivery note(s): {deliv_nums}"
			)

		notifs = list(set(inv_notifs + deliv_notifs))
		notifs = list(map(int, notifs))

		return notifs

	def _exist_dms_cases(self, claim: Claim) -> bool:
		"""Check if document-related case already exists in DMS."""

		g_log.info("Searching for existing DMS cases ...")
		amount = claim.case["search"].get("cust_disputed")
		title = claim.case["search"]["title"]
		comp_code = claim.company_code
		tolerance = claim.tolerance
		states = [1, 2, 3]

		records = dms.find_cases(title, comp_code, amount, tolerance, states)

		if len(records) >= 1:
			case_id_nums = [rec["case_id"] for rec in records]
			g_log.warning(f"Document already exists in DMS under case ID(s): {case_id_nums}.")
		else:
			g_log.info("No DMS cases referring to the document were found.")

		return len(records) != 0

	def _create_zqm_notification(self, claim: Claim, pdf_dir: str, rec_id: RecordID) -> CaseID:
		"""Manage creating a ZQM25-type service notification."""

		g_log.info("Creating ZQM25 notification ...")

		reference_by = claim.notification["create"]["reference_by"]
		ref_by = claim.notification["create"][reference_by]
		ref_no = claim.notification["create"]["reference_no"]
		amount = claim.notification["create"]["amount"]
		att_name = claim.notification["create"]["attachment_name"]
		description = claim.notification["create"]["description"]
		coordinator = claim.notification["create"]["coordinator"]
		processor = claim.notification["create"]["processor"]
		responsible = claim.notification["create"].get("responsible")
		stat_ac = claim.create_status_ac()

		notif_id, case_id, case_guid = zqm.create_notification(
			acc = zqm.Account(ref_by),
			reference_no = ref_no,
			desc = description,
			category_name = claim.category,
			amount = amount,
			company_code = claim.company_code
		)

		g_log.info(f"Notification {notif_id} successfully created, case ID: {case_id}")

		g_log.info("Updating DMS case parameters ...")
		root_cause = "L14" if amount < claim.threshold else None
		case_status = 3 if amount < claim.threshold else 1

		dms.modify_case_params(
			case_guid,
			coordinator = coordinator,
			processor = processor,
			responsible = responsible,
			root_cause_code = root_cause,
			status = case_status,
			status_ac = stat_ac
		)

		g_log.info("Case parameters successfully updated.")

		# attaching pdf comes as the last step - sholuld any problem occur
		# while attaching the file, updating of params in DMS won't be affected.
		g_log.info("Attaching document to DMS case ...")
		att_name = claim.create_attachment_name(att_name, case_id)
		pdf_paths = Directory(pdf_dir).list_dir(rec_id, ext = ".pdf")
		dms.attach(case_guid, pdf_paths[0], att_name)
		g_log.info("Document successfully attached.")

		FileManager.rename_files(pdf_dir, att_name, rec_id, ext = ".pdf")
		FileManager.remove_files(pdf_dir, rec_id)

		return CaseID(case_id)

	def _create_qm_notification(self, claim: Claim, pdf_dir: DirPath, rec_id: RecordID) -> CaseID:
		"""Cerate a new QM01-type service notification."""

		ref_no = claim.notification["create"]["reference_no"]
		amount = claim.notification["create"]["amount"]
		att_name = claim.notification["create"]["attachment_name"]
		desc = claim.notification["create"]["description"]
		user = claim.notification["create"]["user"]
		coordinator = claim.notification["create"]["coordinator"]
		processor = claim.notification["create"]["processor"]
		reference_by = claim.notification["create"]["reference_by"]
		responsible = claim.notification["create"].get("responsible")
		stat_ac = claim.create_status_ac()
		warehouse_id = None

		if reference_by is None:
			# no notification was found, so creating a
			# new one is not possible without a reference
			raise RuntimeWarning("Unable to create a service notification without a reference!")

		if reference_by in ("account_number", "head_office_number"):
			g_log.info("Creating QM01 notification using customer account as a reference ...")
			acc = claim.notification["create"][reference_by]
			ref_by = qm.Account(acc)
		elif reference_by == "delivery_number":
			delivery_numbers = claim.notification["create"]["delivery_number"]
			delivery_number = delivery_numbers[0]
			if len(delivery_numbers) > 1:
				g_log.warning(
					"More than one delivery note was associated with the document. "
					f"The first value {delivery_number} will be used to create the claim.")
			g_log.info("Creating QM01 notification using the delivery note number as a reference ...")
			ref_by = qm.Delivery(delivery_number)
		elif reference_by == "invoice_number":
			invoice_numbers = claim.notification["create"]["invoice_number"]
			if len(invoice_numbers) > 1:
				invoice_number = invoice_numbers[0]
				g_log.warning(
					"More than one invoice was associated with the document. "
					f"The first value {invoice_number} will be used to create the claim.")
			invoice_number = invoice_numbers[0]
			g_log.info("Creating QM01 notification using invoice number as a reference ...")
			ref_by = qm.Invoice(invoice_number)
		else:
			raise ValueError(f"Unrecognized reference by: {reference_by}!")

		# NOTE: docasny fix na sklady kym sa neprezisti
		# ci priorita je vobec potrebna pre notifikacie
		if reference_by in ("delivery_number", "invoice_number"):
			if "delivery_number" in claim.notification["create"]:
				deliv_num = claim.notification["create"]["delivery_number"][0]
				warehouse_id = se16.get_shipping_point(qm.Delivery(deliv_num))

		g_log.info(f"Warehouse ID (shipping point): {logger.quotify(warehouse_id)}")

		notif_id, case_id, case_guid = qm.create_notification(
			reference_by = ref_by,
			reference_no = ref_no,
			amount = amount,
			threshold = claim.threshold,
			coordinator = user,
			description = desc,
			category_name = claim.category,
			company_code = claim.company_code,
			shipping_point = warehouse_id
		)

		g_log.info(f"Notification {notif_id} successfully created, case ID: {case_id}")

		g_log.info("Updating DMS case parameters ...")
		root_cause = "L14" if amount < claim.threshold else None
		case_status = 3 if amount < claim.threshold else 1

		dms.modify_case_params(
			case_guid,
			coordinator = coordinator,
			processor = processor,
			responsible = responsible,
			root_cause_code = root_cause,
			status = case_status,
			status_ac = stat_ac
		)

		g_log.info("Case parameters successfully updated.")

		# attaching pdf comes as the last step - sholuld any problem occur
		# while attaching the file, updating of params in DMS won't be affected.
		g_log.info("Attaching document to DMS case ...")
		att_name = claim.create_attachment_name(att_name, case_id)
		pdf_paths = Directory(pdf_dir).list_dir(rec_id, ext = ".pdf")
		dms.attach(case_guid, pdf_paths[0], att_name)
		g_log.info("Document successfully attached.")

		FileManager.rename_files(pdf_dir, att_name, rec_id, ext = ".pdf")
		FileManager.remove_files(pdf_dir, rec_id)

		return CaseID(case_id)

	def _create_dms_case(
			self, claim: Claim, notif_cfg: dict, notifs: list,
			pdf_dir: DirPath, rec_id: RecordID) -> CaseID:
		"""Create a new case for an existing QM01-type service notification."""

		cust_disputed = claim.notification["extend"]["amount"]
		coordinator = claim.notification["extend"]["coordinator"]
		processor = claim.notification["extend"]["processor"]
		responsible = claim.notification["extend"].get("responsible")
		att_name = claim.notification["extend"]["attachment_name"]
		ref_no = claim.notification["extend"]["reference_no"]
		desc = claim.notification["extend"]["description"]

		if notif_cfg["duplicates"] == "first":
			g_log.warning(
				"More than one notification found! "
				"The oldest one will be used to create the claim.")
			notif_id = min(notifs)
		if notif_cfg["duplicates"] == "last":
			g_log.warning(
				"More than one notification found! "
				"The latest one will be used to create the claim.")
			notif_id = max(notifs)
		if notif_cfg["duplicates"] == "error":
			raise RuntimeError(
				"More than one notification found! "
				"The creation of a DMS case requires "
				"the existence of a single notification."
			)

		g_log.info("Adding new case to the service notification ...")
		while True:
			try:
				case_id, case_guid = qm.add_case(
					notif_id = int(notif_id),
					category_name = claim.category,
					company_code = claim.company_code,
					threshold = claim.threshold,
					amount = cust_disputed,
					reference_no = ref_no,
					title = desc
				)
			except rfc.NotificationDeletedError as exc:
				g_log.error(exc)
				notifs.remove(notif_id)
				notif_id = min(notifs)
				g_log.info(f"Attempting to use the oldest available notification: {notif_id} ...")
			else:
				break

		g_log.info(f"Notification successfully updated on case ID: {case_id}")

		g_log.info("Updating DMS case parameters ...")
		root_cause = "L14" if cust_disputed < claim.threshold else None
		case_status = 3 if cust_disputed < claim.threshold else 1
		orig_stat_ac = dms.get_case_parameters(case_guid)["status_ac"]
		new_stat_ac = claim.create_status_ac(orig_stat_ac)

		dms.modify_case_params(
			case_guid,
			coordinator = coordinator,
			processor = processor,
			responsible = responsible,
			root_cause_code = root_cause,
			status = case_status,
			status_ac = new_stat_ac
		)

		g_log.info("Case parameters successfully updated.")

		# attaching pdf comes as the last step - sholuld any problem occur
		# while attaching the file, updating of params in DMS won't be affected.
		g_log.info("Attaching document to DMS case ...")
		att_name = claim.create_attachment_name(att_name, case_id)
		pdf_paths = Directory(pdf_dir).list_dir(rec_id, ext = ".pdf")
		dms.attach(case_guid, pdf_paths[0], att_name)
		g_log.info("Document successfully attached.")

		FileManager.rename_files(pdf_dir, att_name, rec_id)

		return CaseID(case_id)

	def _creditnote_recorded(self, claim: Claim) -> str:
		"""
		Check if a credit note is already recorded in DMS.

		Params:
		-------
		claim: Parameters and values that represent a claim.

		Returns:
		--------
		The GUID identification string if a case exists witout a recorded credit note.
		If a case exists with a recorded credit note, tehn None is returned.

		Raises:
		-------
		RuntimeError: If multiple matches were found in DMS.
		"""

		g_log.info("Searching DMS for any existig cases related to the credit note ...")

		title = claim.case["search"]["title"]
		doc_amount = claim.case["search"]["cust_disputed"]
		tolerance = claim.tolerance

		records = dms.find_cases(title, claim.company_code, states = [1, 2, 3])

		if len(records) == 0:
			raise RuntimeWarning("No corresponding case exists in DMS for the credit note.")

		if len(records) > 1:
			raise RuntimeWarning(
				"Multiple disputes found! To record a credit note, "
				"only one DMS case that is not devaluated must exist!")

		case_guid = records[0]["case_guid"]
		case_params = dms.get_case_parameters(case_guid)
		case_id = int(case_params["case_id"])
		prev_stat_sl = case_params["status_sales"]
		prev_root_cause = case_params["root_cause_code"]
		case_amount = PrimitiveParser().parse_number(case_params["disputed_amount"])
		g_log.info(f"Found DMS record with case ID: {case_id}")

		if doc_amount < case_amount:
			g_log.warning(
				f"The credit note matched the case ID: {case_id} on the document number, "
				f"but the case amount: {case_amount} is greater than the document amount: "
				f"{doc_amount}. Therefore, the case is not considered a full match.")

		amounts = PrimitiveParser().find_numbers(prev_stat_sl)

		for found_amount in amounts:
			if isclose(found_amount, doc_amount, abs_tol = tolerance):
				if prev_root_cause in ("L01", "L06", "L14"):
					g_log.info(f"Found credit note recorded in case ID: {case_id}.")
					return None

		g_log.info("The case doesn't contain such credit note record.")

		return case_guid

	def _record_creditnote(
			self, claim: Claim, case_guid: str,
			pdf_dir: DirPath, rec_id: RecordID) -> CaseID:
		"""Records a credit note issued by the customer to a DMS case."""

		g_log.info("Recording the credit note to DMS ...")

		document_amount = claim.case["update"]["amount"]
		st_sales_rule = claim.case["update"]["status_sales"]
		att_namerule = claim.case["update"]["attachment_name"]
		coordinator = claim.case["update"]["coordinator"]
		processor = claim.case["update"]["processor"]
		responsible = claim.case["update"].get("responsible")

		case_params = dms.get_case_parameters(case_guid)
		disp_amount = PrimitiveParser().parse_number(case_params["disputed_amount"])

		g_log.info("Compiling new case parameters ...")
		case_id = int(case_params["case_id"])
		root_cause_code = case_params["root_cause_code"]
		status = int(case_params["status"])

		new_stat_sl = claim.create_status_sales(
			status_sales = case_params["status_sales"],
			amount = document_amount,
			gen_rule = st_sales_rule,
		)

		if disp_amount > claim.threshold and root_cause_code not in ("L01", "L06"):
			new_root_cause = "L01"
		else:
			new_root_cause = None

		diff = disp_amount - document_amount

		if diff < claim.threshold and status == 1:
			new_status = 2
		else:
			new_status = None

		g_log.info("Parameters succeccfully compiled.")

		g_log.info("Updating the DMS case on the compiled parameters ...")
		dms.modify_case_params(
			case_guid,
			processor = processor,
			coordinator = coordinator,
			responsible = responsible,
			root_cause_code = new_root_cause,
			status_sales = new_stat_sl,
			status = new_status,
			reason = "XXX"
		)
		g_log.info("Parameters successfully updated.")

		# attaching pdf comes as the last step - sholuld any problem occur
		# while attaching the file, updating of params in DMS won't be affected.
		g_log.info("Attaching document to DMS case ...")
		att_name = claim.create_attachment_name(att_namerule, case_id)
		pdf_paths = Directory(pdf_dir).list_dir(rec_id, ext = ".pdf")
		dms.attach(case_guid, pdf_paths[0], att_name)
		g_log.info("Document successfully attached.")

		FileManager.rename_files(pdf_dir, att_name, rec_id, ext = ".pdf")
		FileManager.remove_files(pdf_dir, rec_id)

		g_log.info(f"The credit note was successfully recorded to case: {case_id}.")

		return CaseID(case_id)

	def _update_case(
			self, claim: Claim, case_guid: str,
			pdf_dir: DirPath, rec_id: RecordID) -> CaseID:
		"""Updates an existing case in DMS."""

		g_log.info("Updating the existing case in DMS ...")

		document_amount = claim.case["update"]["amount"]
		st_sales_rule = claim.case["update"]["status_sales"]
		att_namerule = claim.case["update"]["attachment_name"]
		coordinator = claim.case["update"].get("coordinator") # optional param in the rule
		processor = claim.case["update"].get("processor")     # optional param in the rule
		responsible = claim.case["update"].get("responsible") # optional param in the rule

		case_params = dms.get_case_parameters(case_guid)
		disp_amount = PrimitiveParser().parse_number(case_params["disputed_amount"])

		g_log.info("Compiling new case parameters ...")
		case_id = int(case_params["case_id"])

		new_stat_sl = claim.create_status_sales(
			status_sales = case_params["status_sales"],
			amount = document_amount,
			gen_rule = st_sales_rule,
		)
		g_log.info("Parameters succeccfully compiled.")

		g_log.info("Updating the DMS case on the compiled parameters ...")
		dms.modify_case_params(
			case_guid,
			processor = processor,
			coordinator = coordinator,
			responsible = responsible,
			status_sales = new_stat_sl,
			disputed_amount = disp_amount
		)
		g_log.info("Parameters successfully updated.")

		# attaching pdf comes as the last step - sholuld any problem occur
		# while attaching the file, updating of params in DMS won't be affected.
		g_log.info("Attaching document to DMS case ...")
		att_name = claim.create_attachment_name(att_namerule, case_id)
		pdf_paths = Directory(pdf_dir).list_dir(rec_id, ext = ".pdf")
		dms.attach(case_guid, pdf_paths[0], att_name)
		g_log.info("Document successfully attached.")

		FileManager.rename_files(pdf_dir, att_name, rec_id, ext = ".pdf")
		FileManager.remove_files(pdf_dir, rec_id)

		g_log.info(f"The credit note was successfully recorded to case: {case_id}.")

		return CaseID(case_id)

	def _move_files(
			self, src: DirPath, dst: DirPath, doc_status: str,
			rec_id: RecordID, case_id: CaseID = None) -> None:
		"""Move processed files to a destination folder.

		Params:
		-------
		src: Path to source file directory.
		dst: Path to destination file directory.
		doc_status: Text denoting document processing status.
		rec_id: A unique number under which the document is stored in the database.
		case_id: A unique number under which the document-related case is registered in DMS.

		Returns:
		--------
		File types and their respective new locations.
		"""

		if case_id is not None:
			id_num = case_id
			g_log.info("Storing the case ID to database ...")
			db.update_record(self._table, int(rec_id), case_id = int(case_id))
			g_log.info("Case ID successfully stored.")
		else:
			id_num = rec_id

		try:
			new_paths = FileManager.move_files(src, dst, id_num)
		except Exception as exc:
			g_log.error(str(exc))
			return

		g_log.info("Updating database record ...")
		db.update_record(self._table, int(rec_id), doc_status = doc_status, link = new_paths["pdf"])
		g_log.info("Record successfully updated.")

	def _list_json_files(self, src: DirPath, deepcheck: bool = False) -> dict:
		"""Create list of json files containing data extracted form customer documents.

		Params:
		-------
		src: Path to the directory where JSONs are stored.

		Note:
		----
		Each JSON file must contain a record ID number.

		A JSON file will be excluded form processing if:
		- database record ID is not found in the file name
		- more than one PDF file exist with the same record ID as the JSON file
		- no PDF file exists with the same record ID as the JSON file

		Returns:
		--------
		A list of records with JSON file path, JSON file name, and the record ID.

		Example:
		--------
		>>> list_json_files('C:\\src_dir)
		>>> [
				{
					'json_path': 'obi_de_retoure_id=125478.json',
					'file_name': 'obi_de_retoure_id=125478',
					'record_id': 125478
				},

				{
					'json_path': 'roller_at_retoure_id=125478.json',
					'file_name': 'roller_at_retoure_id=125478',
					'record_id': 125478
				},
			]
		"""

		doc_files = []
		src = Directory(src)

		for json_path in src.list_dir(ext = ".json"):

			json_file = File(json_path)
			record = {}

			try:
				rec_id = json_file.extract_record_id()
			except FileNameFormatError as exc:
				g_log.error(str(exc))
				continue

			if deepcheck:

				pdf_files = src.list_dir(rec_id, ext = ".pdf")
				n_files = len(pdf_files)

				if n_files == 0:
					g_log.error("PDF document for the ID %d not found!", rec_id)
					g_log.warning("The document won't be processed.")
					continue

				if n_files > 1:
					g_log.error(
						"A single pdf file expected for record ID: %d, "
						"but found %d such files!", rec_id, n_files)
					g_log.warning("The document won't be processed.")
					continue

			record.update({
				"json_path": json_path,
				"file_name": json_file.name,
				"record_id": rec_id
			})

			doc_files.append(record)

		return doc_files

	def execute(self) -> None:
		"""
		Execute the claim management request.

		kwargs:
		-------
		country: Name of the country to process.
		"""

		notif_cfg = self._cfg["processing"]["notifications"]
		dirs = self._cfg["dirs"]
		src_dir = dirs["upload"]

		g_log.info("Creating list of document data files ...")
		json_paths = self._list_json_files(src_dir, deepcheck = False)
		n_total = len(json_paths)
		g_log.info(f"Found {n_total} files to process.\n")

		if n_total == 0:
			g_log.info("=== Processing aborted ===\n")
			return

		prev_comp_code = None

		for nth, item in enumerate(json_paths, start = 1):

			if self._task_lock.exists():
				g_log.info("=== Processing cancelled ===\n")
				return

			logger.section_break(g_log, tag = f" Document {nth}/{n_total} ")
			g_log.info("Document name: '%s'.", item["file_name"])

			data = Reader(item["json_path"]).read()

			rec_id = item["record_id"]
			rec = db.get_record(self._table, int(rec_id))
			msg = mails.get_message(self._account, rec["message_id"])

			try:
				claim = Claim(data, self._rules_map, self._acc_maps)
			except Exception as exc:
				g_log.exception(exc)
				g_log.error("Claim compilation failed!")
				self._move_files(src_dir, dirs["failed"], "processing_error", rec_id)
				mails.append_text(msg, "G.ROBOT_RFC (ERROR): Document processing in SAP failed!")
				continue

			# To ensure correct case ID numbering, the SAP connection must be
			# must be reset each time the program encounters a company code
			# different from that of the previously processed document.
			if claim.company_code != prev_comp_code and prev_comp_code is not None:
				self._reset_sap_connection()

			prev_comp_code = claim.company_code
			ctrl_categ = self._get_user_control(rec_id)
			g_log.warning(f"Message control category found: {logger.quotify(ctrl_categ)}")

			if ctrl_categ == "IGNORE_ALREADY_EXISTING":
				# this type of cotrol applies to debit notes only
				if claim.kind == "debit":
					g_log.warning(
						"The user requested to ignore any existing "
						"duplicates in DMS and create a new case.")
				elif claim.kind == "credit":
					g_log.warning(
						"The control category applied by the user is not "
						"applicable for credit notes and will be ignored.")

			try:

				if claim.transaction == "ZQM":
					if not self._exist_dms_cases(claim) or ctrl_categ == "IGNORE_ALREADY_EXISTING":
						case_id = self._create_zqm_notification(claim, src_dir, rec_id)
						self._move_files(src_dir, dirs["done"], "completed", rec_id, case_id)
					elif "BAHAG" in claim.header["issuer"]:
						raise RuntimeError(
							"Duplicated documents issued by BAHAG! Such documents "
							"are to be processed manuallly by accountants.")
					else:
						self._move_files(src_dir, dirs["duplicate"], "duplicate", rec_id)
				elif claim.transaction == "QM":
					if self._refers_to_account(claim):
						if not self._exist_dms_cases(claim) or ctrl_categ == "IGNORE_ALREADY_EXISTING":
							case_id = self._create_qm_notification(claim, src_dir, rec_id)
							self._move_files(src_dir, dirs["done"], "completed", rec_id, case_id)
						elif "BAHAG" in claim.header["issuer"]:
							raise RuntimeError(
								"Duplicated documents issued by BAHAG! Such documents "
								"are to be processed manuallly by accountants.")
						else:
							self._move_files(src_dir, dirs["duplicate"], "duplicate", rec_id)
					else:

						notifs_id = self._exists_qm_notification(claim)

						if len(notifs_id) == 0:
							if self._exist_dms_cases(claim):
								if ctrl_categ == "IGNORE_ALREADY_EXISTING":
									case_id = self._create_qm_notification(claim, src_dir, rec_id)
									self._move_files(src_dir, dirs["done"], "completed", rec_id, case_id)
								else:
									g_log.warning( # moze byt omylom zalozene na iny document
										"No YZ-type notification was found using the specified reference(s), "
										"but a DMS case exists. The document is considered a duplicate.")
									if "BAHAG" in claim.header["issuer"]:
										raise RuntimeError(
											"Duplicated documents issued by BAHAG! Such documents "
											"are to be processed manuallly by accountants.")
									self._move_files(src_dir, dirs["duplicate"], "duplicate", rec_id)
							else:
								case_id = self._create_qm_notification(claim, src_dir, rec_id)
								self._move_files(src_dir, dirs["done"], "completed", rec_id, case_id)
						elif not self._exist_dms_cases(claim):
							case_id = self._create_dms_case(claim, notif_cfg, notifs_id, src_dir, rec_id)
							self._move_files(src_dir, dirs["done"], "completed", rec_id, case_id)
						elif "BAHAG" in claim.header["issuer"]:
							raise RuntimeError(
								"Duplicated documents issued by BAHAG! Such documents "
								"are to be processed manuallly by accountants.")
						else:
							self._move_files(src_dir, dirs["duplicate"], "duplicate", rec_id)

				elif claim.transaction == "DMS":
					case_guid = self._creditnote_recorded(claim)
					if case_guid is None:
						if "BAHAG" in claim.header["issuer"]:
							raise RuntimeError(
								"Duplicated documents issued by BAHAG! Such documents "
								"are to be processed manuallly by accountants.")
						self._move_files(src_dir, dirs["duplicate"], "duplicate", rec_id)
					else:
						case_id = self._record_creditnote(claim, case_guid, src_dir, rec_id)
						self._move_files(src_dir, dirs["done"], "completed", rec_id, case_id)

			except RuntimeWarning as wng:
				g_log.warning(str(wng))
				g_log.warning("The document-related files won't be moved.")
				g_log.info("Writing warning message to user email ...")
				mails.append_text(msg, f"G.ROBOT_RFC (WARNING): {str(wng)}")
				g_log.info("Message successfully written.")
			except Exception as exc:
				g_log.exception(exc)
				logger.print_data(data, desc = "Document data:", row_list = True)
				g_log.error("Document processing failed!")
				self._move_files(src_dir, dirs["failed"], "processing_error", rec_id)
				g_log.info("Writing error message to user email ...")
				mails.append_text(msg, "G.ROBOT_RFC (ERROR): Document processing in SAP failed!")
				g_log.info("Message successfully written.")
			else:
				g_log.info("Writing info message to user email ...")
				mails.append_text(msg, "G.ROBOT_RFC (INFO): Document successfully processed in SAP.")
				g_log.info("Message successfully written.")
			finally:
				logger.section_break(g_log, n_chars = 37, end = "\n")

		g_log.info("The core control manager has finished processing.")
