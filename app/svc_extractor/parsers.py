# pylint: disable = C0301, C0302

"""Base module for data parsers."""

import math
import re
from abc import ABC, abstractmethod
from collections import OrderedDict
from datetime import date, datetime
from os.path import basename, splitext
from typing import Union
import yaml
from .... import logger

d_log = logger.get_logger("document")
g_log = logger.get_global_logger()

class PatternMatchError(Exception):
	"""Unmatched or mismatched regex pattern(s) for a mandatory field."""

class TemplateNotFoundError(Exception):
	"""Attempt to match data with any template fails."""

class CompositeParser(ABC):
	"""Parsing of composite data types."""

	def _fill_missing(self, item) -> list:
		"""Fills missing numerical values."""
		return [v.replace("", "0,00") if v == "" else v for v in item]

	@abstractmethod
	def parse_items(self, items: list, amount: float) -> Union[list,None]:
		"""
		Parses document items.

		Params:
		-------
		items: List of document items to parse.
		amount: Total document amount.

		Returns:
		--------
		List of parsed items.

		If parsing fails, then `None` is returned.

		Note:
		-----
		The total amount should always be checked against the sum of the partial
		amounts in the items listed on the document. So far, this is only done for
		OBI DE/AT, where the items are used in the process of automatically creating
		credit notes for the disputes. If the equality test is passed, the item is
		added to the database with the result. If not, the items are removed from
		the extraction result completely. However, if the items are missing, the
		'conventional penalty' automation will not be able to create a corresponding
		credit note if the CS decides to accept the customer's claim.
		"""

class PrimitiveParser(ABC):
	"""Parsing of primitive data types."""

	@abstractmethod
	def parse_number(
			self, val: str, coerce: str = None
		) -> Union[float,int]:
		"""Parses document items."""

	@abstractmethod
	def parse_date(
			self, val: str, fmt: str,
			dst_fmt: str = None,
			target_type: str = "datetime"
		) -> Union[date, datetime]:
		"""Parses a date string into a datetime object."""

class Parser(PrimitiveParser):
	"""Base class for document data parsers."""

	def parse_numbers(self, vals: Union[list,tuple], coerce: str = None) -> list:
		"""..."""

		result = []

		for val in vals:
			parsed = self.parse_number(val, coerce)
			result.append(parsed)

		return result

	def parse_number(
			self, val: str, coerce: str = None,
			errors: str = "raise") -> Union[float,int]:
		"""Converts a string amount into a float.

		Params:
		-------
		val:
			A string representing the amount value to convert. \n
			If the string contains any witespaces, these will be \n
			stripped before parsing.

		coerce:
			Indicates whether the pared number should be converted \n
			into a specific data type. Available values: \n			
				- None (default): data type of the resulting number will be inferred
				- 'int': resulting number will be converted to an integer
				- 'float': resulting number will be converted to a float

		errors:
			Action to take if an error is encountered: \n
			- 'raise': Exceptions will be raised.
			- 'ignore': The original input value will be returned.
			- 'devaluate': None will be returned instead.

		Returns:
		--------
		Parsed number.

		Examples:
		--------
		>>> parse_number('125,30-')
		>>> -125.3

		>>> parse_number('1.254.125,33-')
		>>> -1254125.33

		>>> parse_number('1.254.125.33-')
		>>> -1254125.33

		>>> parse_number('1,254,125,33-')
		>>> -1254125.33

		>>> parse_number('125.33')
		>>> 125.33

		>>> parse_number('125,5400')
		>>> 125.54

		>>> parse_number('1,000', coerce = 'int')
		>>> 1

		Raises:
		-------
		Values with type other than `str` raise a TypeError.
		Values with type `str` that don't represent a number raise a ValueError.
		"""

		if errors not in ["raise", "ignore", "devaluate"]:
			raise ValueError(f"Unrecognized value '{errors}' used!")

		if not isinstance(val, str):
			if errors == "raise":
				raise TypeError(
					"Could not parse the vlaue! Expected "
					f"value type was 'str', but got '{val}'.")
			if errors == "ignore":
				return val
			if errors == "devaluate":
				return None

		repl = val.replace(" ", "")
		repl = repl.strip("-")
		decimals = 0

		# some documents contain amouts rounded
		# to 4 decimal places instead of 2
		if re.search(r"\D", repl) is not None:
			decimals = len(re.split(r"\D", repl)[-1])

		# some documents contian amouts rounded
		# to 4 decimal places instead of 2
		repl = repl.replace(".", "")
		repl = repl.replace(",", "")

		if not repl.isnumeric():
			if errors == "raise":
				raise TypeError("Only numeric values are accepted!")
			if errors == "ignore":
				return val
			if errors == "devaluate":
				return None

		parsed = int(repl)

		if decimals != 0:
			parsed /= 10**decimals

		if "-" in val:
			parsed *= -1

		if coerce == "int":
			parsed = int(parsed)
		elif coerce == "float":
			parsed = float(parsed)

		return parsed

	def parse_date(
			self, val: str, fmt: str, dst_fmt: str = None,
			target_type: str = "datetime") -> Union[date, datetime]:
		"""Parses date and returns date after parsing.

		Params:
		-------
		val:
			String date to parse.

		fmt:
			String that defines the format of the input date.

		dst_fmt:
			String that controls the resulting date format. \n
			If `None` is used (default), then no final formatting \n
			will be applied and the result defined by 'target_type' \n
			parameter will be returned.

		target_type:
			Resulting data type.
			If invalid value is passed, then 'datetime' will be used.

		Returns:
		--------
		Parsed date as a datetime object.
		"""

		if not isinstance(val, str):
			raise TypeError(
				"Could not parse the vlaue! Expected "
				f"value type was 'str', but got '{val}'.")

		parsed = datetime.strptime(val, fmt)

		if target_type == "date":
			res = parsed.date()
		elif target_type == "datetime":
			res = parsed
		else: # if unsupported value is passed
			res = parsed

		if dst_fmt is not None:
			res = parsed.strftime(dst_fmt)

		return res

