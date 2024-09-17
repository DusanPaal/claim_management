# pylint: disable = C0301, W1203, R0903, C0302

"""Claim data compiler"""

import locale
import re
from typing import Union
from ... import logger
from ...resources.sap import va03

g_log = logger.get_global_logger()

class Claim:
	"""Claim context object."""

	_data = None
	_rules = None
	_maps = None

	_categories = {

		"QM": (
			"delivery",
			"finance",
			"invoice",
			"penalty_general",
			"penalty_delay",
			"penalty_quote",
			"price",
			"rebuild",
			"return"
		),

		"ZQM": (
			"bonus",
			"promo",
			"quality",
		),

		"DMS": None # NA for credit notes

	}

	_reference_by = (
		"invoice_number", "delivery_number",
		"account_number", "head_office_number"
	)

	_company_codes = (
		"1001", "1072", "0074"
	)

	_tax_codes = {
		"1001": {
			"": 0.0,
			"AB": 19,
			"AA": 16
		},
		"0074": {
			"": 0.0,
			"IG": 7.7
		},
		"1072": {
			"": 0.0,
			"YR": 20
		}
	}

	_header = {}
	_notification = {}
	_case = {}

	def __init__(self, data: dict, rules: dict, acc_maps: dict) -> None:
		"""
		Create the compiler of claim context data.

		Params:
		-------
		data: Data extracted form a document.
			- "document_number" (`str` or `int`): Document number, either a numeric or an alphanumeric text (stated).
			- "delivery_number" (`int`): NUmber of the delivery note issued by Ledvane (optional).
			- "invoice_number" (`int`): The number of the invoice issued by Ledvance related to the document.
			- "backreference_number" (`str` or `int`):  Number of the original debit note, as stated on some credit notes (irregular).
			- "archive_number" (`int`): Numer of the document in an archivig storage in the customer's database.
			- "purchase_order_number" (`int` or a `list[int]`): Number or a list of numbers of the orders as registered at Ledvance (irregular).
			- "agreement_number" (`int`): The number of the agreement signed by Ledvance and the customer.
			- "return_number" (`int`): Number of the warehouse return document (irregular).
			- "supplier" (`int` or  `str`): Supplier number, always a 'str' (stated).
			- "branch" (`int`): Number of the customer's branch that issued the document, always an 'int' (irregular).
			- "amount" (`float`): Total document amount (mandatory).
			- "reason" (`str` or a list[`str`]): Reason for issung of the debit note (irregular).
			- "tax" (`float`): The percentage used for tax calculation of the docment's gross amount.
			- "identifier"(`str` or `int`): A numeric value used by the customer to internally identify the document.
			- "zip" (`int`): Postal code used to identify the city where the customer's business unit that issued the document is located.
			- "subtotals" (list | float): The subtotals to the document item amounts calculated on a specific item parameters.
			- "items" (list of list[int|float]): A list of the parameters extracted from the claimed items.

		rules_map: Map of customers and the document rules.
		acc_maps: Customer account maps.
		"""

		if data["category"] is not None:
			data["category"] = data["category"].lower()

		data["issuer"] = data["issuer"].replace(" ", "_")

		self._data = data
		self._rules = rules
		self._maps = acc_maps

		self._compile()

	def _generate_description(self, desc_rule: str, **kwargs) -> str:
		"""Generate claim description from rules and data."""

		# get all tokens used in the description rule, with or withut placeholderes
		used_tokens = []
		used_tokens.extend(re.findall(r"^\w+$", desc_rule))
		used_tokens.extend(re.findall(r"<\?*(\w+)>", desc_rule))

		# get optional tokens used in the description rule
		optional_tokens = re.findall(r"<\?+(\w+)>", desc_rule)

		# get non-optional tokens used in the description rule
		required_tokens = set(used_tokens).difference(optional_tokens)

		# check if all parameters for the used tokens are bound
		for param, val in kwargs.items():
			if val is None and param in required_tokens:
				raise UnboundLocalError(
					f"The parameter '{param}' is None, but is "
					"expected to be used in the description!")

		# check if all used tokens are unique
		if len(set(used_tokens)) != len(used_tokens):
			raise ValueError("Duplicated tokens are not allowed!")

		# check if all used tokens are passed as kwargs
		if len(set(used_tokens).intersection(kwargs.keys())) == 0:
			raise ValueError(
				"None of the tokens in description rule "
				"can be replaced by the used params!"
			)

		# at least one non-optional token must be used
		if len(used_tokens) == len(optional_tokens):
			raise ValueError(
				"At least one non-optinal token must "
				"be used in the desription rule!"
			)

		desc = desc_rule

		# remove unused optional tokens from the description rule
		for tok in optional_tokens:
			if kwargs.get(tok) is None:
				desc = re.sub(fr".?<\?+{tok}>", "", desc)

		# remove any delimiters that remain hanging on the left end
		# as a result of removal of the tokens in some scenarios
		desc = re.sub(r"^.(?=<)", "", desc)

		# if there are multiple optional tokens used,
		# prioritize the one with lowest '?' count
		if len(re.findall(r"<\?+\w+>", desc)) > 1:
			desc = re.sub(r"\?", "", desc, count=1)
			desc = re.sub(r".<\?+\w+>", "", desc)

		# replace question marks in the optional tokens left
		desc = re.sub(r"\?+", "", desc)

		# replace tokens with values
		for arg, val in kwargs.items():

			repl = str(val)

			width = self._get_padding_width(arg, desc_rule)

			if width is not None:
				if arg == "branch":
					repl = repl.zfill(width)
				else:
					pass  # open for padding other tokens if needed

				arg = "".join([str(width), arg])

			desc = re.sub(f"<?{arg}>?", repl, desc)

		# if parsing succeeded, there should be no
		# placeholders or tags in the resulting description
		assert re.search(r"<|>|\?", desc) is None, "Parsing failed!"

		# remove any delimiters left from the pattern rule
		desc = re.sub(r"\W$", "", desc)
		desc = re.sub(r"^\W", "", desc)

		assert "None" not in desc, "Parsing failed!"

		return desc

	def create_attachment_name(self, att_rule: str, case_id: int) -> str:
		"""Create a formatted attachment name for a DMS case.

		Params:
		-------
		att_rule: Rule that controls the resulting text format.
		case_id: Case identification number in DMS.

		Returns:
		--------
		The generated attachment name.
		"""

		if "<case_id>" not in att_rule:
			raise ValueError(
				"Placeholder '<case_id>' not found in the formatting rule!")

		return att_rule.replace("<case_id>", str(case_id))

	def create_status_sales(self, status_sales: str, gen_rule: str, amount: float) -> str:
		"""Create a formatted Status Sales text for a DMS case.

		Params:
		-------
		att_rule: Rule that controls the resulting text format.
		case_id: Case identification number in DMS.
		amount: Dcument total amount.

		Returns:
		--------
		The generated Status Sales text.
		"""

		if "<amount>" not in gen_rule:
			raise ValueError("Placeholder '<amount>' not found in the formatting rule!")

		orig_loc = locale.getlocale()
		locale.setlocale(locale.LC_ALL, 'de_DE.UTF-8')
		fmt = locale.currency(amount, grouping = True, symbol = False)
		locale.setlocale(locale.LC_ALL, orig_loc)

		repl = gen_rule.replace("<amount>", fmt)
		new_val = " ".join([status_sales, repl])

		return new_val.strip()

	def _create_case_searchtext(self, search_rule: str, data: dict) -> str:
		"""
		Create a foormatted DMS case searchtext.

		Params:
		-------
		search_rule: Rule that controls the resulting text format.
		data: Data that cntains fields with the values to replace.

		Returns:
		--------
		Formatted text that contains the case ID.
		"""

		# developer may decide to use '*' to denote matching
		# in sap processing rules, but RFC accepts '%' only
		result = search_rule.replace("*", "%")

		placeholders = (
			"<backreference_number>",
			"<document_number>",
			"<invoice_number>",
			"<archive_number>",
			"<identifier>"
		)

		for phdr in placeholders:
			param_name = phdr.replace("<", "").replace(">", "")
			result = re.sub(phdr, str(data.get(param_name, "")), result)
			result = re.sub(param_name, str(data.get(param_name, "")), result)

		# if parsing succeeded, there should be no
		# placeholders or tags left in the resulting title text
		assert re.search(r"<|>|\?", result) is None, "Parsing failed!"
		assert search_rule != result, "Title formatting failed!"
		assert result != "", "Title formatting failed!"
		assert result != "%%", "Title formatting failed!"

		return result

	def _get_padding_width(self, tok: str, desc_rule: str) -> Union[int, None]:
		"""Identify the padding width from a token as the number of chars."""

		match = re.search(fr"(-?\d+){tok}", desc_rule)

		if not match:
			return None

		num = int(match.groups()[0])

		if num < 0:
			raise ValueError(f"Invalid padding width: {num}!")

		return num

	def _get_accounts(self, claim: dict, data: dict, acc_maps: dict) -> tuple:
		"""
		Identifies the customer and head office
		accounts from the data using an account map.
		"""

		issuer = claim["header"]["issuer"]
		acc_map = acc_maps.get(issuer)

		if acc_map is None:
			g_log.info("A customer account map is not available.")
			return (None, None)

		g_log.info("Querying the account map for account numbers ...")

		acc_num = None
		hoff_num = None

		# NOTE: pri niektorych Bahag dokumentoch, napr. Minderlieferung sa
		# supplier z textu netaha z dovodu predchadzania chyb pri parsovani,
		# kedze tieto udaje mozu obsahovat deformity. Pri takychto pripadoch
		# sa pouziva get() na ziskatie odajov z dat.
		if "BAHAG" in issuer:
			acc_num = acc_map.get_account(
				supplier = data.get("supplier"),
				business_unit = data.get("branch")
			)
			hoff_num = acc_map.get_account(
				supplier = data.get("supplier"),
				business_unit = "head_office"
			)
		elif "HAGEBAU" in issuer:
			acc_num = acc_map.get_account(
				business_unit = data.get("branch")
			)
			hoff_num = acc_map.get_account(
				business_unit = "head_office"
			)
		elif "MARKANT" in issuer:
			acc_num = acc_map.get_account(
				supplier = data.get("supplier")
			)
		elif "METRO" in issuer:
			acc_num = acc_map.get_account(
				business_unit = data.get("branch")
			)
			hoff_num = acc_map.get_account(
				business_unit = "head_office"
			)
		elif "OBI" in issuer:
			acc_num = acc_map.get_account(
				supplier = data.get("supplier"),
				business_unit = data.get("branch")
			)
			hoff_num = acc_map.get_account(
				supplier = data.get("supplier"),
				business_unit = "head_office"
			)

		g_log.info(f"Customer account found: {acc_num}")
		g_log.info(f"Head office account found: {hoff_num}")

		return (acc_num, hoff_num)

	def _get_accounting_docs(self, claim_create: dict, data, acc: int = None) -> tuple:
		"""Identify delivery and invoice numbers from the extracted data."""

		inv_num = data.get("invoice_number")
		deliv_num = data.get("delivery_number")
		po_num = data.get("purchase_order_number")

		inv_nums = None
		deliv_nums = None

		# invoice number and delivery note number are available
		if inv_num is not None and deliv_num is not None:
			g_log.info(
				"Accounting documents are already available in the data. "
				f"Invoice number: {inv_num}; delivery note number: {deliv_num}."
			)

			inv_nums = inv_num if isinstance(inv_num, list) else [inv_num]
			deliv_nums = deliv_num if isinstance(deliv_num, list) else [deliv_num]

		# neither invoice number nor delivery note number is available
		elif inv_num is None and deliv_num is None:

			# try using another referencing document to obtain
			# the missing invoice and delivery note numbers.
			# As of now, it's only the purchase order number
			# that can be used for this purpose.
			g_log.info("Invoice and delivery numbers are not available in the document data.")

			if "reference_from" not in claim_create:
				g_log.warning("The data does not contain any other parameter that could be used to retrieve these documents from SAP.")
				return (None, None)

			if claim_create["reference_from"] != "purchase_order_number":
				raise ValueError(f"Unrecognized 'reference_from' value: '{claim_create['reference_from']}'!")

			if isinstance(po_num, list) and len(po_num) > 1:
				po_num = po_num[0]
				g_log.warning(
					"Multiple purchase order numbers were found in the document data, "
					"only the first one will be used to obtain the accounting documents.")

			g_log.info(f"Searching for the invoice and delivery note numbers using purchase order number: {po_num} ...")
			assert "purchase_order_number" in data, "Purchase order number is required to create a notification, but not found in the document data!"

			try:
				acc_docs = va03.find_accounting_documents(va03.PurchaseOrder(po_num), acc)
			except va03.DocumentsNotFoundWarning as wng:
				g_log.warning(str(wng)) # ked existuje sales document ale neexistuje ani faktura ani dodaci list
			except va03.DocumentNotFoundError as exc:
				g_log.error(str(exc)) # ked neexistuje sales document
			else:
				inv_nums = list({rec["invoice"] for rec in acc_docs})
				deliv_nums = list({rec["delivery"] for rec in acc_docs})

			if acc is None and len(acc_docs) > 1:
				# ak by naslo viacero zaznamov sales dokumentov bez pouzitia zakkaznickeho konta ako filtra,
				# takyto pripad sa nesmie spracovat, kedze nie je istota, na ktory sales dokument zakladat
				raise RuntimeError("Multiple records found without using customer account as a filter!")

			g_log.info(f"Invoice number(s) found: {inv_nums}.")
			g_log.info(f"Delivery note numbers found: {deliv_nums}.")

		# delivery note number is available - find the missing invoice number
		elif inv_num is None and deliv_num is not None:

			g_log.info("Invoice number is not available in the document data.")
			g_log.info(f"Searching for the invoice number using the delivery note number {deliv_num} ...")

			try:
				acc_docs = va03.find_accounting_documents(va03.Delivery(deliv_num))
			except va03.InvoiceNotFoundError as exc:
				g_log.error(str(exc))
			else:
				inv_nums = list({rec["invoice"] for rec in acc_docs})
			finally:
				deliv_nums = [deliv_num]

			g_log.info(f"Invoice number(s) found: {inv_nums}.")

		# invoice number is available - find the missing delivery note number
		elif inv_num is not None and deliv_num is None:

			g_log.info("Delivery note number is not available in the document data.")
			g_log.info(f"Searching for the delivery note number using the invoice number {inv_num} ...")

			try:
				acc_docs = va03.find_accounting_documents(va03.Invoice(inv_num))
			except va03.DeliveryNotFoundError as exc:
				g_log.error(str(exc))
			else:
				deliv_nums = list({rec["delivery"] for rec in acc_docs})
			finally:
				inv_nums = [inv_num]

			g_log.info(f"Delivery note numbers found: {deliv_nums}.")

		return (inv_nums, deliv_nums)

	def _create_description(self, desc_rule, data: dict) -> str:
		"""Generate description of the SN."""

		desc = self._generate_description(
			desc_rule,
			invoice_number = data.get("invoice_number"),
			document_number = data.get("document_number"),
			archive_number = data.get("archive_number"),
			agreement_number = data.get("agreement_number"),
			identifier = data.get("identifier"),
			return_number = data.get("return_number"),
			branch = data.get("branch")
		)

		return desc

	def create_status_ac(self, orig_status_ac: str = "") -> str:
		"""
		Modify the formatting rule by replacing a token in the rule
		with a specific value and return the new rule. Supported tokens:
		- "tax_code": placeholder for a specific 2-char tax code that
					  represents a specific tax rate.

		If the formatting rule contains the "+=" operator, this indicates
		that the generated value should be added to an existing "Status AC"
		text in the DMS.

		If the formatting consists of the "+=" token only, then the original
		"Status AC" text won't be changed.

		If the tax rate is not contained in the document data, then an empty
		string will be returned as the new formatting rule which means that
		any existing "Status AC" text in the DMS will be erased.

		The evaluation of the modified formatting rule in terms of the operation
		to perform on the original "Status AC" text is carried out once the
		case ID is identified later in the stage of the claim processing.
		"""

		fmt_rule = self.notification["create"].get("status_ac")

		if fmt_rule is None:
			return None

		if "tax" not in self._data:
			g_log.warning(
				"Tax rate not found in the data extracted from the document. "
				"The program assumes that the tax rate wasn't specified in "
				"the original document.")
			return ""

		tax_rates = self._tax_codes[self.company_code]
		tax_rate = self._data["tax"]
		tax_code = None

		for t_code, t_rate in tax_rates.items():
			if tax_rate == t_rate:
				tax_code = t_code
				break

		if tax_code is None:
			raise RuntimeError(
				"Could not identify a tax code for tax rate: "
				f"{tax_rate} and company code: {self.company_code}")

		result = fmt_rule.replace("tax_code", tax_code)

		if "+=" in result:
			result = result.strip().replace("+=", "")
			result = " ".join([orig_status_ac, result])

		result = result.strip()

		if result == "":
			return None

		return result

	def _get_reference(self, val: Union[int, str, list], claim: dict) -> tuple:
		"""Identify a claim reference and return the reference name and value."""

		g_log.info("Identifying document references ...")

		tr_type = claim["header"]["transaction"]
		assert tr_type in ("QM", "ZQM"), ("Invalid operation! Reference "
		f"idntification is not applicable for transaction '{tr_type}'!")

		# static account numbers
		if isinstance(val, int):
			g_log.info(f"Static account number found: {val}.")
			return ("account_number", val) # NOTE co ale s head officom?

		# ensure categories have a correct reference value
		if tr_type == "ZQM" and val not in ("head_office_number", "account_number"):
			raise ValueError(
				f"Invalid 'reference_by' value: '{val}' for category: 'quality'! "
				"Quality can be referenced by an account or head office number only!"
			)

		# reference name
		if isinstance(val, str):
			used_refs = [val]
		# reference names
		elif isinstance(val, list):
			used_refs = val

		g_log.info(f"Dynamic reference(s) used in processing rules: {used_refs}.")

		# dynamic reference fields contained
		# in data are resulved on runtime
		available_refs = (
			"invoice_number",
			"delivery_number",
			"purchase_order_number",
			"account_number",
			"head_office_number"
		)

		invalid_ref_flds = set(used_refs).difference(available_refs)

		if len(invalid_ref_flds) != 0:
			raise ValueError(
				"Unrecognized 'reference_by' "
				f"value: '{invalid_ref_flds}'!")

		# get any available dynamic reference fields regardless of their vals
		all_refs = set(claim["claim_create"].keys()).intersection(available_refs)

		if len(all_refs) == 0:
			raise RuntimeWarning(
				"No valid reference value found for notification creation. "
				"The application may not be able to process the claim.")

		unused_refs = set(all_refs).difference(used_refs)
		unused_valid_refs = []
		used_valid_refs = []
		all_valid_refs = []

		# get the first available the reference from the list
		# the reference with the highest priority is on the top of the list
		for ref_name in available_refs:

			ref_val = claim["claim_create"].get(ref_name)

			if ref_val is None:
				continue

			if ref_name in used_refs:
				used_valid_refs.append((ref_name, ref_val))
			elif ref_name in unused_refs:
				unused_valid_refs.append((ref_name, ref_val))

			all_valid_refs.append(ref_name)

		g_log.info(f"Dynamic reference(s) that can be used: {all_valid_refs}")

		if len(used_valid_refs) == 0 and len(unused_valid_refs) != 0:
			raise RuntimeError(
				"Attempts to get a valid value for the dynamic references "
				"listed in the 'reference_by' option failed. There are other "
				"references with valid values available that could be used, "
				"but they aren't included in the 'reference_by' parameter list. "
				"Check the processing rules for more details.")
		if len(used_valid_refs) == 0 and len(unused_valid_refs) == 0:
			raise RuntimeError(
				"Attempts to get a valid value for the dynamic references "
				"listed in the 'reference_by' option failed. There aren't "
				"any other references with valid values that could be used to "
				"create the notification.")

		# select the reference with the highest priority that
		# is located at the top of the list of used references
		selected_ref = used_valid_refs[0]

		g_log.info(
			"Dynamic reference (name and value) selected to "
			f"create the notification: {list(selected_ref)}.")

		return selected_ref

	def _get_transaction_type(self, data: dict) -> str:
		"""Identify the claim processing transaction."""

		if data["kind"] == "debit":
			if data["category"] in self._categories["QM"]:
				tr_type = "QM"
			elif data["category"] in self._categories["ZQM"]:
				tr_type = "ZQM"
			else:
				raise ValueError(f"Unrecognized document category: '{data['category']}'!")
		elif data["kind"] == "credit":
			tr_type = "DMS"
		else:
			raise ValueError(f"Unrecognized document kind: '{data['kind']}'!")

		return tr_type

	def _assign_rules(self, data: dict, rules_map: list) -> list:
		"""Match extracted data agains a list of rules."""

		matched = []
		rules = rules_map[data["issuer"]]

		for rule in rules:

			if data["template_id"] != rule["template_id"]:
				continue

			if data["kind"] == "credit":
				matched.append(rule)
			elif data["kind"] == "debit":

				if isinstance(rule["category"], str):
					rule_categs = [rule["category"]]
				else:
					rule_categs = rule["category"]

				if data["category"] in rule_categs:
					matched.append(rule)

		if len(matched) == 0:
			raise RuntimeError("No rule matched the data!")

		if len(matched) > 1:
			raise RuntimeError(
				"A single rule match for the document data "
				f"expected, but matched {len(matched)} rules!")

		return matched[0]

	def _compile(self) -> dict:
		"""
		Apply SAP processing rules to the extacted document data
		and return the claim context object.

		Params:
		-------
		json_path: Path to the file containing data extracted form a document.
		rules_map: Map of customers and the document rules.
		acc_maps: Customer account maps.

		Returns:
		--------
		A dict of claim processing params and their respective values:

		Note:
		-----
		The context object consists of:

			- "header":
				Always in the context object.
				Contains general information about the claim:
					- "category" (`str`): Name of the document category (e.g. 'penalty_delivery')
					- "issuer" (`str`): Uppercased customer name followed by the country code delimited by an underscore(e.g. 'MARKANT_DE')
					- "kind" (`str`): Kind of the docuemnt, either a debit or a credit note (e.g. 'credit')
					- "template_id" (`str`): A string that identifies the mathed template used for data extraction.
					- "transaction" (`str`): Type of the processing transaction (e.g. 'qm')
					- "name" (`str`): Name of the document in local language.
					- "company_code": Company code

			- "claim_create":
				Applicable for debit notes, otherwise an empty `dict`.
				Parameters used to create a service notification:
					- "reference_by" (`str`): Name of the parameter, the value of which is used to reference the new notification.
					- "reference_no" (`str`): Text to enter into the notificarion's "Reference no." field.
					- "description" (`str`): Text to enter into the notificarion's "Description." field.
					- "user" (`str`): Only for notifiaciton created in the "zqm" transaction, otherwise `None`. Name of the person at CS who is responsible for processing of the notification.
					- "processor" (`str`): Name of the person at CS who is responsible for processing of the disputed case.
					- "coordinator" (`str`): Name of the person at CS who coordinates the processing of the disputed case.
					- "attachment_name" (`str`): Naming rule for the DMS case attachment (the plaecholder is resoved to actual value once the case ID is available.)
					- "delivery_number" (list[int] or an empty list): Delivery note number(s) found in SAP if not available in the doc data.
					- "invoice_number" (list[int] or an empty list): Invoice number(s) found in SAP if not available in the doc data.
					- "status_ac" (`str`): Text to enter into the "Status AC" field in DMS.

			- "case_add":
				Applicable for debit notes, otherwise an empty `dict`.
				Parameters used to create a new case for an existing service notification:
					- "reference_no" (`str`): identical with "claim_create"
					- "description" (`str`): identical with "claim_create"
					- "user" (`str`): identical with "claim_create"
					- "processor" (`str`): identical with "claim_create"
					- "coordinator" (`str`): identical with "claim_create"
					- "attachment_name" (`str`): identical with "claim_create"

			- "case_update":
				Applicable for credit notes and debit note corrections, otherwise an empty `dict`.
				Parameters used to update an existing DMS case:
					- "status_sales" (`str`): Text to enter into the "Status sales" field in DMS.
					- "attachment_name" (`str`): identical with "claim_create"
					- "processor" (`str`): identical with "claim_create"
					- "coordinator" (`str`): identical with "claim_create"
					- "status_ac" (`str`): Text to enter into the "Status AC" field in DMS.
					- "cust_disputed" (`float`): Numeric value to enter into the "Cust.-Disputed" field in DMS.
		"""

		g_log.info("Searching for processing rules ...")
		rules = self._assign_rules(self._data, self._rules)
		g_log.info("Rules file matched: '%s'.", rules["name"])

		g_log.info("Compiling claim context object ...")
		tr_type = self._get_transaction_type(self._data)

		claim = {
			"header": {
				"category": self._data["category"],
				"issuer": self._data["issuer"],
				"kind": self._data["kind"],
				"template_id": self._data["template_id"],
				"transaction": tr_type
			}
		}

		# get accounts for debit and credit notes. Although the account is not
		# necessary to assign an account to credit notes, it may be useful when
		# assigning a DMS case to a particular credit note if there are multiple
		# DMS cases found using title and amount.
		acc_num, hoff_num = self._get_accounts(claim, self._data, self._maps)

		# apply rules from rulesets and copy the result to the claim
		for ruleset_name, params in rules.items():

			# add the params to the claim header
			if not isinstance(params, dict):
				if ruleset_name not in claim["header"] and ruleset_name != "name":
					if ruleset_name in ("threshold", "tolerance"):
						claim["header"].update({ruleset_name: float(params)})
					else:
						claim["header"].update({ruleset_name: params})
				continue

			claim.update({ruleset_name: {}})

			# add the ruleset to the claim
			if ruleset_name != "case_search":
				claim[ruleset_name].update({
					"amount": self._data["amount"]
				})

			if ruleset_name == "claim_create":

				inv_nums, deliv_nums = self._get_accounting_docs(
					params, self._data, acc_num
				)

				if deliv_nums is not None:
					claim[ruleset_name].update({
						"delivery_number": deliv_nums,
					})

				if inv_nums is not None:
					claim[ruleset_name].update({
						"invoice_number": inv_nums,
					})

				if acc_num is not None:
					assert isinstance(acc_num, int)
					claim[ruleset_name].update({
						"account_number": acc_num,
					})

				if hoff_num is not None:
					assert isinstance(hoff_num, int)
					claim[ruleset_name].update({
						"head_office_number": hoff_num,
					})

				if len(claim[ruleset_name]) == 0:
					raise RuntimeError(
						"No valid reference parameter found "
						"to create service notification!"
					)

			# evaluate the params of the added ruleset
			# and update the claim accordingly
			for key, val in params.items():

				if ruleset_name == "claim_create":
					if key == "reference_by":
						try:
							ref_name, ref_val = self._get_reference(val, claim)
						except RuntimeWarning as wng:
							g_log.warning(wng)
							# if any related SN already exists, the claim will
							# be processed, otehrwise an error will be raised.
							claim[ruleset_name].update({key: None})
						else:
							new_val = ref_name
							claim[ruleset_name].update({ref_name: ref_val})
					elif key == "description":
						new_val = self._create_description(val, self._data)
					else:
						new_val = val  # just copy the original value
				elif ruleset_name == "case_search":
					if key == "title":
						new_val = self._create_case_searchtext(val, self._data)
					elif key == "account":
						if val == "head_office":
							new_val = hoff_num
						elif val == "customer_account":
							new_val = acc_num
						else:
							raise ValueError("Unrecognized ")
						key = val
					else:
						new_val = self._data[val]
				elif ruleset_name in ("case_add", "case_update"):
					if key == "description":
						new_val = self._create_description(val, self._data)
					elif val in self._data:
						new_val = self._data[val]
					else:
						new_val = val
				else:
					raise ValueError(f"Unrecognized ruleset: {ruleset_name}")

				# finally, store the newly created value
				# or the original value into the claim
				claim[ruleset_name][key] = new_val

		# validate header
		assert claim["header"]["company_code"] in self._company_codes, "Unrecognized company code!"
		assert claim["header"]["transaction"] in self._categories, "Invalid transaction!"
		assert isinstance(claim["header"]["template_id"], str) and len(claim["header"]["template_id"]) == 11, "Invalid template ID!"
		assert isinstance(claim["header"]["threshold"], float) and claim["header"]["threshold"] >= 0, "Invalid treshold!"
		assert isinstance(claim["header"]["tolerance"], float) and claim["header"]["tolerance"] >= 0, "Invalid tolerance!"
		assert claim["header"]["kind"] in ("debit", "credit"), "Invalid document kind!"
		assert isinstance(claim["header"]["issuer"], str), "Issuer not a 'str' type!"
		issuer_tokens = claim["header"]["issuer"].split("_")
		assert len(issuer_tokens) == 2 and len(issuer_tokens[1]) == 2, "Invalid issuer name!"
		categ = claim["header"]["category"]
		assert categ is None or categ in (self._categories["QM"] + self._categories["ZQM"]), f"Invalid category: '{categ}'!"

		# validate case_search
		assert isinstance(claim["case_search"]["title"], str) and claim["case_search"]["title"] != "", "Invalid title!"
		cust_disputed = claim["case_search"].get("cust_disputed")
		assert cust_disputed is None or (isinstance(cust_disputed, float) and cust_disputed > 0), "Invalid amount!"

		# validate claim_create
		if "claim_create" in claim:

			# QM reference by
			assert claim["claim_create"]["reference_by"] in self._reference_by

			if claim["claim_create"]["reference_by"] == "delivery_number":
				deliv_num = claim["claim_create"]["delivery_number"]
				assert deliv_num is None or (isinstance(deliv_num, list) and all(isinstance(num), int) for num in deliv_num)
			elif claim["claim_create"]["reference_by"] == "invoice_number":
				inv_num = claim["claim_create"]["invoice_number"]
				assert inv_num is None or (isinstance(inv_num, list) and all(isinstance(num), int) for num in inv_num)
			elif claim["claim_create"]["reference_by"] == "account_number":
				assert isinstance(claim["claim_create"]["account_number"], int)
			elif claim["claim_create"]["reference_by"] == "head_office_number":
				assert isinstance(claim["claim_create"]["head_office_number"], int)

			# QM Reference number
			refno_tokens = claim["claim_create"]["reference_no"].split(" ")
			assert len(refno_tokens) == 2 and len(refno_tokens[1]) == 2

			# DMS Status AC
			stat_ac = claim["claim_create"].get("status_ac")
			assert stat_ac is None or (isinstance(stat_ac, str))

			# QM Description
			desc = claim["claim_create"]["description"]
			assert isinstance(desc, str) and desc != ""

			# QM Processor-User
			user = claim["claim_create"].get("user")
			assert user is None or (isinstance(user, str) and user != "")

			# DMS person responsible
			resp = claim["claim_create"].get("responsible")
			assert resp is None or (isinstance(resp, str) and resp != "")

			# DMS Processor
			proc = claim["claim_create"]["processor"]
			assert isinstance(proc, str) and proc != ""

			# DMS coordinator
			coord = claim["claim_create"]["coordinator"]
			assert isinstance(coord, str) and coord != ""

			# DMS attachment name
			att_name = claim["claim_create"]["attachment_name"]
			assert isinstance(att_name, str) and att_name != ""

		if "case_add" in claim:

			# QM Reference number
			refno_tokens = claim["case_add"]["reference_no"].split(" ")
			assert len(refno_tokens) == 2 and len(refno_tokens[1]) == 2

			# QM Description
			desc = claim["case_add"]["description"]
			assert isinstance(desc, str) and desc != ""

			# QM Processor-User
			user = claim["case_add"]["user"]
			assert isinstance(user, str) and user != ""

			# DMS Status AC
			stat_ac = claim["case_add"].get("status_ac")
			assert stat_ac is None or (isinstance(stat_ac, str))

			# DMS Processor
			proc = claim["case_add"]["processor"]
			assert isinstance(proc, str) and proc != ""

			# DMS coordinator
			coord = claim["case_add"]["coordinator"]
			assert isinstance(coord, str) and coord != ""

			# DMS person responsible
			resp = claim["case_add"].get("responsible")
			assert resp is None or (isinstance(resp, str) and resp != "")

			# DMS attachment name
			att_name = claim["case_add"]["attachment_name"]
			assert isinstance(att_name, str) and att_name != ""

		if "case_update" in claim:

			# DMS Status AC
			stat_ac = claim["case_update"].get("status_ac")
			assert stat_ac is None or (isinstance(stat_ac, str))

			# DMS Status Sales
			stat_sales = claim["case_update"].get("status_sales")
			assert stat_sales is None or (isinstance(stat_sales, str) and stat_sales != "")
			assert isinstance(claim["case_update"]["attachment_name"], str) and stat_sales != ""

			# DMS Processor
			proc = claim["case_update"].get("processor")
			assert proc is None or (isinstance(proc, str) and proc != "")

			# DMS coordinator
			coord = claim["case_update"].get("coordinator")
			assert coord is None or (isinstance(coord, str) and coord != "")

			# DMS person responsible
			resp = claim["case_update"].get("responsible")
			assert resp is None or (isinstance(resp, str) and resp != "")

			# DMS Customer-disputed amount
			cust_disputed = claim["case_update"].get("cust_disputed")
			assert cust_disputed is None or (isinstance(cust_disputed, float) and cust_disputed > 0)

		g_log.info("Claim context data successfully compiled.")

		self._header.update(claim["header"])
		self._case.update({"search": claim["case_search"]})
		self._case.update({"update": claim.get("case_update")})
		self._notification.update({"extend": claim.get("case_add")})
		self._notification.update({"create": claim.get("claim_create")})

	@property
	def header(self) -> dict:
		"""Claim header parameters."""
		return self._header

	@property
	def transaction(self) -> str:
		"""Name of the processing transaction."""
		return self._header["transaction"]

	@property
	def company_code(self) -> str:
		"""Company code associated with the issuer."""
		return self._header["company_code"]

	@property
	def issuer(self) -> str:
		"""Customer that issued the document"""
		return self._header["issuer"]

	@property
	def category(self) -> str:
		"""Document category name."""
		return self._header["category"]

	@property
	def threshold(self) -> float:
		"""Processing threshold amount."""
		return self._header["threshold"]

	@property
	def kind(self) -> str:
		"Doument kind name."""
		return self._header["kind"]

	@property
	def template_id(self) -> str:
		"""ID of the data extraction template."""
		return self._header["template_id"]

	@property
	def tolerance(self) -> float:
		"""Amount tolerance used for searching in SAP."""
		return self._header["tolerance"]

	@property
	def notification(self) -> dict:
		"""Claim notification parameters."""
		return self._notification

	@property
	def case(self) -> dict:
		"""Claim case parameters."""
		return self._case
