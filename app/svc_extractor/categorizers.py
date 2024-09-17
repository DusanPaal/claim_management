# pylint: disable = R0903

"""Document categorization."""

import re
from typing import Literal


class CategoryNotFoundError(Exception):
	"""
	Cannot identify document category.

	This happens when the reason text on
	the debit note doesn't match any of the
	known reasons listed in an internal
	category catalogue.
	"""

class Document:
	"""Abstracts a customer document."""

	_dispatcher = {}

	def __init__(self, data: dict) -> None:
		"""
		Creates a `Document` type object.

		Params:
		-------
		data: Data extracted from a document.
		"""

		self._data = data

	def categorize(self) -> str:
		"""Identifies category name of a document."""

		templ_id = self._data["template_id"]

		if templ_id not in self._dispatcher:
			raise NotImplementedError(
				"No categorization method exists for "
				f"template with ID: '{templ_id}'!"
			)

		return self._dispatcher[self._data["template_id"]]()


class BahagDocument(Document):
	"""
	Abstracts Bahag documents.

	Note:
	-----
	Keyword 'Sonstiges' may indicate a quality, as well as a return.
	The category can only be resolved at the CS department.
	"""

	_catalog = {

		"rebuild": [
			"altware",
			"umbau",
			"Aktualisierung",
			"Roll Out",
			"Sortimenswechsel"
		],

		"quality": [
			"reklama[tc]ion",
			"defekt",
			"leuchtet nicht",
			"funk[tc]ioniert",
			"blinkelt",
			"kaputt",
			"kein Funktion"
		],

		"return": [
			"Label",
			"ERP Altlabel",
			"Energielabel",
			"Anweisung SCD",
			"ERP Richtlinie",
			"Retoure zu Reparaturauftrag",
			"Keine Modulware",
			"Im Markt vernichtet",
			"falsche Aufmachung",
			"Made in Russia",
			"vor Ort vernichten",
			"Retoure",
			"Sortimentsbereinigung",
			"Falschbestellung",
			"Ware vernichtet",
			"zurück",
			"Falschlieferung"
		]

	}

	def __init__(self, data: dict) -> None:
		"""
		Creates a `BahagDocument` type object.

		Params:
		-------
		data: Data extracted from a document.
		"""

		Document.__init__(self, data)

		self._dispatcher = {
			"101072AT002": self._categorize_penalty,
			"101001CZ002": self._categorize_penalty,
			"101001DE011": self._categorize_penalty,
			"101001LU016": self._categorize_penalty,
			"101001DE015": self._categorize_return,
			"101072AT004": self._categorize_return,
		}

	def _categorize_penalty(self) -> str:
		"""Identifies category of penalties."""

		deliv_quote, deliv_delay = self._data["subtotals"]

		if deliv_quote == deliv_delay:
			categ = "penalty_general"
		elif deliv_quote > deliv_delay:
			categ = "penalty_quote"
		else:
			categ = "penalty_delay"

		return categ

	def _categorize_return(self) -> str:
		"""Identifies category of returns."""

		# optimization - concatenate reason texts into one
		# statement instead of looping through each of them
		reasons = "|".join(self._data["reason"])

		for categ, kwds in self._catalog.items():
			for kwd in kwds:
				if re.search(kwd, reasons, re.I):
					return categ

		raise CategoryNotFoundError(
			"Could not categorize the document! No identification keyword "
			f"from the categorization catalog matched the reason text '{reasons}'."
		)


class HagebauDocument(Document):
	"""
	Abstracts Hagebau documents.

	Note:
	-----
	The category of documents where only note
	"Sonstiges" exists must be resoved by the CS dept.

	The category of documents where note contians
	"Artikel beschädigt / im Markt vernichtet" could be
	"quality" or "return" and needs to be resolved by the CS
	"""

	_catalog = {

		"return": [
			"Preisreduzierung / Abverkaufshilfe",
			"Rückgabe wiederverkaufsfähiger Ware",
			"Sortimentsbereinigung",
			"falsch bestellte Ware",
			"nicht bestellte Ware"
		],

		"price": [
			"Preisabweichung"
		],

		"delivery": [
			"Lieferung unvollständig",
			"Verderb / Bruch bei Lieferung",
			"Annahme verweigert",
			"Paletten",
			"Fracht",
			"Verpackung"
		],

		"invoice": [
			"Doppelberechnung ohne Doppellieferung",
			"Komplettlieferung fehlt",
			"Rabattabweichung",
			"Aufwand"
		],

		"penalty_general": ["Konventionalstrafe"],
		"bonus": ["WKZ"]  # zaklada sa manualne

	}

	def __init__(self, data: dict) -> None:
		"""
		Creates a `HagebauDocument` type object.

		Params:
		-------
		data: Data extracted from a document.
		"""

		Document.__init__(self, data)

		self._dispatcher = {
			"121001DE001": self._categorize_debitnote,
			"121072AT001": self._categorize_debitnote,
			"120074CH001": self._categorize_debitnote,
		}

	def _categorize_debitnote(self) -> str:
		"""Identifies category of a debit note."""

		reason = self._data["reason"]

		for categ, kwds in self._catalog.items():
			for kwd in kwds:
				if re.search(kwd, reason, re.I):
					return categ

		raise CategoryNotFoundError(
			"Could not categorize the document! The reason "
			f"keyword '{reason}' not found in the catalog."
		)


