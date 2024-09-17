# pylint: disable = W0718, W1203, C0302

"""
The module provides a high-level interface for data
extraction form documents using MS Forms Recognizer.
"""

import json
import logging
import math
import re
from copy import deepcopy
from datetime import date, datetime
from math import isclose
from os.path import basename, dirname, join, splitext
from typing import Union

import yaml
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from azure.storage.blob import ContainerClient

from ... import logger

VirtualPath = str
VirtualPaths = list
LocalPath = str
LocalPaths = list
Blobs = list

_log = logging.getLogger("global")

_lang_dict_path = join(dirname(__file__), "lang.yaml")
with open(_lang_dict_path, encoding = "utf-8") as fstream:
	_lang_dictionary = yaml.safe_load(fstream)

class LowConfidenceError(Exception):
	"""Raisesd when a value was extracted
	below an acceptable confidence level.
	"""

def _round_amount(val: Union[float, int]) -> float:
	"""Rounds amout to a 2-decimal float.

	Parameters:
	-----------
	val:
		Value to round.

		If a float is passed, then the value is rounded
		to two decimal places. If an int is passed, then
		no rounding is performed and the the value is
		only converted to a float with a zero after the
		decimal point.

	Returns:
	--------
	The rounded value.

	Example:
	--------
	>>> round_amount(12.5545)
	>>> 12.56

	>>> round_amount(12.25)
	>>> 12.25

	>>> round_amount(12.273)
	>>> 12.27

	>>> round_amount(12.277)
	>>> 12.28

	>>> round_amount(12.4357)
	>>> 12.44

	>>> round_amount(-112.4357)
	>>> -112.44

	>>> round_amount(5)
	>>> 5.0
	"""

	if not isinstance(val, (int, float)):
		raise TypeError(f"Expected value type was float, but got {type(val)}: {val}!")

	if isinstance(val, int):
		return float(val)

	decimals = str(val).split(".")[1]

	if len(decimals) in (1, 2):
		return val

	n_decimals = len(decimals) - 1
	mult = val * 10**n_decimals

	if int(str(val)[-1]) < 5:
		if val > 0:
			capped = math.floor(mult)
		else:
			capped = math.ceil(mult)
	else:
		if val > 0:
			capped = math.ceil(mult)
		else:
			capped = math.floor(mult)

	result = capped  / 10**n_decimals

	return _round_amount(result)

def _parse_obi_de_return(converted: dict, optional: list, verify_items: bool = True) -> dict:
	"""Validate items extractd from an Obi DE "Retoure" debit notes."""

	output = deepcopy(converted)

	# document number
	docnum = converted["document_number"]
	docnum = docnum.replace("RA", "").replace("RE", "")
	docnum = _parse_number(docnum, errors="ignore")
	output["document_number"] = docnum

	# document name
	docname = converted["document_name"]
	output["document_name"] = re.sub(r"\(\d\)", "", docname)

	# total document amount
	output["amount"] = _extract_amount(output["amount"])

	# supplier
	suppler_match = re.search(pattern = r"[1-9]\d{3}", string = converted["supplier"])
	assert suppler_match is not None, "Suppier not found!"
	supplier = suppler_match.group(0)
	output["supplier"] = _parse_number(supplier, coerce = "int")

	# branch
	output["branch"] = _parse_number(converted["branch"], coerce="int")

	# tax code (UID-NR)
	tax_code_match = re.search(pattern=r"DE\d+", string = converted["tax_code"])
	assert suppler_match is not None, "UID-NR tax code not found!"
	tax_code = tax_code_match.group(0)

	if len(tax_code) != 11:
		raise ValueError(f"Invalid tax code extacted: '{tax_code}'")

	output["tax_code"] = tax_code

	# invoice number
	if output.get("invoice_number") is not None:
		output["invoice_number"] = _parse_number(converted["invoice_number"])

	# delivery numberItem list is empty
	if output.get("delivery_number") is not None:
		output["delivery_number"] = _parse_number(converted["delivery_number"])

	# purchase order number
	if output.get("purchase_order_number") is not None:
		output["purchase_order_number"] = _parse_number(
			converted["purchase_order_number"])

	if output["kind"] == "debit":
		assert len(output["items"]) != 0, "Items not found!"

	total_items_amount = 0
	parsed_items = []

	for idx, item in enumerate(converted["items"]):

		item_code_cust = item.get("item_code_customer")
		item_code_led = item.get("item_code_ledvance")

		if "item_code" not in optional:

			assert item_code_cust is not None, (
				"Field 'item_code_customer': Value not found!")

			assert item_code_cust.isnumeric(), (
				f"Field 'item_code_customer': "
				f"Value '{item_code_cust}' not a number!"
			)

			assert item_code_led is not None, (
				"Field 'item_code_ledvance': Value not found!")

		item_name = item.get("item_name")

		if "item_name" not in optional:
			assert item_name is not None, (
				"Field 'item_name': Value not found!")
			assert item_name != "", (
				"Field 'item_name': Value cannot be an empty string!")

		item_discount = item.get("item_discount", "0")
		assert item_discount is not None, (
			"Field 'item_discount': Value not found!")

		item_discount = _parse_number(item_discount, coerce="float")

		pieces_count = item.get("pieces_count")
		assert pieces_count is not None, (
			"Field 'pieces_count': Value not found!")

		pieces_count = _parse_number(pieces_count, coerce="int")

		amount_per_piece = item.get("amount_per_piece")
		assert amount_per_piece is not None, (
			"Field 'amount_per_piece': Value not found!")

		amount_per_piece = _parse_number(amount_per_piece, coerce="float")

		item_amount = item.get("item_amount")
		assert item_amount is not None, (
			"Field 'item_amount': Value not found!")

		item_amount = _parse_number(item_amount, coerce="float", n_decimals=2)

		if verify_items:
			sign = "+"

			if item_discount >= 1:
				item_discount = -1 * item_discount
				sign = ""

			total_net_amount = _round_amount(amount_per_piece * pieces_count)
			total_gross_amount = total_net_amount * (1 + item_discount / 100)
			calc_item_amount = _round_amount(total_gross_amount)

			assert isclose(item_amount, calc_item_amount, rel_tol=0.01), (
				f"Item {idx}: {item_amount} != {calc_item_amount} "
				f"[ = {amount_per_piece} * {pieces_count} * (1 {sign} "
				f"{item_discount} / 100)]"
			)

			total_items_amount += total_gross_amount

		parsed_items.append({
			"item_code_customer": item_code_cust,
			"item_code_ledvance": item_code_led,
			"item_discount": item_discount,
			"item_name": item_name,
			"pieces_count": pieces_count,
			"amount_per_piece": amount_per_piece,
			"item_amount": item_amount
		})

	total_items_amount = _round_amount(total_items_amount)
	doc_amount = output["amount"]

	if output["kind"] == "debit" and verify_items:
		assert isclose(doc_amount, total_items_amount, rel_tol=0.01), (
			"Document total amount != calculated total amount "
			f"({doc_amount} != {total_items_amount})")

		output["items"] = parsed_items

	return output

