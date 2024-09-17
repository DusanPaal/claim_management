"""Contains classes used across the package."""

class Document:
	"""Base class for documents."""

	def __init__(self, val: int) -> None:
		"""Creates a document."""

		self._value = val

	def __int__(self) -> int:
		return self._value

	def __str__(self) -> str:
		return str(self._value)

class Invoice(Document):
	"""Represents an invoice."""

	def __init__(self, val: int) -> None:
		"""Creates an invoice."""

		if not isinstance(val, int):
			raise TypeError(f"Value of type 'int' expected, but got '{val}'!")

		if len(str(val)) != 9:
			raise ValueError(f"Value {val} doesn't represent a valid invoice number!")

		Document.__init__(self, val)

class Delivery(Document):
	"""Represents a delivery note."""

	def __init__(self, val: int) -> None:
		"""Creates a delivery note."""

		if not isinstance(val, int):
			raise TypeError(f"Value of type 'int' expected, but got '{val}'!")

		if not (len(str(val)) == 9 and str(val).startswith("31")):
			raise ValueError(f"Value {val} doesn't represent a valid delivery note number!")

		Document.__init__(self, val)

class PurchaseOrder(Document):
	"""Represents a purchase order made by the customer."""

	def __init__(self, val: int) -> None:
		"""Creates a purchase order."""

		if not isinstance(val, int):
			raise TypeError(f"Value of type 'int' expected, but got '{val}'!")

		if not 5 <= len(str(val)) <= 7:
			raise ValueError(f"Value {val} doesn't represent a valid purchase order number!")

		Document.__init__(self, val)

class Account:
	"""Represents a customer account."""

	def __init__(self, val: int) -> None:
		"""Creates an account."""

		if not isinstance(val, int):
			raise TypeError(f"Value of type 'int' expected, but got '{val}'!")

		if len(str(val)) != 7:
			raise ValueError(f"Value {val} doesn't represent a valid customer account!")

		self._value = val

	def __int__(self) -> int:
		return self._value

	def __str__(self) -> str:
		return str(self._value)