class MarkantParser(Parser, CompositeParser):
	"""Parser for Obi documents."""

	def __init__(self, template_id: str) -> None:
		"""Constructor for class: `ObiParser`."""

		self._dispatcher = {
			"141001DE002": self._parse_bgl_debit,
			"141001DE003": self._parse_dp_debit,
			"141001DE011": self._parse_debit,
		}

		if template_id not in self._dispatcher:
			raise NotImplementedError(
				"No composite data parsing method implemented "
				f"for template with ID: '{template_id}'!"
			)

		self._template_id = template_id

	def parse_items(self, items: list, amount: float) -> list:
		"""Parses document items."""
		return self._dispatcher[self._template_id](items, amount)

	def _parse_bgl_debit(self, items: list, amount: float) -> list:
		"""Parses penalty type items."""

		doc_items_amount = 0
		calc_items_amount = 0
		result = []

		for item in items:

			item = list(item)

			if item[1] == "":
				item[1] = "0,000"

			if item[2] == "":
				item[2] = "0,000"

			if item[3] == "":
				item[3] = "0,0000"

			if item[4] == "":
				item[4] = "0,0000"

			doc_diff = self.parse_number(item[0], coerce = "float")
			pcs_ordered = self.parse_number(item[1], coerce = "int")
			pcs_delivered = self.parse_number(item[2], coerce = "int")
			price_ordered = self.parse_number(item[3], coerce = "float")
			price_delivered = self.parse_number(item[4], coerce = "float")

			result.append([doc_diff, pcs_ordered, pcs_delivered, price_ordered, price_delivered])

			if pcs_ordered == 0 and pcs_delivered == 0 and price_delivered == 0 and price_ordered == 0:
				calc_diff = doc_diff
			elif pcs_ordered == 0 and pcs_delivered == 0:
				calc_diff = price_delivered - price_ordered
			elif price_delivered == 0 and price_ordered == 0:
				calc_diff = doc_diff
			elif pcs_ordered == pcs_delivered:
				calc_diff = (price_delivered - price_ordered) * pcs_ordered
			elif price_delivered == price_ordered:
				calc_diff = (pcs_ordered - pcs_delivered) * price_ordered
			else:
				calc_diff = (pcs_ordered - pcs_delivered) * (price_delivered - price_ordered)

			calc_diff = abs(round(calc_diff, 2))

			calc_items_amount += calc_diff
			doc_items_amount += doc_diff

		doc_items_amount = round(doc_items_amount, 2)
		calc_items_amount = round(calc_items_amount, 2)

		if doc_items_amount + calc_items_amount != amount * 2:
			g_log.error("Sum of item amounts not equal to the document total amount!")
			d_log.error("Sum of item amounts not equal to the document total amount!")
			g_log.warning("Field 'items' will be removed from extracted data.")
			return None

		return result

	def _parse_dp_debit(self, items: list, amount: float) -> list:
		"""Parses penalty type items."""

		doc_items_amount = 0
		calc_items_amount = 0
		result = []

		for item in items:

			item = list(item)

			if item[1] == "":
				item[1] = "0,000"

			if item[2] == "":
				item[2] = "0,000"

			if item[3] == "":
				item[3] = "0,0000"

			if item[4] == "":
				item[4] = "0,0000"

			doc_diff = self.parse_number(item[0], coerce = "float")
			pcs_ordered = self.parse_number(item[1], coerce = "int")
			pcs_delivered = self.parse_number(item[2], coerce = "int")
			price_ordered = self.parse_number(item[3], coerce = "float")
			price_delivered = self.parse_number(item[4], coerce = "float")

			result.append([doc_diff, pcs_ordered, pcs_delivered, price_ordered, price_delivered])

			if pcs_ordered == 0 and pcs_delivered == 0 and price_delivered == 0 and price_ordered == 0:
				calc_diff = doc_diff
			elif pcs_ordered == 0 and pcs_delivered == 0:
				calc_diff = price_delivered - price_ordered
			elif price_delivered == 0 and price_ordered == 0:
				calc_diff = doc_diff
			elif pcs_ordered == pcs_delivered:
				calc_diff = (price_delivered - price_ordered) * pcs_ordered
			elif price_delivered == price_ordered:
				calc_diff = (pcs_ordered - pcs_delivered) * price_ordered
			else:
				calc_diff = (pcs_ordered - pcs_delivered) * (price_delivered - price_ordered)

			calc_diff = abs(round(calc_diff, 2))

			calc_items_amount += calc_diff
			doc_items_amount += doc_diff

		doc_items_amount = round(doc_items_amount, 2)
		calc_items_amount = round(calc_items_amount, 2)

		if doc_items_amount + calc_items_amount != amount * 2:
			g_log.error("Sum of item amounts not equal to the document total amount!")
			d_log.error("Sum of item amounts not equal to the document total amount!")
			g_log.warning("Field 'items' will be removed from extracted data.")
			return None

		return result

	def _parse_debit(self, items: list, amount: float) -> list:
		"""Parses penalty type items."""

		doc_items_amount = 0
		calc_items_amount = 0
		result = []

		for item in items:

			item = list(item)

			if item[1] == "":
				item[1] = "0,000"

			if item[2] == "":
				item[2] = "0,000"

			if item[3] == "":
				item[3] = "0,0000"

			if item[4] == "":
				item[4] = "0,0000"

			doc_diff = self.parse_number(item[0], coerce = "float")
			pcs_ordered = self.parse_number(item[1], coerce = "int")
			pcs_delivered = self.parse_number(item[2], coerce = "int")
			price_ordered = self.parse_number(item[3], coerce = "float")
			price_delivered = self.parse_number(item[4], coerce = "float")

			result.append([doc_diff, pcs_ordered, pcs_delivered, price_ordered, price_delivered])

			if pcs_ordered == 0 and pcs_delivered == 0 and price_delivered == 0 and price_ordered == 0:
				calc_diff = doc_diff
			elif pcs_ordered == 0 and pcs_delivered == 0:
				calc_diff = price_delivered - price_ordered
			elif price_delivered == 0 and price_ordered == 0:
				calc_diff = doc_diff
			elif pcs_ordered == pcs_delivered:
				calc_diff = (price_delivered - price_ordered) * pcs_ordered
			elif price_delivered == price_ordered:
				calc_diff = (pcs_ordered - pcs_delivered) * price_ordered
			else:
				calc_diff = (pcs_ordered - pcs_delivered) * (price_delivered - price_ordered)

			calc_diff = abs(round(calc_diff, 2))

			calc_items_amount += calc_diff
			doc_items_amount += doc_diff

		doc_items_amount = round(doc_items_amount, 2)
		calc_items_amount = round(calc_items_amount, 2)

		if doc_items_amount + calc_items_amount != amount * 2:
			g_log.error("Sum of item amounts not equal to the document total amount!")
			d_log.error("Sum of item amounts not equal to the document total amount!")
			g_log.warning("Field 'items' will be removed from extracted data.")
			return None

		return result