def _parse_obi_de_delivery(converted: dict, optional: list, verify_items: bool = True) -> dict:
	"""Validate items extractd from an Obi DE "Mängelanzeige" debit notes."""

	output = deepcopy(converted)
	total_items_amount = 0

	# document number
	docnum = converted["document_number"]
	assert docnum is not None, "Field 'document_number': Value not found!"
	match = re.search(r"41\d{7}", docnum)
	assert match is not None, f"Field 'document_number': Value not found in text: '{docnum}'"
	output["document_number"] = match.group(0)

	# supplier
	supplier = re.search(pattern = r"[1-9]\d{3}", string = converted["supplier"])
	assert supplier is not None, "Field 'supplier': Value not found!"
	output["supplier"] = _parse_number(supplier.group(0), coerce="int")

	# branch
	assert output["branch"] is not None, "Field 'branch': Value not found!"
	output["branch"] = _parse_number(converted["branch"], coerce="int")

	# total document amount
	assert output["amount"] is not None, "Field 'amount': Value not found!"
	output["amount"] = _extract_amount(output["amount"])

	# items
	if output["kind"] == "debit":
		assert len(output["items"]) != 0, "Items not found!"

	parsed_items = []

	for idx, item in enumerate(output["items"]):

		# OBIAR
		item_code_customer = item.get("item_code_customer")
		item_code_ledvance = item.get("item_code_ledvance")

		if "item_code" not in optional:

			assert item_code_customer is not None, (
				"Field 'item_code_customer': Value not found!")
			assert item_code_customer.isnumeric(), (
				f"Item {idx}: Field 'item_code_customer': "
				f"Value '{item_code_customer}' not a number!"
			)

			assert item_code_ledvance is not None, (
				"Field 'item_code_ledvance': Value not found!")
			item_code_ledvance = item_code_ledvance.lstrip("AaCc")
			assert item_code_ledvance.isnumeric(), (
				f"Item {idx}: Field 'item_code_ledvance': "
				f"Value '{item_code_ledvance}' not a number!"
			)

		# RechMg
		n_pieces_cust = item.get("item_code_pieces_customer")
		n_pieces_led = item.get("item_code_pieces_ledvance")

		assert n_pieces_cust is not None, (
			f"Item {idx}: Field 'item_code_pieces_customer': Value not found!")
		n_pieces_cust = _parse_number(n_pieces_cust, coerce="int")

		assert n_pieces_led is not None, (
			f"Item {idx}: Field 'item_code_pieces_customer': Value not found!")
		n_pieces_led = _parse_number(n_pieces_led, coerce="int")

		# RechEK
		item_code_amount_cust = item.get("item_code_amount_customer")
		item_code_amount_led = item.get("item_code_amount_ledvance")

		assert item_code_amount_cust is not None, (
			f"Item {idx}: Field 'item_code_amount_customer': Value not found!")
		item_code_amount_cust = _parse_number(item_code_amount_cust, coerce="float", n_decimals=2)

		assert item_code_amount_led is not None, (
			f"Item {idx}: Field 'item_code_amount_ledvance': Value not found!")
		item_code_amount_led = _parse_number(item_code_amount_led, coerce="float", n_decimals=2)

		# PosRab
		item_disc_rate_cust = item.get("item_discount_rate_customer")
		item_disc_rate_led = item.get("item_discount_rate_ledvance")

		assert item_disc_rate_cust is not None, (
			f"Item {idx}: Field 'item_discount_rate_customer': Value not found!")
		item_disc_rate_cust = _parse_number(item_disc_rate_cust, coerce="float")

		assert item_disc_rate_led is not None, (
			f"Item {idx}: Field 'item_discount_rate_ledvance': Value not found!")
		item_disc_rate_led = _parse_number(item_disc_rate_led, coerce="float")

		# KopfRab
		item_header_disc_rate_cust = item.get("header_discount_rate_customer")
		item_header_disc_rate_led = item.get("header_discount_rate_ledvance")

		assert item_header_disc_rate_cust is not None, (
			f"Item {idx}: Field 'header_discount_rate_customer': Value not found!")
		item_header_disc_rate_cust = _parse_number(item_header_disc_rate_cust, coerce="float")

		assert item_header_disc_rate_led is not None, (
			f"Item {idx}: Field 'header_discount_rate_ledvance': Value not found!")
		item_header_disc_rate_led = _parse_number(item_header_disc_rate_led, coerce="float")

		# Wert
		item_amount_cust = item.get("item_amount_customer")
		item_amount_led = item.get("item_amount_ledvance")

		assert item_amount_cust is not None, (
			f"Item {idx}: Field 'item_amount_customer': Value not found!")
		item_amount_cust = _parse_number(item_amount_cust, coerce="float")

		assert item_amount_led is not None, (
			f"Item {idx}: Field 'item_amount_ledvance': Value not found!")
		item_amount_led = _parse_number(item_amount_led, coerce="float")

		# BA-Wert
		item_amount = item.get("item_amount")
		assert item_amount is not None, (
			f"Item {idx}: Field 'item_amount': Value not found!")
		item_amount = _parse_number(item_amount, coerce="float")

		# calcs
		if verify_items:
			total_net_amount_cust = _round_amount(n_pieces_cust * item_code_amount_cust)
			total_net_amount_led = _round_amount(n_pieces_led * item_code_amount_led)

			calc_item_amount = _round_amount(total_net_amount_led - total_net_amount_cust)
			assert isclose(item_amount, calc_item_amount, rel_tol=0.01), (
				f"Item {idx}: Document item amount != calculated item amount: "
				f"{item_amount} != {calc_item_amount}")
			total_items_amount += item_amount

		parsed_items.append({
			"item_code_customer": item_code_customer,
			"item_code_ledvance": item_code_ledvance,
			"item_code_pieces_customer": n_pieces_cust,
			"item_code_amount_customer": item_code_amount_cust,
			"item_code_amount_ledvance": item_code_amount_led,
			"item_discount_rate_customer": item_disc_rate_cust,
			"item_discount_rate_ledvance": item_disc_rate_led,
			"header_discount_rate_customer": item_header_disc_rate_cust,
			"header_discount_rate_ledvance": item_header_disc_rate_led,
			"item_amount_customer": item_amount_cust,
			"item_amount_ledvance": item_amount_led,
			"item_amount": item_amount
		})

	# final verificaion of the doc amount
	if output["kind"] == "debit" and verify_items:
		total_items_amount = _round_amount(total_items_amount)
		doc_amount = output["amount"]

		assert isclose(doc_amount, total_items_amount, rel_tol=0.01), (
			"Document total amount != calculated total amount "
			f"({doc_amount} != {total_items_amount})")

	output["items"] = parsed_items

	return output

