# pylint: disable = W0603

"""
The module provides a high-level interface for performing
for performing application-specific operations with a database.
"""

from collections.abc import Sequence, Collection
from datetime import datetime as dt
from typing import Any, Union

from pandas import DataFrame
import sqlalchemy as sqal
from sqlalchemy.sql.expression import bindparam
from sqlalchemy import MetaData, select, column
from sqlalchemy.sql.schema import Table
from sqlalchemy.sql.selectable import Select
from sqlalchemy.engine.base import Connection
from sqlalchemy.engine.cursor import CursorResult

from .. import logger

g_log = logger.get_global_logger()
_conn: Connection = None

class RecordNotFoundError(Exception):
	"""No record is found in the
	database for the specified selection criteria.
	"""

def _execute_query(qry: Union[Select, str], data: list = None) -> CursorResult:
	"""Execute a database query and return the result."""

	try:
		if data is None:
			response = _conn.execute(qry)
		else:
			response = _conn.execute(qry, data)
	except:
		_conn.connection.rollback()
		raise

	_conn.connection.commit()

	return response

def _compile_record(result: list, cols) -> dict:
	"""Convert the data retrieved as the result of a query \n
	into a dictionary of field names and their values.
	"""

	if len(result) == 0:
		return {}

	if isinstance(result, list):
		res = result[0]
	else:
		res = result

	rec = {}

	for idx, col in enumerate(cols):
		rec.update({col.name: res[idx]})

	return rec

def connect(
		host: str, port: int, name: str, user: str,
		password: str, debug: bool = False) -> None:
	"""Connect to the database engine.

	Params:
	-------
	host: Name of the database hosting server.
	port: Number of the port to connect to the server.
	name: Name of the database.
	user: A valid user name.
	passw: A valid password.
	"""

	global _conn

	url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"
	pool_debug = "debug" if debug else False

	engine = sqal.create_engine(url, echo_pool = pool_debug)

	try:
		_conn = engine.connect()
	except:
		engine.dispose()
		raise

def disconnect(self) -> None:
	"""Disconnect from the database engine."""

	global _conn

	if _conn is None:
		g_log.warning("Attempt to close a non-existent database connection ignored.")
		return

	_conn.close()
	_conn = None

def get_table(name: str, schema: str = None) -> Table:
	"""Get a database table.

	Params:
	-------
	name: The name of the table. \n
	schema:
		The name of the schema under which the table
		resides in the database (default: None).

		By default, the schema is not considered when \n
		detecting the table in the database. If a schema \n
		name is specified, then that schema will be used \n
		when searching for the specified table. \n

	Returns:
	--------
	An object that represents the database table.

	Raises:
	-------
	TableNotFoundError:
		When a table with the specified name does not exist in the database.

	ConnectionError:
		When attempting to use the procedure when no connection to the database exists.
	"""

	if _conn is None:
		raise ConnectionError("No connection to the database exists!")

	return Table(name, MetaData(), autoload_with = _conn, schema = schema)

def insert_value(table: Table, rec_id: int, col: str, value: Any) -> None:
	"""Insert a value into a specific field in a database record.

	Params:
	-------
	table: Database table in which the record exists.
	rec_id: Identification number of the record in database table.
	col: The name of the table column to update.
	value: Value to store in the record field.
	"""

	if table.name == "doc_data":
		id_col = "message_attachments_id"
	elif table.name == "documents":
		id_col = "id"
	else:
		raise ValueError(f"Unrecognized table name: '{table.name}'")

	query = table.update().where(
		table.c[id_col] == rec_id
	).values({
		col: value
	})

	_execute_query(query)

def get_value(table: Table, rec_id: int, col: str) -> Any:
	"""Get a record value from a database field.

	Params:
	-------
	table: Database table in which the record exists.
	rec_id: Identification number of the record in database table.
	col: The name of the table column on which to select.

	Returns:
	--------
	The value of the corresponding type as inferred from the DB record.
	"""

	query = select(
		table.c[col]
	).where(
		table.c["id"] == rec_id
	)

	response = _execute_query(query)
	result = response.fetchall()

	if len(result) == 0:
		raise RecordNotFoundError(
			f"No record with id: {rec_id} found "
			f"in database table: '{table.name}'."
		)

	return result[0][0]

def create_record(table: Table, **params) -> Union[int, None]:
	"""Create a new record in the database and return it's ID.

	Params:
	-------
	table: Database table where the record is created.
	params: Names of table columns and the corresponding values to be stored.

	Returns:
	--------
	The ID number of the record created in the database table.
	If the operation fails, then None is returned.
	"""

	query = table.insert().values(params)
	result = _execute_query(query)

	# docasne riesenie. do buducna radsej sprait v tabulke primary key
	if len(result.inserted_primary_key) == 0:
		return None

	rec_id = result.inserted_primary_key[0]

	return rec_id