class HitDocument(Document):
	"""Abstracts HIT documents."""

	_catalog = {

		"delivery": [
			"Mengendifferenz",
			"nicht.*?geliefert",
		],

		"price": ["Abweichung.*Preise"],
		"quality": ["Beschädigte Waren"],

	}

	def __init__(self, data: dict) -> None:
		"""
		Creates a `HitDocument` type object.

		Params:
		-------
		data: Data extracted from a document.
		"""

		Document.__init__(self, data)

		self._dispatcher = {
			"131001DE001": self._categorize_debitnote,
		}

	def _categorize_debitnote(self) -> str:
		"""Identifies category of a debit note."""

		reason = self._data["reason"]

		if isinstance(reason, list):
			raise ValueError(
				"Could not categorize the document! "
				f"Excepcted a single reson, but found {len(reason)}."
			)

		for categ, kwds in self._catalog.items():
			for kwd in kwds:
				if re.search(kwd, reason, re.I):
					return categ

		raise CategoryNotFoundError(
			"Could not categorize the document! The keyword "
			f"'{reason}' not found in the reason catalog."
		)


class HornbachDocument(Document):
	"""Abstracts Hornbach documents."""

	def __init__(self, data: dict) -> None:
		"""
		Creates a `HornbachDocument` type object.

		Params:
		-------
		data: Data extracted from a document.
		"""

		Document.__init__(self, data)

		self._dispatcher = {
			"211072AT001": self._categorize_rechnungskuerzung,
			"211001DE001": self._categorize_rechnungskuerzung,
		}

	def _categorize_rechnungskuerzung(self) -> str:
		"""Identifies category name of a quality."""

		# if all attempts to categorize the doc based on keywords
		# fail, try to get the category from the listed items
		if self._data.get("items") is None:
			raise KeyError("Items are required to categorize the document!")

		price_diff = 0
		pieces_diff = 0

		for item in self._data["items"]:

			cust_pcs = item[2]
			ledv_pcs = item[3]
			cust_price = item[4]
			ledv_price = item[5]

			if cust_pcs < ledv_pcs:
				# item is a delivery loss
				diff = (ledv_pcs - cust_pcs) * ledv_price
				pieces_diff += abs(round(diff, 2))
			elif cust_pcs == ledv_pcs:
				# item is a pricing mistake
				diff = (ledv_price - cust_price) * cust_pcs
				price_diff += abs(round(diff, 2))
			else:
				raise ValueError(
					"Item count received by the customer cannot "
					"exceed the number of expeded items by Ledvance "
					"in a delivery loss document!")

		categ = "price" if price_diff > pieces_diff else "delivery"

		return categ