def _parse_obi_de_invoice(converted: dict) -> dict:
	"""Validate items extractd from an Obi DE invoice."""

	output = deepcopy(converted)

	# invoice number
	invoice_number = converted["invoice_number"]
	assert re.match(r"41\d{7}", invoice_number) is not None, (
		f"Invaid invoice number: '{invoice_number}'")
	output["invoice_number"] = invoice_number

	# supplier
	supplier = re.search(pattern = r"[1-9]\d{3}", string = converted["supplier"])
	assert supplier is not None, "Field 'supplier' not found!"
	output["supplier"] = _parse_number(supplier.group(0), coerce="int")

	# branch
	output["branch"] = _parse_number(converted["branch"], coerce="int")

	# delivery note
	if output.get("delivery_number") is not None:
		output["delivery_number"] = _parse_number(converted["delivery_number"])

	# total document amount
	output["amount"] = _extract_amount(output["amount"])

	return output

def _parse_obi_de_credit(converted: dict) -> dict:
	"""Validate items extractd from an Obi DE Belegstorno."""

	output = deepcopy(converted)

	# invoice number
	document_number = converted["document_number"]
	assert document_number is not None, "Field 'document_number': Value not found!"

	if re.match(r"41\d{7}", document_number) is None:
		assert re.match(r"PE\d{8}", document_number) is not None, (
			f"Invaid document number: '{document_number}'")

	output["document_number"] = document_number

	# supplier
	supplier = re.search(pattern = r"[1-9]\d{3}", string = converted["supplier"])
	assert supplier is not None, "Field 'supplier' not found!"
	output["supplier"] = _parse_number(supplier.group(0), coerce="int")

	# branch
	output["branch"] = _parse_number(converted["branch"], coerce="int")

	# total document amount
	assert output["amount"] is not None, "Field 'amount' not found!"
	output["amount"] = _extract_amount(output["amount"])

	return output