class ObiParser(Parser, CompositeParser):
	"""Parser for Obi documents."""

	def __init__(self, template_id: str) -> None:
		"""Constructor for class: `ObiParser`."""

		self._dispatcher = {
			"161001DE005": self._parse_delivery,
			"161001DE001": self._parse_penalty,
			"161072AT005": self._parse_penalty,
			"161001DE007": self._parse_return,
		}

		if template_id not in self._dispatcher:
			raise NotImplementedError(
				"No composite data parsing method implemented "
				f"for template with ID: '{template_id}'!"
			)

		self._template_id = template_id

	def parse_items(self, items: list, amount: float) -> list:
		"""Parses document items."""
		return self._dispatcher[self._template_id](items, amount)

	def _parse_delivery(self, items: list, amount: float) -> list:
		"""Parses delivery type items."""

		result = []
		items_amount = 0

		for item in items:

			parsed_item = []

			for val in item:

				if re.fullmatch(r"\d+,\d{3}", val):
					parsed_val = self.parse_number(val, coerce = "int")
				elif re.match(r"\d+,\d{4}", val):
					parsed_val = self.parse_number(val, coerce = "float")
				elif re.match(r"\d+,\d{2}", val):
					parsed_val = self.parse_number(val, coerce = "float")
				else:
					parsed_val = val

				parsed_item.append(parsed_val)

			result.append(parsed_item)
			diff = parsed_item[5] - parsed_item[2]
			items_amount += diff

		# validate parsed data
		if round(items_amount, 2) != amount:
			g_log.error("Sum of item amounts not equal to the document total amount!")
			d_log.error("Sum of item amounts not equal to the document total amount!")
			g_log.warning("Field 'items' will be removed from extracted data.")
			return None

		return result

	def _parse_return(self, items: list, amount: float) -> list:
		"""Parses delivery type items."""

		result = []
		items_amount = 0

		for item in items:

			parsed_item = []

			for val in item:

				if val == "":  # Rabatt
					parsed_val = 0.0
				elif val.isnumeric(): # LAR
					parsed_val = self.parse_number(val, coerce = "int")
				elif re.fullmatch(r"\d+,\d{3}", val): # Menge
					parsed_val = self.parse_number(val, coerce = "int")
				elif re.match(r"\d+,\d{4}", val): # EK-Preis
					parsed_val = self.parse_number(val, coerce = "float")
				elif re.match(r"\d+,\d{2}", val): # PosWert
					parsed_val = self.parse_number(val, coerce = "float")
				else:
					parsed_val = val

				parsed_item.append(parsed_val)

			result.append(parsed_item)
			items_amount += parsed_item[-1]

		# validate parsed data
		if round(items_amount, 2) != amount:
			g_log.error("Sum of item amounts not equal to the document total amount!")
			d_log.error("Sum of item amounts not equal to the document total amount!")
			g_log.warning("Field 'items' will be removed from extracted data.")
			return None

		return result

	def _parse_penalty(self, items: list, amount: float) -> list:
		"""Parses penalty type items."""

		items_amount = 0
		err_tax_rate =  False
		result = []

		for item in items:

			partial_penalty = self.parse_number(item[0])
			po_number = self.parse_number(item[1], coerce = "int")
			item_amount = self.parse_number(item[2])
			parsed = [partial_penalty, po_number, item_amount]
			result.append(parsed)

			calc_rate = int(partial_penalty / item_amount * 100)

			if calc_rate in (2, 25):
				items_amount += partial_penalty
				continue

			# possible reason: incorrect data extraction or mistake made by the customer
			d_log.error("Invalid tax rate %.2f %% in document items!", calc_rate)
			g_log.error("Invalid tax rate %.2f %% in document items!", calc_rate)
			g_log.warning("Field 'items' will be removed from extracted data.")
			err_tax_rate = True
			break

		if err_tax_rate:
			return None

		if round(items_amount, 2) != amount:
			g_log.error("Sum of item amounts not equal to the document total amount!")
			d_log.error("Sum of item amounts not equal to the document total amount!")
			g_log.warning("Field 'items' will be removed from extracted data.")
			return None

		return result

