# pylint: disable = W1203

"""Accounting maps."""

from abc import abstractmethod
from os.path import join
from typing import Union
from ... import logger
from ...resources.files import APP_ROOT, DataFrame, DirPath, Reader

g_log = logger.get_global_logger()


class AccountMap:
	"""Represents an account map."""

	_cust_name = None
	_cntry_code = None
	_data = None

	_mandatory_cols = (
		"supplier",
		"business_unit",
		"account"
	)

	def __init__(self, map_dir: DirPath, cust: str) -> None:
		"""
		Create an account map.

		Params:
		-------
		file:
			Path to the file that contains
			the data used to create the map.

		cust:
			Customer form which the map will be created.

			The value consists of a customer name and
			a 2-character country code separated by an
			underscore (e.g. 'OBI_DE')
		"""

		map_path = join(map_dir, f"{cust}.xlsx")
		data: DataFrame = Reader(map_path).read()

		if not data["account"].str.isnumeric().all():
			raise ValueError(f"{cust}: Column 'account' contains non-numeric entries!")

		unknown_cols = set(data.columns).difference(self._mandatory_cols)

		if len(unknown_cols) != 0:
			raise ValueError(f"{cust}: Data contains unrecognized columns: {unknown_cols}!")

		if "account" not in data:
			raise ValueError(f"{cust}: Column 'account' misssing from the data!")

		# check if non-numeric vals used are recognized
		if "business_unit" in data:

			mask = data["business_unit"].str.isnumeric() & data["business_unit"].notna()
			vals = data.loc[~mask, "business_unit"]

			invalid_busin = set(vals).difference(["head_office"])

			if len(invalid_busin) != 0:
				raise ValueError(
					f"{cust}: Column 'business_unit' contains "
					f"non-numeric entries: {invalid_busin}"
				)

		self._data = data
		self.cust_name, self._cntry_code = cust.split("_")

	def _validate_input(self, kwargs: dict, *expected) -> None:
		"""Validate input for procedure: `get_account()`."""

		suppl = kwargs.get("supplier")
		busin_unit = kwargs.get("business_unit")

		if suppl is not None:
			if not isinstance(suppl, (int,str)):
				raise TypeError(f"Incorrect supplier type: '{type(suppl)}'!")
			if not str(suppl).isnumeric():
				raise ValueError(f"Incorrect supplier value: {suppl}!")

		if busin_unit is not None:
			if not isinstance(busin_unit, (int,str)):
				raise TypeError(f"Incorrect business unit type: '{type(busin_unit)}'!")
			if not (busin_unit == "head_office" or str(busin_unit).isnumeric()):
				raise ValueError(f"Incorrect business unit value: {busin_unit}!")

		invalid_params = set(kwargs.keys()).difference(expected)

		if len(invalid_params) != 0:
			raise KeyError(f"Invalid kwarg parameter(s): {invalid_params}!")

	def _print_query(self, qry: str) -> None:
		"""Print data query as debug message."""
		g_log.debug(f"Account map data query: \"{qry}\"")


	@property
	def country_code(self) -> str:
		"""Country code."""
		return self._cntry_code

	@property
	def customer(self) -> str:
		"""Customer name."""
		return self.cust_name

	@abstractmethod
	def get_account(self, **kwargs) -> Union[int, None]:
		"""
		Return a customer or a head office
		account number as recorded at Ledvace.

		kwargs:
		-------
		Field names and values that represent the search criteria.
		if a head office account is requested, then the 'head_office'
		value needs to be passed as 'business_unit' argument.

		Note:
		-----
		Unrecognized kwargs are ignored.

		Returns:
		--------
		An 'int' that represent the customer account.
		If no account is found using the specified criteria, return 'None'.
		"""


class ObiAccountMap(AccountMap):
	"""Represents an 'OBI' account map."""

	def get_account(self, **kwargs) -> Union[int, None]:
		"""Return a customer account number.

		kwargs:
		-------
		supplier:
			An `int` or `str` representing the supplier
			number stated on a document.

		business_unit:
			An `int` or `str` representing the business unit number
			stated on the document or the `head_office` literal.

		Note:
		-----
		Unrecognized kwargs are ignored.

		Returns:
		--------
		An 'int' representing the customer account.
		If no account is found that matches the specified
		criteria, then 'None' is returned.
		"""
		self._validate_input(kwargs, "supplier", "business_unit")

		suppl = kwargs["supplier"]
		busin_unit = kwargs["business_unit"]

		query = f"supplier == '{suppl}' and business_unit == '{busin_unit}'"
		self._print_query(query)
		res = self._data.query(query)
		acc = None if res.empty else int(res["account"].iloc[0])

		return acc