def _parse_obi_de_penalty(converted: dict, verify_items: bool = True) -> dict:
	"""Validate items extractd from an Obi DE "LQ-Vereinbarung" debit notes."""

	output = deepcopy(converted)

	# document number
	docnum = converted["document_number"]
	assert docnum is not None, "Field 'document_number': Value not found!"

	if re.match(r"PE\d{5,}", docnum) is None:
		assert re.match(r"DE\d{10}", docnum) is not None, (
			f"Invaid document number: '{docnum}'")
	output["document_number"] = docnum

	# supplier
	assert converted["supplier"] is not None, "Field 'supplier': Value not found!"
	supplier = re.search(pattern = r"[1-9]\d{3}", string = converted["supplier"])
	assert supplier is not None, (
		"Could not extract the supplier number form the "
		f"'supplier' field text: '{converted['supplier']}'")
	output["supplier"] = _parse_number(supplier.group(0), coerce="int")

	# branch
	output["branch"] = _parse_number(converted["branch"], coerce="int")

	# total document amount
	output["amount"] = _extract_amount(output["amount"])

	# tax code (UID-NR)
	tax_code = converted.get("tax_code")

	if tax_code is not None:
		match = re.search(pattern = r"DE\d+", string = converted["tax_code"])
		assert tax_code is not None, "Tax code not found!"
		tax_code = match.group(0)

		if len(tax_code) != 11:
			raise ValueError(f"Invalid tax code extacted: '{tax_code}'")

	output["tax_code"] = tax_code

	# delivery note
	if output.get("delivery_number") is not None:
		output["delivery_number"] = _parse_number(converted["delivery_number"])

	# purchase order number
	po_num = output.get("purchase_order_number")

	if po_num is not None:
		output["purchase_order_number"] = _parse_number(po_num)

	# items
	parsed_items = []
	total_items_amount = 0

	if output["document_number"].startswith("PE"):
		# item retrieval is valid for LQ-Vereinbarung documents only
		assert len(output["items"]) != 0, "Items not found!"

	for idx, item in enumerate(converted["items"]):

		po_num = item.get("purchase_order_number")
		assert po_num is not None, f"Item {idx}: Field 'purchase_order_number': Value not found!"
		assert po_num.isnumeric(), f"Item {idx}: Field 'purchase_order_number': Value not a number!"
		po_num = _parse_number(po_num)

		tax_rate = item.get("tax_rate")
		assert tax_rate is not None, (
			f"Item {idx}: Field 'tax_rate': Value not found!")
		tax_rate = _parse_number(tax_rate.rstrip("%"), coerce="float")

		item_amount = item.get("item_amount")
		assert item_amount is not None, (
			f"Item {idx}: Field 'item_amount': Value not found!")
		item_amount = _parse_number(item_amount, coerce="float")
		total_items_amount += item_amount

		parsed_items.append({
			"purchase_order_number": po_num,
			"tax_rate": tax_rate,
			"item_amount": item_amount,
		})

	# final verificaion of the doc amount
	total_items_amount = _round_amount(total_items_amount)
	doc_amount = output["amount"]

	if verify_items:
		assert isclose(doc_amount, total_items_amount, rel_tol = 0.01), (
			"Document total amount != calculated total amount "
			f"({doc_amount} != {total_items_amount})")

	output["items"] = parsed_items

	return output

def _parse_data(converted: dict, coerce_rates: str) -> dict:
	"""Parses OBI document data."""

	id_tokens = converted["model_id"].split("_")
	customer = f"{id_tokens[0].upper()}_{id_tokens[1].upper()}"
	result = None

	if customer == "OBI_DE":
		if "LQ" in converted["name"]:
			result = _parse_obi_de_penalty(
				converted, verify_items = False)
		elif "Retoure" in converted["name"]:
			result = _parse_obi_de_return(
				converted, optional = ["item_code", "item_name"], verify_items = False)
		elif "Mängelanzeige" in converted["name"]:
			result = _parse_obi_de_delivery(
				converted, optional = ["item_code"], verify_items = False)
		elif "Rechnung" in converted["name"]:
			result = _parse_obi_de_invoice(converted)
		elif "Belegstorno" in converted["name"]:
			result = _parse_obi_de_credit(converted)

	if result is None:
		raise NotImplementedError(f"No data parser exists for '{customer}'!")

	if coerce_rates is None:
		return result

	# coerce rate-like main fields
	for key, val in converted.items():

		if "_rate" not in key:
			continue

		if coerce_rates == "int" and not isinstance(val["value"], int):
			result.update({key: int(val["value"])})
		elif coerce_rates == "float" and not isinstance(val["value"], float):
			result.update({key: val["value"]})

	# coerce rate-like item fields
	for key, val in converted["items"].items():

		if "_rate" not in key:
			continue

		if coerce_rates == "int" and not isinstance(val["value"], int):
			result.update({key: int(val["value"])})
		elif coerce_rates == "float" and not isinstance(val["value"], float):
			result.update({key: val["value"]})

	return result