class RollerParser(Parser, CompositeParser):
	"""Parser for Roller documents."""

	def __init__(self, template_id: str) -> None:
		"""Constructor for class: `RollerParser`."""

		self._dispatcher = {
			"171001DE001": self._parse_return,
		}

		if template_id not in self._dispatcher:
			raise NotImplementedError(
				"No composite data parsing method implemented "
				f"for template with ID: '{template_id}'!"
			)

		self._template_id = template_id

	def parse_items(self, items: list, amount: float) -> list:
		"""Parses document items."""
		return self._dispatcher[self._template_id](items, amount)

	def _parse_return(self, items: list, amount: float) -> list:
		"""Parses deli  very type items."""

		result = []
		items_amount = 0

		for item in items:

			n_pieces = self.parse_number(item[0], coerce = "int")
			amount_net = self.parse_number(item[1], coerce = "float")
			tax_rate = self.parse_number(item[2], coerce = "float")
			amount_tax = self.parse_number(item[3], coerce = "float")
			amount_gross = self.parse_number(item[4], coerce = "float")

			if n_pieces <= 0:
				raise ValueError("Number of pieces must be a positive integer!")

			if tax_rate not in (19.0, 0.0):
				raise ValueError(f"Incorrect tax rate: {tax_rate}!")

			if amount_gross <= 0:
				raise ValueError("Item gross amount must be a positive float!")

			result.append([n_pieces, amount_net, tax_rate, amount_gross])

			items_amount = amount_net + amount_tax

		# validate parsed data
		if round(items_amount, 2) != amount:
			g_log.error("Sum of item amounts not equal to the document total amount!")
			d_log.error("Sum of item amounts not equal to the document total amount!")
			g_log.warning("Field 'items' will be removed from extracted data.")
			return None

		return result