class BahagAccountMap(AccountMap):
	"""Represents a 'Bahag' account map."""

	def get_account(self, **kwargs) -> Union[int, None]:
		"""Return a customer account number.

		kwargs:
		-------
		supplier:
			An `int` representing the supplier
			(Lieferant) number stated on a document.

		business_unit:
			An `int` representing the business unit number
			stated on the document or the `head_office` literal.

		Note:
		-----
		Unrecognized kwargs are ignored.

		Returns:
		--------
		An 'int' representing the head office account.
		If no account is found that matches the specified
		criteria, then 'None' is returned.
		"""
		self._validate_input(kwargs, "supplier", "business_unit")

		busin_unit = kwargs["business_unit"]
		suppl = kwargs["supplier"]

		query = f"supplier == '{suppl}' and business_unit == '{busin_unit}'"
		self._print_query(query)
		res = self._data.query(query)
		acc = None if res.empty else int(res["account"].iloc[0])

		return acc

class HagebauAccountMap(AccountMap):
	"""Represents a 'Hagebau' account map."""

	def get_account(self, **kwargs) -> Union[int, None]:
		"""
		Return a customer account number.

		kwargs:
		-------
		business_unit:
			An `int` representing the business unit number
			stated on the document or the `head_office` literal.

		Note:
		-----
		Unrecognized kwargs are ignored.

		Returns:
		--------
		An 'int' representing the customer account.
		If no account is found that matches the specified
		criteria, then 'None' is returned.
		"""
		self._validate_input(kwargs, "business_unit")

		busin_unit = kwargs["business_unit"]
		query = f"business_unit == '{busin_unit}'"

		self._print_query(query)
		res = self._data.query(query)
		acc = None if res.empty else int(res["account"].iloc[0])

		return acc

class MarkantAccountMap(AccountMap):
	"""Represents a 'Markant' account map."""

	def get_account(self, **kwargs) -> Union[int, None]:
		"""
		Return a customer account number.

		kwargs:
		-------
		supplier: `int`
			Supplier (ILN) number stated on the document.

		Note:
		-----
		Unrecognized kwargs are ignored.

		Returns:
		--------
		An 'int' representing the customer account.
		If no account is found that matches the specified
		criteria, then 'None' is returned.
		"""
		self._validate_input(kwargs, "supplier")

		suppl = kwargs["supplier"]
		query = f"supplier == '{suppl}'"

		self._print_query(query)
		res = self._data.query(query)
		acc = None if res.empty else int(res["account"].iloc[0])

		return acc


class MetroAccountMap(AccountMap):
	"""Represents a 'Metro' account map."""

	def get_account(self, **kwargs) -> Union[int, None]:
		"""
		Return a customer account number.

		kwargs:
		-------
		business_unit:
			An `int` representing the business unit number
			stated on the document or the `head_office` literal.

		Note:
		-----
		Unrecognized kwargs are ignored.

		Returns:
		--------
		An 'int' representing the customer account.
		If no account is found that matches the specified
		criteria, then 'None' is returned.
		"""
		self._validate_input(kwargs, "business_unit")

		busin_unit = kwargs["business_unit"]
		query = f"business_unit == '{busin_unit}'"

		self._print_query(query)
		res = self._data.query(query)
		acc = None if res.empty else int(res["account"].iloc[0])

		return acc


class MapLoader:
	"""Loader for account maps."""

	def load(self) -> dict:
		"""Load available account maps from excel data."""

		map_dir = join(APP_ROOT, "engine", "claim", "core", "maps")

		maps = {
			"BAHAG_DE": BahagAccountMap(map_dir, "BAHAG_DE"),
			"BAHAG_AT": BahagAccountMap(map_dir, "BAHAG_AT"),
			"BAHAG_SI": BahagAccountMap(map_dir, "BAHAG_SI"),
			"HAGEBAU_AT": HagebauAccountMap(map_dir, "HAGEBAU_AT"),
			"HAGEBAU_DE": HagebauAccountMap(map_dir, "HAGEBAU_DE"),
			"MARKANT_AT": MarkantAccountMap(map_dir, "MARKANT_AT"),
			"MARKANT_DE": MarkantAccountMap(map_dir, "MARKANT_DE"),
			"METRO_AT": MetroAccountMap(map_dir, "METRO_AT"),
			"OBI_AT": ObiAccountMap(map_dir, "OBI_AT"),
			"OBI_CH": ObiAccountMap(map_dir, "OBI_CH"),
			"OBI_DE": ObiAccountMap(map_dir, "OBI_DE"),
			"OBI_SI": ObiAccountMap(map_dir, "OBI_SI")
		}

		return maps