def _parse_number(
		val: str,
		coerce: str = None,
		strip_vals: list = None,
		errors: str = "raise",
		n_decimals: int = None
	) -> Union[float, int]:
	"""Converts a string amount into a float.

	Params:
	-------
	val:
		A string representing the amount value to convert. \n
		If the string contains any witespaces, these will be \n
		stripped before parsing.

	coerce:
		Indicates whether the pared number should be converted \n
		into a specific data type. Available values:
		- None (default): data type of the resulting number will be inferred
		- 'int': resulting number will be converted to an integer
		- 'float': resulting number will be converted to a float

	errors:
		Action to take if an error is encountered:
		- 'raise': An ValueError exception is raised (default).
		- 'ignore': The input value is returned.
		- 'nullify': The None value is returned.

	n_decimals:
		Number of decimals to round the parsed number.

		Rounding can be performed only of the resulting number is a float.
		By default, no rounding is performed. If a positive integer is used,
		then the resulting number is rounded to the specified decimal places.

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

	>>> parse_number('125,5487', n_decimals = 3)
	>>> 125.549

	>>> parse_number('1,000', coerce = 'int')
	>>> 1

	>>> parse_number('abc', errors = 'ignore')
	>>> 'abc'

	>>> parse_number('abc', errors = 'nullify')
	>>> None

	>>> parse_number('abc', errors = 'raise')
	>>> ValueError: 'Only numeric values are accepted!'

	Raises:
	-------
	Values with type other than `str` raise a TypeError.
	Values with type `str` that don't represent a number raise a ValueError.
	"""

	if errors not in ["raise", "ignore", "nullify"]:
		raise ValueError(f"Unrecognized value '{errors}' used!")

	if not isinstance(val, str):
		if errors == "raise":
			raise TypeError(f"Expected value type to parse was 'str', but got '{val}'!")
		if errors == "ignore":
			return val
		if errors == "nullify":
			return None

	for stripv in strip_vals or []:
		val = val.strip(stripv)

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
			raise ValueError(f"Expected a numeric string, but got '{val}'!")
		if errors == "ignore":
			return val
		if errors == "nullify":
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

	if n_decimals is not None and isinstance(parsed, float):
		n_decimals = max(n_decimals, 1)
		return round(parsed, n_decimals)

	return parsed

def _parse_date(
		val: str,
		fmt: str,
		dst_fmt: str = None,
		target_type: str = "datetime"
	) -> Union[date, datetime]:
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
			f"Expected value type was 'str', but got '{type(val)}': {val}!")

	parsed = datetime.strptime(val, fmt)

	if target_type == "date":
		res = parsed.date()
	elif target_type == "datetime":
		res = parsed
	else:
		raise ValueError(f"Invalid target type: '{target_type}'!")

	if dst_fmt is not None:
		res = parsed.strftime(dst_fmt)

	return res

def _format_bounding_region(bounding_regions) -> str:
	"""Formats bounding regions into a string representation."""

	if not bounding_regions:
		return "N/A"

	fmt = []

	for region in bounding_regions:
		fmt.append(f"Page #{region.page_number}: {region.polygon}")

	return ", ".join(fmt)

def _format_polygon(polygon) -> str:
	"""Formats polygon coordinates into a string representation."""

	if not polygon:
		return "N/A"

	coords = []

	for pol in polygon:
		coords.append(f"[{pol.x}, {pol.y}]")

	return ", ".join(coords)

def _convert_table(records: list) -> dict:
	"""Converts data extracted from a docuemnt table."""

	result = []

	for rec in records:

		record = {}

		for key, val in rec.value.items():
			record.update({key: val.value})

		result.append(record)

	return result

def _extract_amount(text: str) -> float:
	"""Exracts first amount-like substring from a text."""

	match = re.search(r"([\d.,-]+\d{2})", text)

	if match is None:
		raise ValueError(f"Could not find document amount in string: '{text}'")

	return _parse_number(match[0], coerce = "float")

