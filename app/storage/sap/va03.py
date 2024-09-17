# pylint: disable = C0301, R0903

"""Mediates operations performed in SAP VA03 Transaction."""

from ... import logger
from typing import Union, overload
from . import rfc, Invoice, Delivery, PurchaseOrder, Account

class DocumentsNotFoundWarning(Warning):
	"""When a document is not found."""

class DocumentNotFoundError(Exception):
	"""When a document is expected but not found."""

class DeliveryNotFoundError(DocumentNotFoundError):
	"""When a delivery is expected but not found."""

class InvoiceNotFoundError(DocumentNotFoundError):
	"""When an invoice is expected but not found."""

g_log = logger.get_global_logger()

def _get_accounting_docs(sales_docs: list) -> dict:
	"""
	Returns accounting documents
	associated with sales documents.
	"""

	result = []

	for sales_doc in sales_docs:

		assert isinstance(sales_doc, str), "Sales document not a 'str'! RFC accepts 'str' values only!"

		# Get billing doc number (invoice)
		resp = rfc.RFC_READ_TABLE(
			rfc.connection,
			query_table = 'VBFA',
			options = [
				{'TEXT': f"VBELV = '{sales_doc}'"},
				{'TEXT': "AND VBTYP_N = 'M'"}
			],
			fields = [{'FIELDNAME': 'VBELN'}],
			data_format = 'structured',
			rowcount = 1
		)

		if len(resp['DATA']) != 0:
			invoice = resp['DATA'][0]['VBELN']
		else:
			invoice = None

		# Get outbound delivery number
		resp = rfc.RFC_READ_TABLE(
			rfc.connection,
			query_table = 'VBFA',
			options = [
				{'TEXT': f"VBELV = '{sales_doc}'"},
				{'TEXT': "AND VBTYP_N = 'J'"}
			],
			fields = [{'FIELDNAME': 'VBELN'}],
			data_format = 'structured',
			rowcount = 1
		)

		if len(resp['DATA']) != 0:
			delivery = resp['DATA'][0]['VBELN']
		else:
			delivery = None

		# Get sold-to (cutomer account number)
		resp = rfc.RFC_READ_TABLE(
			rfc.connection,
			query_table = 'VBAK',
			options = [
				{'TEXT': f"VBELN = '{sales_doc}'"}
			],
			fields = [{'FIELDNAME': 'KUNNR'}],
			data_format = 'structured',
			rowcount = 1
		)

		acc_num = resp['DATA'][0]['KUNNR']

		if invoice is None and delivery is None:
			raise DocumentsNotFoundWarning(
				"Neither a debit note nor an invoice was found. "
				"However, they are not expected to be issued if "
				"the goods was sold for own-consumption. "
				"A deeper investigation is suggested.")

		result.append({
			"sales_document": int(sales_doc),
			"invoice": int(invoice),
			"delivery": int(delivery),
			"account": int(acc_num)
		})

	return result

@overload
def find_accounting_documents(doc: Invoice) -> list:
	"""
	Searches for delivery notes associated with an invoice.

	Params:
	------
	doc: Represents the invoice issued by Ledvance.

	Returns:
	--------
	List of delivery notes found.
	"""

@overload
def find_accounting_documents(doc: Delivery) -> list:
	"""
	Searches for invoices associated with a delivery note.

	Params:
	------
	doc: Represents the delivery note of an order shipped by Ledvance.

	Returns:
	--------
	List of invoices found.
	"""

@overload
def find_accounting_documents(doc: PurchaseOrder, acc: Account) -> list:
	"""
	Searches for invoices associated with a delivery note.

	Params:
	------
	doc: Represents the purchase order made by the customer.
	acc: Represents the customer account assciated with the purchase order.

	Returns:
	--------
	A list of ...
	"""