class ToomParser(Parser, CompositeParser):
	"""Parser for Toom documents."""

	def __init__(self, template_id: str) -> None:
		"""Constructor for class: `RollerParser`."""

		self._dispatcher = {
			"181001DE001": self._parse_return,
		}

		if template_id not in self._dispatcher:
			raise NotImplementedError(
				"No composite data parsing method implemented "
				f"for template with ID: '{template_id}'!"
			)

		self._template_id = template_id

	def parse_items(self, items: list, amount: float) -> list:
		"""Parses document items."""

		return self._dispatcher[self._template_id](items, amount)

	def _parse_return(self, items: list, amount: float) -> list:
		"""Parses return type items."""

		result = []
		items_gross_amount = 0

		for item in items:
			tax_rate = self.parse_number(item[0], coerce = "float")
			n_pieces = self.parse_number(item[1], coerce = "int")
			amount_net = self.parse_number(item[2], coerce = "float")
			result.append([tax_rate, n_pieces, amount_net])
			items_gross_amount += amount_net * n_pieces * (1 + tax_rate / 100)

		# validate parsed data
		if not math.isclose(items_gross_amount, amount, rel_tol = 0.01):
			g_log.error("Sum of item amounts not equal to the document total amount!")
			d_log.error("Sum of item amounts not equal to the document total amount!")
			g_log.warning("Field 'items' will be removed from extracted data.")
			return None

		return result

class HornbachParser(Parser, CompositeParser):
	"""Parser for Toom documents."""

	def __init__(self, template_id: str) -> None:
		"""Constructor for class: `HornbachParser`."""

		self._dispatcher = {
			"211072AT001": self._parse_delivery_price,
			"211001DE001": self._parse_delivery_price,
		}

		if template_id not in self._dispatcher:
			raise NotImplementedError(
				"No composite data parsing method implemented "
				f"for template with ID: '{template_id}'!"
			)

		self._template_id = template_id

	def _parse_delivery_price(self, items: list, amount: float) -> list:
		"""Parses return type items."""

		result = []
		items_gross_amount = 0

		for item in items:
			article_num = self.parse_number(item[0], coerce = "int", errors = "devaluate")
			deliv_num = self.parse_number(item[1], coerce = "int")
			n_invoiced = self.parse_number(item[3], coerce = "int")
			n_delivered = self.parse_number(item[2], coerce = "int")
			amount_ordered = self.parse_number(item[4], coerce = "float")
			amount_invoiced = self.parse_number(item[5], coerce = "float")
			item_net_amount = self.parse_number(item[6], coerce = "float")
			tax_rate = self.parse_number(item[7], coerce = "float")
			result.append([article_num, deliv_num, n_delivered, n_invoiced, amount_ordered, amount_invoiced, item_net_amount, tax_rate])
			amount_invoiced = 0 if amount_invoiced == amount_ordered else amount_invoiced
			gross_amount = (n_invoiced - n_delivered) * (amount_invoiced + amount_ordered) * (1 + tax_rate / 100)
			items_gross_amount += gross_amount

		# validate parsed data
		if not math.isclose(items_gross_amount, amount, rel_tol = 0.01):
			g_log.error("Sum of item amounts not equal to the document total amount!")
			d_log.error("Sum of item amounts not equal to the document total amount!")
			g_log.warning("Field 'items' will be removed from extracted data.")
			return None

		return result

	def parse_items(self, items: list, amount: float) -> list:
		"""Parses document items."""

		return self._dispatcher[self._template_id](items, amount)