def _convert(translated: dict) -> dict:
	"""Converts raw data to a more compact form,
	the structure of which is compatible with
	the extraction output of the regex engine.
	"""

	def get_branch_scanned(docnum: str) -> str:
		docnum = re.sub(r"\s+", "", docnum)
		match = re.search(r"DE(\d{3})", docnum)
		if match is None:
			raise ValueError(f"Branch number not found in string: '{docnum}'!")
		return match.group(1)

	result = {}

	# copy model id
	result["model_id"] = translated["model_id"]

	# issuer name is the name of the customer and
	# a 2-letter country code delimited by an underscore
	tokens = translated["model_id"].split("_")
	customer_name = "_".join([tokens[0], tokens[1]])
	result["issuer"] = customer_name

	# get document category
	# NOTE: Forms nerozlisuje Debit/credit pri sanovanych dokuentoch,
	# kedze Storno je sucastou nazvu dokumentu a nejde ho oddelit od
	# zvysku nazvu ako samostatne klucove slovo. Preto je potrebne
	# urcit programovo ci sa jedna o debit note alebo credit note
	fields = translated["documents"][0]["fields"]
	doc_name = fields["document_name"]["value"]
	doc_name = "" if doc_name is None else doc_name

	if "Retoure" in doc_name:
		if "Storno" in doc_name:
			result["name"] = "Storno-Retourenanzeige"
			result["category"] = None
			result["template_id"] = "161001DE008"
			result["kind"] = "credit"
		if "Gutschrift" in doc_name:
			result["name"] = "Gutschrift aus Retourenanzeige"
			result["category"] = None
			result["template_id"] = "161001DE003"
			result["kind"] = "credit"
		else:
			result["name"] = "Retourenanzeige"
			result["category"] = ["return", "quality", "delivery", "rebuild"]
			result["template_id"] = "161001DE007"
			result["kind"] = "debit"
	elif "Lieferverzug" in doc_name and "Unterlieferung" in doc_name:
		result["category"] = "penalty_general"
		result["name"] = "Beleg aus LQ-Vereinbarung"
		result["template_id"] = "161001DE011"
		result["kind"] = "debit"
	elif "Lieferverzug" in doc_name:
		result["name"] = "Beleg aus LQ-Vereinbarung"
		result["category"] = "penalty_delay"
		result["template_id"] = "161001DE010"
		result["kind"] = "debit"
	elif "Unterlieferung" in doc_name:
		result["name"] = "Beleg aus LQ-Vereinbarung"
		result["category"] = "penalty_quote"
		result["template_id"] = "161001DE009"
		result["kind"] = "debit"
	elif "LQ-Vereinbarung" in doc_name:
		result["name"] = "Beleg aus LQ-Vereinbarung"
		result["category"] = "penalty_general"
		result["template_id"] = "161001DE001"
		result["kind"] = "debit"
	elif "BELEGSTORNO" in doc_name:
		result["name"] = "Belegstorno"
		result["category"] = None
		result["template_id"] = "161001DE002"
		result["kind"] = "credit"
	elif "OBI Services" in doc_name:
		result["name"] = "Rechnung"
		result["template_id"] = "161001DE004"
		result["category"] = "invoice"
		result["kind"] = "credit"
	elif "Maengelanzeige" in doc_name:
		if "storno" in doc_name:
			result["name"] = "Mängelanzeigenstorno"
			result["template_id"] = "161001DE006"
			result["category"] = None
			result["kind"] = "credit"
		else:
			result["name"] = "Mängelanzeige"
			result["template_id"] = "161001DE005"
			result["category"] = ["delivery", "price"]
			result["kind"] = "debit"
	else:
		raise RuntimeError(f"Field 'document_name' has unexpected value: '{doc_name}'")

	# extract document fields and their values from raw data
	for key, val in translated["documents"][0]["fields"].items():
		result.update({key: val["value"]})

	if "Unterlieferung" in doc_name or "Lieferverzug" in doc_name:
		if fields["document_number"]["value"] is None:
			raise ValueError(
				"Could not extract branch number from the document number! "
				"The document number was not extracted from the document.")
		result["branch"] = get_branch_scanned(
			fields["document_number"]["value"])

	if result.get("items") is None:
		result["items"] = []

	return result

def _translate(extracted: dict) -> dict:
	"""Translates names of the extracted
	fields from a local language to English.
	"""

	# create a copy of the original data
	result = deepcopy(extracted)

	# detect language
	lang = result["model_id"].split("_")[1]

	# select the corrsponding dictionary
	# that contains Eeglish translations
	lang_dict = _lang_dictionary[lang]

	# get reference to the fields to translate
	fields = result["documents"][0]["fields"]

	# perform translation
	for local_name, val in fields.copy().items():

		if local_name not in lang_dict["fields"]:
			continue

		english_name = lang_dict["fields"][local_name]
		del fields[local_name]
		fields.update({english_name: val})

	# assert that all fields were translated
	missed = set(fields.keys()).difference(lang_dict["fields"].values())
	assert len(
		missed) == 0, f"The following fields weren't translated: {missed}"

	if "items" not in fields:
		fields.update({"items": {"value": []}})
	elif fields["items"]["value"] is None:
		fields["items"]["value"] = []

	translated_items = []

	for item in fields["items"]["value"]:

		translated_item = {}

		for local_name, val in item.items():
			if local_name not in lang_dict["items"]:
				raise ValueError(f"Unrecognized field name: '{local_name}'!")
			translated_item.update({lang_dict["items"][local_name]: val})

		translated_items.append(translated_item)

	fields["items"]["value"] = translated_items

	return result