class MarkantDocument(Document):
	"""Abstracts Markant documents."""

	_catalog = {

		"delivery": [
			"nicht geliefert",
			"kein Wareneingang",
			"Fehlmenge",
			"Mengenreklamation",
			"zu wenig geliefert"
		],

		"price": [
			"Betragsreklamation",
			"Abweichung Preise",
		],

		"invoice": [
			"falschberechnung",
			"bereits belastet/vergütet",
			"(doppelt|mit Rechnung).*?(verrechnet|berechnet|abgerechnet)",
			"Abliefernachweis nicht erhalten"
		],

		"finance": [
			"Verkaufsbelege"
		],

		"penalty_general": [
			r"OTIF-P\?nale"
		],

		"bonus": [
			"Verkaufsförderung"
		]

	}

	def __init__(self, data: dict) -> None:
		"""Creates a `MarkantDocument` type object.

		Params:
		-------
		data: Data extracted from a document.
		"""

		Document.__init__(self, data)

		self._dispatcher = {
			"141001DE011": self._categorize_debitnote,
			"141001DE014": self._categorize_return,
			"141001DE008": self._categorize_wr_return,
			"141072AT004": self._categorize_wr_return,
			"141001DE007": self._categorize_bwl_return,
			"141001DE002": self._categorize_bgl_dp_debitnote,
			"141001DE003": self._categorize_bgl_dp_debitnote,
			"141001DE004": self._categorize_rvg_debitnote,
			"141072AT008": self._categorize_debitnote,
			"141072AT007": self._categorize_rvg_debitnote
		}

	def _categorize_debitnote(self) -> str:
		"""Identifies category of penalties."""

		reason = self._data["reason"]

		for categ, kwds in self._catalog.items():
			for kwd in kwds:
				if re.search(kwd, reason, re.I):
					return categ

		# if all attempts to categorize the doc based on keywords
		# fail, try to get the category from the listed items
		if self._data.get("items") is None:
			raise KeyError("Items are required to categorize the document!")

		price_diff = 0
		pieces_diff = 0

		for item in self._data["items"]:

			cust_pcs = item[1]
			ledv_pcs = item[2]
			cust_price = item[3]
			ledv_price = item[4]

			if cust_pcs < ledv_pcs:
				# item is a delivery loss
				diff = (ledv_pcs - cust_pcs) * ledv_price
				pieces_diff += abs(round(diff, 2))
			elif cust_pcs == ledv_pcs:
				# item is a pricing mistake
				diff = ledv_price - cust_price
				price_diff += abs(round(diff, 2))
			else:
				raise ValueError(
					"Item count received by the customer cannot "
					"exceed the number of expeded items by Ledvance "
					"in a delivery loss document!"
				)

		categ = "price" if price_diff > pieces_diff else "delivery"

		return categ

	def _categorize_rvg_debitnote(self) -> str:
		"""Identifies category of RVG debit notes."""

		reason = self._data["reason"]

		for categ, kwds in self._catalog.items():
			for kwd in kwds:
				if re.search(kwd, reason, re.I):
					return categ

		raise CategoryNotFoundError(
			"Could not categorize the document! The keyword "
			f"'{reason}' not found in the reason catalog."
		)

	def _categorize_wr_return(self) -> str:
		"""Identifies category of WR returns."""

		kwds = ["funktion", "defekt"]

		for kwd in kwds:
			if kwd in self._data["reason"].lower():
				return "quality"

		return "return"

	def _categorize_bwl_return(self) -> Literal['rebuild', 'return']:
		"""Identifies category of BWL returns."""

		if "umbau" in self._data["reason"].lower():
			return "rebuild"

		return "return"

	def _categorize_return(self) -> Literal['return']:
		"""
		Identifies category of
		'Belastung aus Retouren' returns.

		Returns:
		-------
		A constant value "return" since all
		these types of docs are conidered
		returns if not flagged otherwise by users.
		"""

		return "return"

	def _categorize_bgl_dp_debitnote(self) -> Literal['price', 'delivery']:
		"""Identifies category of BGL debits."""

		if self._data.get("items") is None:
			raise KeyError("Items are required to categorize the document!")

		price_diff = 0
		pieces_diff = 0

		for item in self._data["items"]:

			cust_pcs = item[1]
			ledv_pcs = item[2]

			cust_price = item[3]
			ledv_price = item[4]

			if cust_pcs < ledv_pcs:
				# item is a delivery loss
				diff = ledv_price - cust_price
				pieces_diff += diff
			elif cust_pcs == ledv_pcs:
				# item is a pricing mistake
				diff = ledv_price - cust_price
				price_diff += diff
			else:
				raise ValueError(
					"Item count received by the customer cannot "
					"exceed the number of expeded items by Ledvance "
					"in a delivery loss document!"
				)

		categ = "price" if price_diff > pieces_diff else "delivery"

		return categ


class MetroDocument(Document):
	"""Abstracts Metro documents."""

	def __init__(self, data: dict) -> None:
		"""
		Creates a `MetroDocument` type object.

		Params:
		-------
		data: Data extracted from a document.
		"""

		Document.__init__(self, data)

	def _categorize_quality(self) -> str:
		"""Identifies category name of a quality."""

		# TODO: implementation here

		categ = ""

		return categ