# data extraction class
class Template(OrderedDict):
	"""
	Represents a template that lives
	as a single .yml file on the disk.
	"""

	_unique_value_fields = [
		"amount",
		"document_number",
		"archive_number",
		"return_number",
		"agreement_number",
		"supplier",
		"subtotals",
		"identifier",
		"branch",
		"zip",
	]

	_categs = [
		"bonus",
		"delivery",
		"finance",
		"invoice",
		"penalty_general",
		"penalty_delay",
		"penalty_quote",
		"price",
		"promo",
		"quality",
		"rebuild",
		"return"
	]

	_parser = None

	def __init__(self, *args, **kwargs):
		"""
		Constructor of class: `Template`.

		See docuemntation for OrderedDict for a detailed
		description of `args` and `kwargs` arguments.
		"""

		super(Template, self).__init__(*args, **kwargs)

		# set default options
		self._options = {
			"remove_whitespace": False,
			"lowercase": False,
			"replace": [],
			"date_formats": []
		}

		# Merge template-specific options with defaults
		self._options.update(self.get("options", {}))

		# check the integrity of header fields
		for fld in ["issuer", "kind", "name", "template_id"]:
			if fld not in self.keys() or self[fld] is None:
				raise KeyError(
					f"Could not load template '{self['name']}'! "
					f"Field '{fld}' missing from the template header."
				)

		# NOTE: Categorization is valid only for debits and makes no sense
		# for credit notes the current clam handling process.

		# Ensure, that field 'category' has correct data type and format
		# For credit notes, set the 'category' field to `None` value.
		if self["kind"] == "credit":
			self["category"] = None
		elif self["kind"] == "debit":
			if "category" not in self.keys():
				raise KeyError(
					f"Could not load the template '{self['name']}'! "
					"Field 'category' missing from the template header."
				)

			if isinstance(self["category"], str):
				used_categs = [self["category"]]
			elif isinstance(self["category"], list):
				used_categs = self["category"]
			else:
				raise TypeError(
					"Expected was 'category' value with type 'str' "
					f"or 'list[str]', but got '{type(used_categs)}'!"
				)

			unrecognized_categs = set(used_categs).difference(self._categs)

			if len(unrecognized_categs) != 0:
				raise ValueError(
					f"Could not load the template '{self['name']}'! "
					f"Unrecognized 'category' value(s): {unrecognized_categs}."
				)

		if self["category"] is not None:
			if isinstance(self["category"], list):
				self["category"] = [categ.lower() for categ  in self["category"]]
			elif isinstance(self["category"], str):
				self["category"] = self["category"].lower()
			else:
				raise TypeError(f"Unsupported data type for 'category' field: {type(self['category'])}!")

		# ensure proper casing of header field values
		self["issuer"] = self["issuer"].upper()
		self["kind"] = self["kind"].lower()
		self["template_id"] = self["template_id"].upper()

		if self["kind"] == "debit":
			if isinstance(self["category"], str):
				self["category"] = self["category"].lower()
			elif isinstance(self["category"], list):
				self["category"] = [val.lower() for val in self["category"]]
			else:
				raise TypeError(f"Unsupported type: '{type(self['category'])}' for 'category' field!")

	def _validate_numbering(self, val: Union[str,list], field: str = None) -> None:
		"""Validates the correctness of delivery note number(s)."""

		if isinstance(val, list):
			nums = val
		elif isinstance(val, str):
			nums = [val]
		else:
			raise TypeError(f"Value with type 'str' or 'list' expected, but got '{type(val)}'!")

		for num in nums:
			if field is None:
				if not num.isnumeric():
					raise ValueError(f"Invalid number: {num}!")
			elif field == "delivery_number":
				if not num.startswith("31") or len(num) != 9:
					raise ValueError(f"Invalid delivery note number: {num}!")
			elif field == "invoice_number":
				if not num.isnumeric() or num.startswith("0") or len(num) != 9:
					raise ValueError(f"Invalid invoice number: {num}!")
			elif field == "purchase_order_number":
				if not num.isnumeric() or num.startswith("0") or not 5 <= len(num) <= 7:
					raise ValueError(f"Invalid purchase order number: {num}!")
			elif field == "return_number":
				if not (num.isnumeric() and  6 <= len(num) <= 7):
					raise ValueError(f"Invalid return number: {num}!")
			elif field == "agreement_number":
				if not (num.isnumeric() or len(num) == 10):
					raise ValueError(f"Invalid agreement number: {num}!")
			else:
				raise ValueError(f"Unrecognized numbering type: '{field}'!")

	def _match_patterns(
			self, text: str, regex: Union[str,list],
			duplicates: bool = False) -> list:
		"""Performs matching of multiple regex patters on a text."""

		# ensure patts are placed in a list container
		rx_patts = regex if isinstance(regex, list) else [regex]
		res_find = []

		for patt in rx_patts:

			matches = re.findall(patt, text)

			if len(matches) == 0:
				continue

			res_find.extend(matches)

			break

		if not duplicates:
			res_find = list(set(res_find))

		return res_find

	def prepare_input(self, raw_str: str) -> str:
		"""
		Transform raw string using settings
		from 'options' section of the template file.

		Params:
		-------
		raw_str: String to transform.

		Returns:
		--------
		Transformed string.
		"""

		# Remove excessive withspace
		if self._options["remove_whitespace"]:
			optimized_str = re.sub(r"\s{2,}", "", raw_str)
		else:
			optimized_str = raw_str

		# convert to lower case
		if self._options["lowercase"]:
			optimized_str = optimized_str.lower()

		# specific replace
		for repl in self._options["replace"]:
			if len(repl) != 2:
				raise ValueError("A replace should be a list of 2 items!")
			optimized_str = re.sub(repl[0], repl[1], optimized_str)

		return optimized_str

	def matches_keywords(self, text: str) -> bool:
		"""
		Check if document text matches all
		keywords stated in the template file.
		"""

		inclusive = [bool(re.findall(kwd, text)) for kwd in self["inclusive_keywords"]]

		# these types ow keywords are optional when excluding certain
		# substrings is needed to filter on document types
		if "exclusive_keywords" in self:
			exclusive = [bool(re.findall(kwd, text)) for kwd in self["exclusive_keywords"]]
		else:
			exclusive = []

		if all(inclusive) and not any(exclusive):
			d_log.info("Matched template: '%s'", self["name"])
			return True

		return False

	def extract(self, text: str) -> dict:
		"""Given a template file and a string,
		extract matching data fields.
		"""

		d_log.info("Date parsing: date_formats = %s", self._options["date_formats"])
		d_log.info("Inclusive keywords = %s", self["inclusive_keywords"])
		d_log.info("Exclusive keywords = %s", self.get("exclusive_keywords", []))
		d_log.info("Options = %s", self._options)

		output = OrderedDict()
		output["issuer"] = self["issuer"]
		output["name"] = self["name"]
		output["kind"] = self["kind"]
		output["template_id"] = self["template_id"]
		output["category"] = self["category"]

		optional_fields = self.get("optional_fields", [])

		# Try to find data for each field.
		for fld, regex in self["fields"].items():

			allow_duplicates = fld == "items"
			result = self._match_patterns(text, regex, allow_duplicates)

			if len(result) == 0:
				# do not raise exception even if no value was found,
				# but keep matching to get as much data as possible
				if fld in optional_fields:
					d_log.warning(f"regexp '{regex}' for optional field '{fld}' didn't match!")
				else:
					d_log.error(f"regexp '{regex}' for field '{fld}' didn't match!")
			elif len(result) > 1 and fld in self._unique_value_fields:
				d_log.error(
					f"Field '{fld}': regex pattern '{regex}' should "
					f"match a unique value, but found: {result}!")
				raise PatternMatchError(
					f"Field '{fld}': regex pattern '{regex}' matched "
					"multiple values while only one is expected!")
			elif fld == "amount":
				output[fld] = self.parser.parse_number(result[0], coerce = "float")
				if output[fld] <= 0.0:
					raise ValueError("Extracted document amount must be a non-zero positive float!")
			elif fld in ("zip", "archive_number", "branch"):
				self._validate_numbering(result[0])
				output[fld] = self.parser.parse_number(result[0], coerce = "int")
			elif fld in ("supplier", "document_number", "identifier", "backreference_number"):
				output[fld] = self.parser.parse_number(result[0], coerce = "int", errors = "ignore")
			elif fld == "tax":
				if len(result) == 1:
					output[fld] = self.parser.parse_number(result[0], coerce = "float")
				else:
					output[fld] = self.parser.parse_numbers(result, coerce = "float")
			elif fld == "subtotals":
				output[fld] = self.parser.parse_numbers(result[0], coerce = "float")
			elif fld in ("delivery_number", "invoice_number", "purchase_order_number", "return_number", "agreement_number"):
				self._validate_numbering(result, fld)
				if len(result) == 1:
					output[fld] = self.parser.parse_number(result[0], coerce = "int")
				else:
					output[fld] = self.parser.parse_numbers(result, coerce = "int")
			elif fld == "items":
				# NOTE: in yaml templates, items must always come after amount,
				# otherwise item parsing won't be possibe - consider refactoring
				if isinstance(self.parser, CompositeParser):
					output[fld] = self.parser.parse_items(result, output["amount"])
				else:
					output[fld] = result
			elif fld == "email":
				output[fld] = result[0].replace(" ", "")
			elif fld == "reason":
				if isinstance(result[0], (tuple, list)):
					output[fld] = [val.strip() for val in result[0]]
				elif isinstance(result[0], str):
					output[fld] = result[0].strip()
				else:
					raise TypeError("Unexpected type of the 'reason' field!")
			else:
				output[fld] = result[0]

			d_log.info(f"field: '{fld}' | result: {result} | regexp: '{regex}'")

		# If required fields were found, return output, else log error.
		templ_fields = set(self["fields"]) # list of all field names in a tempate
		req_fields = templ_fields.difference(optional_fields)
		req_unmatched = set(req_fields).difference(output.keys())
		req_unmatched = list(req_unmatched)

		if len(req_unmatched) != 0:
			d_log.error(f"Required fields unmatched: {req_unmatched}")
			raise PatternMatchError(f"Required fields unmatched: {req_unmatched}")

		# each data dict must contain at least
		# these filelds once parsing is done
		assert output["issuer"] is not None
		assert output["name"] is not None
		assert output["kind"] is not None
		assert output["document_number"] is not None
		assert output["amount"] is not None
		assert output["template_id"] is not None

		return dict(output)

	def accept_parser(self, psr: Parser) -> None:
		"""Sets data parser."""
		self._parser = psr

	@property
	def parser(self) -> Parser:
		"""data parser"""
		return self._parser