def _verify_integrity(data: dict, tol: float, on_errors: str) -> None:
	"""Checks if all fields meet the expeced confidence threshold."""

	tol = 0.001 if tol <= 0 else tol
	tol = 1 if tol > 1 else tol

	fields = data["documents"][0]["fields"]

	if on_errors not in ("raise", "warn", "ingore"):
		raise ValueError(f"Unrecognized value: '{on_errors}'!")

	skipped_fields = ["Artikel"]

	for fld, params in fields.items():
		for key, val in params.items():
			val = 0 if val is None else val
			if fld not in skipped_fields and key == "confidence" and val < tol:
				msg = (
					f"The value '{params['value']}' for field '{fld}' was extracted with "
					f"confidence {val} that is below the acceptable confidence level {tol}!")
				if on_errors == "raise":
					logger.print_data(fields, desc="Fields:", top_brackets=False)
					raise LowConfidenceError(msg)
				if on_errors == "warn":
					_log.warning(msg)
				if on_errors == "ingore":
					pass
				logger.print_data(fields, desc="Fields:", top_brackets=False)


def _fetch_data(poller) -> dict:
	"""Fetches data form the extraction response."""

	result = poller.result()

	output = {
		"model_id": result.model_id,
		"documents": [],
		"pages": [],
		"tables": []
	}

	for document in result.documents:

		doc_output = {
			"doc_type": document.doc_type,
			"confidence": document.confidence,
			"fields": {}
		}

		for name, field in document.fields.items():

			field_value = field.value if field.value else field.content

			if isinstance(field_value, list):
				field_value = _convert_table(field_value)

			doc_output["fields"][name] = {
				"value_type": field.value_type,
				"value": field_value,
				"confidence": field.confidence
			}

		output["documents"].append(doc_output)

	for page in result.pages:

		page_output = {
			"page_number": page.page_number,
			"lines": [],
			"words": [],
			"selection_marks": []
		}

		for line in page.lines:
			page_output["lines"].append({
				"content": line.content,
				"bounding_box": _format_polygon(line.polygon)
			})

		for word in page.words:
			page_output["words"].append({
				"content": word.content,
				"confidence": word.confidence
			})

		for selection_mark in page.selection_marks:
			page_output["selection_marks"].append({
				"state": selection_mark.state,
				"confidence": selection_mark.confidence,
				"bounding_box": _format_polygon(selection_mark.polygon)
			})

		output["pages"].append(page_output)

	for table in result.tables:

		table_output = {
			"bounding_regions": [],
			"cells": []
		}

		for region in table.bounding_regions:
			table_output["bounding_regions"].append({
				"page_number": region.page_number,
				"bounding_box": _format_polygon(region.polygon)
			})

		for cell in table.cells:
			table_output["cells"].append({
				"row_index": cell.row_index,
				"column_index": cell.column_index,
				"content": cell.content
			})

		output["tables"].append(table_output)

	return output

def _remove_item_labels(parsed: dict) -> dict:
	"""Removes labels from items."""

	vals = []
	result = deepcopy(parsed)

	for item in parsed["items"]:
		vals.append(list(item.values()))

	result["items"] = vals

	return result

def _select_item_columns(parsed: dict, cols: list, missing: str) -> dict:
	"""Returns selected item columns in the data."""

	selected = []
	result = deepcopy(parsed)

	for item in parsed["items"]:
		vals = []
		for idx in cols or []:
			try:
				vals.append(item[idx])
			except IndexError:
				if missing == "coerce":
					return []
				if missing == "raise":
					raise
				if missing == "skip":
					continue
				if missing == "ignore":
					return parsed["items"]

		selected.append(vals)

	result["items"] = selected

	return result

def get_service_client(
		endpoint: str,
		key: str
	) -> DocumentAnalysisClient:
	"""Models data analysis client
	for the MS Forms Recognizer service.

	Params:
	-------
	endpoint:
		Endpoint ...

	key:
		Key ...

	Returns:
	--------
	The client service object.
	"""

	client = DocumentAnalysisClient(
		endpoint=endpoint,
		credential=AzureKeyCredential(key)
	)

	return client

def release_client(client: DocumentAnalysisClient) -> None:
	"""Closes the docuemnt analysis client.

	Parameters:
	-----------
	client: 
		The document analysis client.
	"""
	client.close()