def find_accounting_documents(doc: Union[Invoice, Delivery, PurchaseOrder], acc: Account = None) -> list:
	"""
	Searches for accounting documents.

	Params:
	------
	doc:
		Represents the reference to use for searching associated accounting documents:
		- instance of classs `Invoice`: Represents the invoice issued by Ledvance.
		- instance of classs `Delivery`: Represents the delivery note for an order shipped from Ledvance to the customer.
		- instance of classs `PurchaseOrder`: Represents the purchase order made by the customer.

	acc:
		Represents the customer account assciated with the purchase order (default `None`). \n
		Can be used only in combination with document of type `PurchaseOrder`.

	Represents the purchase order made by the customer.
	acc: Represents the customer account assciated with the purchase order.

	Rasies:
	-------
	DocumentNotFoundError:

	Returns:
	--------
	A list of ...
	"""

	if isinstance(doc, PurchaseOrder):

		po_num_fmt = str(doc)
		fld_name = "VBELN"
		query = [{'TEXT': f"BSTNK = '{po_num_fmt}'"}]

		if acc is not None:
			acc_num_fmt = rfc.format_number(int(acc))
			query.append({'TEXT': f"AND KUNNR = '{acc_num_fmt}'"})

		response = rfc.RFC_READ_TABLE(
			rfc.connection,
			query_table = 'VBAK',
			options = query,
			fields = [{'FIELDNAME': fld_name}],
			data_format = 'structured'
		)

	elif isinstance(doc, (Invoice, Delivery)):

		doc_fmt = rfc.format_number(int(doc))
		fld_name = "VBELV"

		response = rfc.RFC_READ_TABLE(
			rfc.connection,
			query_table = 'VBFA',
			options = [
				{'TEXT': f"VBELN = '{doc_fmt}'"},
				{'TEXT': "AND VBELV LIKE '02%'"}
			],
			fields = [{'FIELDNAME': fld_name}],
			data_format = 'structured'
		)

	else:
		raise TypeError(f"Argument 'doc' has incorrect type: {type(doc)}!")

	sales_docs = [entry[fld_name] for entry in response['DATA']]
	sales_docs = list(set(sales_docs))

	if len(sales_docs) == 0:
		if isinstance(doc, PurchaseOrder) and acc is not None:
			raise DocumentNotFoundError(
				"No accounting document found since no sales document exists for the purchase order. "
				"The order may have been created using an own-consumption-type account."
			)
		if isinstance(doc, Invoice):
			raise DeliveryNotFoundError(
				"Delivery not found since no sales document exists for the invoice. "
				"A credit memo may have been issued for the invoice, or the invoice "
				"represents a backbilling."
			)
		if isinstance(doc, Delivery):
			raise InvoiceNotFoundError(
				"Invoice not found since no sales document exists for the delivery. "
				"A credit memo may have been issued for the invoice."
			)

	records = _get_accounting_docs(sales_docs)

	assert isinstance(records, list) > 0, f"Return value should have a 'list' type, not '{type(records)}'!"
	assert len(records) != 0, "No accounting document was found!"

	for record in records:
		assert "sales_document" in record and isinstance(record["sales_document"], int)
		assert "invoice" in record and record["invoice"] is None or isinstance(record["invoice"], int)
		assert "delivery" in record and record["delivery"] is None or isinstance(record["delivery"], int)
		assert "account" in record and isinstance(record["account"], int)

	g_log.debug(f"Accounting document record(s): {records}")

	return records

def list_purchase_order_procucts(num: PurchaseOrder, tech_names: bool = True) -> list:
	"""Creates a list of products associated with a service notification.

	Parameters:
	-----------
	num:
		Number of the purchase order.
	
	tech_names:
		By default, the resulting data contain records with technical names as field names.
		If False, then English-based descriptors are used as the field names.

	Returns:
	--------
	retrieved data ...
	"""

	# get notificaton
	po_num = rfc.format_number(int(num), n_digits = 12)

	# from the outbound delivery get the list of items
	query = f"AUFNR = '{po_num}'"

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