def update_record(table: Table, rec_id: int, **params) -> bool:
	"""Update database record on new values and return the operation status.

	Params:
	-------
	table: Database table containing the record to be updated.
	rec_id: The ID number of the record to be updated.
	params: Names of table columns and the corresponding values to be updated.

	Returns:
	--------
	True if the record was successfully updated, False if not.
	"""

	update_vals = params.copy()

	update_vals.update({
		"last_update": dt.now().strftime("%m/%d/%Y, %H:%M:%S")
	})

	query = table.update().where(
		table.c["id"] == rec_id
	).values(update_vals)

	resp =_execute_query(query)

	return resp.rowcount != 0

def update_records(table: Table, data: list) -> int:
	"""Perform a bulk update of table records with
	data and return the count of the updated records.

	Params:
	-------
	table: Database table containing the record to be updated.

	data:
		Data to store in te following format:

		[
			{'_id': record_id, field_name_a : value_a1, field_name_b: value_b1},
			{'_id': record_id, field_name_a : value_a2, field_name_b: value_b2},
		]

		Example:

		[
			{'_id': 10000002, 'customer_folder' : 'AMAZON_DE', 'status': 'done'}, \n
			{'_id': 10000004, 'customer_folder' : 'OBI_AT', 'status': 'manual'},
		]

	Returns:
	--------
	Number of the updated rows.
	"""

	vals = {}

	for k in data[0].keys():

		if k == "_id":
			continue

		vals.update({k: bindparam(k)})

	query = table.update().where(
		table.c["id"] == bindparam('_id')
	).values(vals)

	response = _execute_query(query, data)
	updated = response.last_updated_params()

	return len(updated)

def get_records(table: Table, col: str, value: Any) -> tuple:
	"""Get records from a database table.

	Params:
	-------
	table: Database table containing the records.
	col: The name of the table column on which to select.
	value: Value or a collection of values representing the selection criteria. \n

	Returns:
	--------
	A tuple of database records stored as dicts with field names \n
	mapped to field values. If no record is found for a given ID, \n
	then an empty tuple is returned.
	"""

	if isinstance(value, (Sequence, Collection)) and not isinstance(value, (str, bytes, bytearray)):
		# collections not accempted by SqlAlchemy
		# interface may get passed, hence the cast
		values = list(value)
	else:
		values = [value]

	query = select(['*']).where(table.c[col].in_(values))
	result = _execute_query(query)

	recs = []

	for res in result:
		recs.append(_compile_record(res, table.columns))

	return tuple(recs)

def get_records2(table: Table, search_col: str, value: Any, return_col = "*") -> tuple:
	"""Get records from a database table.

	Params:
	-------
	table: Database table containing the records.
	column: The name of the table column on which to select.
	value: Value or a collection of values representing the selection criteria. \n

	Returns:
	--------
	A tuple of database records stored as dicts with field names \n
	mapped to field values. If no record is found for a given ID, \n
	then an empty tuple is returned.
	"""

	if isinstance(value, (Sequence, Collection)) and not isinstance(value, (str, bytes, bytearray)):
		# collections not accempted by SqlAlchemy
		# interface may get passed, hence the cast
		values = list(value)
	else:
		values = [value]

	if "*" in value:
		value = value.replace("*", "%")
		query = select(column(return_col)).where(table.c[search_col].like(value))
	else:
		query = select(return_col).where(table.c[search_col].in_(values))

	result = _execute_query(query)

	recs = [res[0] for res in result.all()]

	return tuple(recs)

def get_record(table: Table, rec_id: int) -> Union[dict,None]:
	"""Get a record from a database table.

	Params:
	-------
	table: Database table containing the record.
	rec_id: The ID number of the record.

	Returns:
	--------
	Field names and the associated data.

	If no record is found with a given ID, then None is returned.
	"""

	query = select(['*']).where(table.c["id"] == rec_id)
	response = _execute_query(query)
	result = response.fetchall()
	record = _compile_record(result, table.columns)

	return record

def delete_record(table: Table, doc_hash: str) -> tuple:
	"""Delete a record in the database and return the operation result.

	Params:
	-------
	table: Database table containing the record to be deleted.
	doc_hash: Hash value calculated from the PDF content.

	Returns:
	--------
	A tuple of `int' values representing the ID numbers of the deleted records.
	"""

	query = table.delete().where(table.c.doc_hash == doc_hash).returning(table.c["id"])
	response = _execute_query(query)
	result = response.fetchall()
	row_nums = [num[0] for num in result]

	return tuple(row_nums)

def get_table_content(table: Table) -> DataFrame:
	"""
	Retrieves contents of a database table.

	Params:
	-------
	table: Database table whose contents are to be retrieved.

	Returns:
	--------
	A DataFrame object containing the table data.
	"""

	qry = table.select()
	result = _execute_query(qry)
	result = DataFrame(result.fetchall())

	return result

def query(table: Table, statement: str) -> CursorResult:
	"""
	Executes query on a table.

	Params:
	-------
	table:
		Database table to be queried.

	statement:
		The query to exeute.

	Returns:
	--------
	The result of the query represented
	by an SqlAlchemy:CursorResult object.
	"""

	return _execute_query(statement)