def extract_file_data(
		client: DocumentAnalysisClient,
		file: LocalPath,
		model_id: str,
		convert: bool = False,
		confidence_tol: float = 1.0,
		integrity_error: str = "warn",
		parse: bool = False,
		item_labels: bool = True,
		item_cols: list = None,
		cols_missing: str = "raise",
		coerce_rates: str = None
	) -> dict:
	"""Extracts data from a local file.

	Parameters:
	-----------
	client:
		Client object that mediates the Azure document analysis service.

	file:
		Path to a local file from which to extract data. \n
		Supported file types are:
		- PDF
		- PNG
		- JPEG

	model_id:
		Name or ID of the AI model used to extract the data.

	convert:
		Whether to convert the extracted data
		to match the regex extractor's output format.

		During conversion, field names are translated
		from a local language to English.

	confidence_tol:
		Tolerance of the confidence value for a field.

		Valid range (lowest to highest confidence): 0.001 - 1.0. \n
		Values out of range are capped to the closest interval boundary. \n
		The parameter applies to all fields except for "items".

	integrity_error:
		Action to take if the integrity test fails: \n
			- "warn": A warning message is printed.
			- "raise" A LowConfidenceError exception is raised.
			- "ignore": No action is taken.

	parse:
		Whether to parse the converted data.

		By default, no parsing is perfomed. \n
		If `True`, then field values in the converted data are parsed. \n
		The parameter is ignored when convert = `False`.

	item_cols:
		Indexes or names of columns to include in the converted data.

		By default, all columns are included. If an empty list is passed, \n
		then no columns are included. If a list of indexes or column names \n
		is passed, then only those columns are included.

	item_labels:
		Whether to use labels for item columns in the converted data.

		If `True`, item labels are used (default behaviour). \n
		The parameter is ignored if the items are not found in the extracted data.

	cols_missing:
		Action to take when a column index or name
		is not found in the "items" field: \n
			- "ignore": All columns are included without filtering.
			- "raise": An IndexError exception is raised.
			- "coerce": An empty list of columns is returned.
			- "skip": The missing column is skipped.

	coerce_rates:
		Whether to coerce rate-like fields to a particular data type: \n
			- None: Parsed (default).
			- "int": Rates are converted to integers.
			- "float": Rates are converted to 2-decimal floats. Applicable only if parse = `True`.

	Returns:
	--------
	Extracted data stored as pairs of field names and their values.
	TODO: Details of returned params in the dict + types
	"""

	ext = splitext(basename(file))[1]

	if not ext.lower() in (".pdf", ".png", ".jpeg"):
		raise ValueError(f"Unsupported file type: '{ext}'!")

	if not coerce_rates in (None, "int", "float"):
		raise ValueError(f"Urecognzed 'convert_rates' value: {coerce_rates}")

	with open(file, "rb") as stream:
		poller = client.begin_analyze_document(
			model_id = model_id, document = stream)

	extracted = _fetch_data(poller)
	_verify_integrity(extracted, confidence_tol, integrity_error)

	if not convert:
		return extracted

	translated = _translate(extracted)
	converted = _convert(translated)

	if parse:
		parsed = _parse_data(converted, coerce_rates)

	if item_cols is None and item_labels:
		if parse:
			return parsed
		return converted

	if item_cols is not None:
		if parse:
			selected = _select_item_columns(
				parsed, item_cols, cols_missing)
		else:
			selected = _select_item_columns(
				converted, item_cols, cols_missing)

	if item_labels:
		return selected

	if item_cols is not None:
		unlabeled = _remove_item_labels(selected)
	elif parsed:
		unlabeled = _remove_item_labels(parsed)
	else:
		unlabeled = _remove_item_labels(converted)

	return unlabeled

def extract_blob_data(
		client: ContainerClient,
		blob_name: str,
		endpoint: str,
		key: str,
		input_container: str,
		output_container: str
	) -> None:
	"""Extracts data from a pdf file.

	Parameters:
	-----------
	client:
	blob_name:
	key:
	endpoint:
	input_container:
	output_container:
	"""

	document_analysis_client = DocumentAnalysisClient(
		endpoint = endpoint, credential = AzureKeyCredential(key)
	)

	input_container_client = client.get_container_client(input_container)
	output_container_client = client.get_container_client(output_container)
	blobs = input_container_client.find_blobs_by_tags(f"name='{blob_name}'")

	for blob in blobs:

		if blob.name != blob_name:
			continue

		if not blob.name.endswith(".pdf"):
			continue

		if not blob.name.startswith("claim_management/dev/documents/"):
			continue

		try:
			customer_name = dirname(blob.name).split('/')[-2]
			blob_client = client.get_blob_client(
				container = input_container, blob = blob.name
			)

			blob_data = blob_client.download_blob()
			poller = document_analysis_client.begin_analyze_document(
				model_id = customer_name, document = blob_data.readall()
			)

			result = poller.result()
			output_filename = splitext(basename(blob.name))[0] + ".json"
			output_dir = dirname(blob.name).replace("Input", "Upload")
			output_path = join(output_dir, output_filename)

			output = {
				"model_id": result.model_id,
				"documents": [],
				"pages": [],
				"tables": []
			}

			for document in result.documents:
				doc_output = {
					"doc_type": document.doc_type,
					"confidence": document.confidence,
					"fields": {}
				}
				for name, field in document.fields.items():
					field_value = field.value if field.value else field.content
					doc_output["fields"][name] = {
						"value_type": field.value_type,
						"value": str(field_value),
						"confidence": field.confidence
					}
				output["documents"].append(doc_output)

			output_container_client.upload_blob(
				name=output_path,
				data=json.dumps(output, indent=4)
			)

			_log.info(f"Successfully analyzed file: {blob.name}")

		except Exception as exc:
			_log.error(f"Error analyzing file {blob.name}: {str(exc)}")

	_log.info("All files analyzed successfully.")