def create_template(tpl_path: str) -> Template:
	"""
	Creates document data parser.

	Params:
	-------
	tpl_path: Path to the yaml file with parsing rules.

	Returns:
	--------
	Document data parser.
	"""

	with open(tpl_path, encoding = "utf-8") as stream:
		tpl = yaml.safe_load(stream)

	tpl["name"] = splitext(basename(tpl_path))[0]
	template_id = tpl["template_id"]

	if "optional_fields" in tpl["fields"].keys():
		raise KeyError("Field 'optional_fields' misplaced!")

	# Test if all required fields are in the correct place template:
	if "inclusive_keywords" not in tpl.keys():
		raise KeyError(f"Field 'inclusive_keywords' missing from template '{tpl['name']}'!")

	# Keywords as list, if only one.
	if not isinstance(tpl["inclusive_keywords"], list):
		tpl["inclusive_keywords"] = [tpl["inclusive_keywords"]]

	issuer = tpl["issuer"]
	template_id = tpl["template_id"]

	try:
		if issuer in ("OBI_AT", "OBI_DE"):
			parser = ObiParser(template_id)
		elif issuer == "MARKANT_DE":
			parser = MarkantParser(template_id)
		elif issuer == "ROLLER_DE":
			parser = RollerParser(template_id)
		# elif issuer == "TOOM DE": # item parsing left out so far
		#     parser = ToomParser(template_id)
		elif issuer in ("HORNBACH_AT", "HORNBACH_DE"):
			parser = HornbachParser(template_id)
		else:
			parser = Parser()
	except NotImplementedError as exc:
		g_log.warning(f"{str(exc)} Only parsing of primitive document data is possible.")
		parser = Parser()

	template = Template(tpl)
	template.accept_parser(parser)

	return template