class ObiDocument(Document):
	"""Abstracts Obi documents."""

	def __init__(self, data: dict) -> None:
		"""
		Creates a `ObiDocument` type object.

		Params:
		-------
		data: Data extracted from a document.
		"""

		Document.__init__(self, data)

		self._dispatcher = {
			"161001DE005": self._categorize_delivery,
			"161072AT005": self._categorize_penalty,
			"161001DE001": self._categorize_penalty,
			"161072SI003": self._categorize_penalty,

		}

	def _categorize_delivery(self) -> str:
		"""Identifies category if Mängelanzeige docs."""

		if "items" not in self._data:
			raise KeyError("Items are required to categorize the document!")

		price_diff = 0
		pieces_diff = 0

		for item in self._data["items"]:

			cust_pcs = item[0]
			ledv_pcs = item[3]

			if cust_pcs > ledv_pcs:
				raise ValueError(
					"Item count received by the customer cannot "
					"exceed the number of expeded items by Ledvance "
					"in a delivery loss document!"
				)

			if cust_pcs < ledv_pcs:
				# item is a delivery loss
				cust_price = item[2]
				ledv_price = item[5]
				diff = ledv_price - cust_price
				pieces_diff += diff
			elif cust_pcs == ledv_pcs:
				# item is a pricing mistake
				cust_price = item[2]
				ledv_price = item[5]
				diff = ledv_price - cust_price
				price_diff += diff

		categ = "price" if price_diff > pieces_diff else "delivery"

		return categ

	def _categorize_penalty(self) -> str:
		"""Identifies category name of a quality."""

		allowed_rates = (2.0, 25.0)

		if isinstance(self._data["tax"], list):
			tax_rates = self._data["tax"]
		elif isinstance(self._data["tax"], float):
			tax_rates = [self._data["tax"]]

		used_rates = set(tax_rates)
		invalid_rates = used_rates.difference(allowed_rates)

		if len(invalid_rates) != 0:
			raise ValueError(f"Unrecognized tax rates: {invalid_rates}!")

		used_rates = list(used_rates)
		tax = used_rates[0] if len(used_rates) == 1 else used_rates

		if tax == 2.0:
			categ = "penalty_delay"
		if tax == 25.0:
			categ = "penalty_quote"
		elif tax == [25.0, 2.0]:
			categ = "penalty_general"

		return categ


class RollerDocument(Document):
	"""Abstracts Roller documents."""

	_catalog = {

		"rebuild": [
			"umbau",
			"altware",
			"lt. zentrale",
			"laut zentrale"
		],

	}

	def __init__(self, data: dict) -> None:
		"""
		Creates a `RollerDocument` type object.

		Params:
		-------
		data: Data extracted from a document.
		"""

		Document.__init__(self, data)

		self._dispatcher = {
			"171001DE001": self._categorize_return,
		}

	def _categorize_return(self) -> str:
		"""Identifies the category of 'Retoure' documents."""

		reason = self._data["reason"]

		for categ, kwds in self._catalog.items():
			for kwd in kwds:
				if re.search(kwd, reason, re.I):
					return categ

		return "return"

class Categorizer:
	"""Categorizes documents."""

	_documents = {
		"BAHAG": BahagDocument,
		"HAGEBAU": HagebauDocument,
		"HIT": HitDocument,
		"MARKANT": MarkantDocument,
		"METRO": MetroDocument,
		"OBI": ObiDocument,
		"ROLLER": RollerDocument,
		"HORNBACH": HornbachDocument
	}

	def categorize(self, data: dict) -> str:
		"""
		Identifies the document category.

		Params:
		-------
		data: Data extracted from the document.

		Returns:
		--------
		Name of the document category.
		"""

		assert "category" in data, "Field 'category' is not contained in the data!"
		assert "issuer" in data, "Field 'issuer' is not contained in the data!"
		assert data["kind"] == "debit", "Docuemnt categorization applies only to debit notes!"

		cust = data["issuer"].split("_")[0]  # customer name
		cust = cust.upper()

		if cust not in self._documents:
			raise NotImplementedError(f"No categorizer exists for customer '{cust}'!")

		doc = self._documents[cust](data)
		categ = doc.categorize()

		if categ not in data["category"]:
			raise ValueError(
				f"The identified category '{categ}' doesn't match "
				f"any of the allowed categories: {data['category']}!"
			)

		return categ
