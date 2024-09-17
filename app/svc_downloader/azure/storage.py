# pylint: disable = W0718, W1203, R0913

"""
The module provides a high-level interface for
manipulation with files stored in the Azure Blob Storage.
"""

import json
import re
from glob import glob
import os
from os.path import basename, isfile, join, split, splitext
from typing import Any, Union
from azure.storage.blob import BlobServiceClient, ContainerClient
from ... import logger

VirtualPath = str
VirtualPaths = list
LocalPath = str
LocalPaths = list
Blobs = list
Client = Union[BlobServiceClient, ContainerClient]

g_log = logger.get_global_logger()

class BlobExistsError(Exception):
	"""When a file to upload already exists in the blob storage."""

class BlobDownloadError(Exception):
	"""When downloading the BLOB contents to a local file fails."""

class ContainerCreationError(Exception):
	"""When containercreation fails."""

class FolderNotFoundError(Exception):
	"""When a folder is requested but doesn't exist."""

class BlobNotFoundError(Exception):
	"""When a BLOB object is requested but doesn't exist."""

def _compile_file_path(dst_dir: LocalPath, blob_name: str) -> str:
	"""Compiles a new file path if a given file exists."""

	nth = 0
	name, ext = splitext(blob_name)

	while True:
		nth += 1
		blob_name = name + f" Copy ({nth})" + ext
		dst_path = join(dst_dir, blob_name)

		if not isfile(dst_path):
			return dst_path

def _format_extension(val: Union[str,list] = None) -> list:
	"""Formats file extension into a lowercase, period-prefixed string. """

	result = []
	val = ".*" if val is None else val
	extensions = [val] if isinstance(val, str) else val

	for ext in extensions:
		ext = ext.strip(".").strip().lower()
		ext = "." + ext
		result.append(ext)

	return result

def get_service_client(
		acc_name: str,
		acc_key: str,
		endpoint_protocol: str,
		endpoint_suffix: str
	) -> BlobServiceClient:
	"""
	Creates a service client for the BLOB storage.

	Params:
	------
	acc_name:
		Name of the account for the BLOB storage.

	acc_key:
		Key of the BLOB storage account.

	endpoint_protocol:
		Endpoint protocol used to communicate with the BLOB storage.

	endpoint_suffix:
		Suffix string that defines the type of the storage account.

	Returns:
	--------
	A client to interact with the BLOB storage at the account level.
	"""

	conn_str = ";".join([
		f"DefaultEndpointsProtocol={endpoint_protocol}",
		f"AccountName={acc_name}",
		f"AccountKey={acc_key}",
		f"EndpointSuffix={endpoint_suffix}"
	])

	return BlobServiceClient.from_connection_string(conn_str)

def get_container_client(
		client: BlobServiceClient,
		name: str
	) -> ContainerClient:
	"""
	Creates a container client for BLOB storage.

	Params:
	-------
	client:
		The Blob Service Client object.

	name:
		Name of the BLOB container.

	Returns:
	--------
	A client to interact with the BLOB
	storage at the container level.
	"""

	return client.get_container_client(name)

def release_client(client: Client) -> None:
	"""
	Closes connection to a blob storage client.

	Params:
	-------
	client:
		A service, storage or blob client object.
	"""
	client.close()

def create_container(
		client: BlobServiceClient,
		name: str
	) -> ContainerClient:
	"""
	Creates a container in the BLOB storage.

	Params:
	-------
	client:
		The BLOB Service Client object.

	name:
		Name of the container to create.

	Returns:
	--------
	The container client object.
	"""

	container = client.get_container_client(name)

	try:
		container.create_container()
		g_log.info("Container created: %s", name)
	except Exception as exc:
		g_log.error(f"Failed to create container: '{name}'!")
		# better raise an error and let the caller handle it
		raise ContainerCreationError(
			f"Failed to create container: {name}") from exc

	return client.get_container_client(name)

def list_blob_paths(
		client: ContainerClient,
		src_dir: VirtualPath = None,
		name_filter: str = None,
		ext: str = None
	) -> list:
	"""
	Creates a list of BLOB names.

	Params:
	-------
	client:
		The client for the container where the BLOBs are stored.

	src_dir:
		Path to a virtual directory where the BLOB objects are stored.
		By default, BLOBs from all direcories are listed. If a valid
		path is used, then names of BLOBs contained in that specified
		directory are listed.

	name_filter:
		Regex-compatible pattern for filtering files by matching
		the pattern string with their names. By default, no filtering
		is performed.

	ext:
		File types to list.
		If a file extension is used (e.g. '.pdf', 'json'),
		then only these file types are included in the list.
		By default, all file types are listed.

	Returns:
	--------
	A list of file names stored as strings.
	"""

	try:
		blob_paths = client.list_blob_names()
	except Exception as exc:
		raise RuntimeError(
			"Failed to create list of BLOB names stored "
			f"in the container: {str(exc)}") from exc

	filtered = []
	name_filter = "" if name_filter is None else name_filter

	for blob_path in blob_paths:

		blob_dir, blob_fullname = split(blob_path)
		blob_ext = splitext(blob_fullname)[1]

		if src_dir is not None and blob_dir != src_dir:
			continue

		if ext is not None and blob_ext != ext:
			continue

		if re.match(name_filter, blob_fullname) is None:
			continue

		filtered.append(blob_path)

	return list(filtered)

def exists_blob(
		client: ContainerClient,
		blob_path: VirtualPath
	) -> bool:
	"""
	Checks whether a BLOB object exists under a given path.

	Params:
	-------
	client:
		The client for the container where the BLOB is stored.

	blob_path:
		Virtual path to the BLOB object that exists in the storage.
		If the object doesn't exist, a BlobNotFoundError exception
		is raised.

	Returns:
	--------
	True, if the BLOB objects exists, otherwise False.
	"""

	blob_client = client.get_blob_client(blob = blob_path)
	return blob_client.exists()

def list_blobs(
		client: ContainerClient,
		src_dir: VirtualPath = None,
		name_filter: str = None,
		ext: str = None
	) -> list:
	"""
	Creates a list of BLOB objects.

	Params:
	-------
	client:
		The client for the container where the BLOBs are stored.

	src_dir:
		Path to a virtual directory where
		the BLOB objects are stored. By default,
		BLOBs from all direcories are listed.
		If a valid path is used, then BLOBs contained
		in that specified directory are listed.

	name_filter:
		Regex-compatible pattern for filtering
		files by matching the pattern string
		with their names.
		By default, no filtering is performed.

	ext:
		File types to list.
		By default, all file types are listed.
		If a file extension is used (e.g. '.pdf', 'json'),
		then only these file types are included in the list.

	Returns:
	--------
	A list of BLOB objects.

	Raises:
	-------
	RuntimeError:
		When creating of the list of BLOBs fails.
	"""

	try:
		blobs = client.list_blobs()
	except Exception as exc:
		raise RuntimeError(
			"Failed to list BLOBs stored in the "
			f"container: {str(exc)}") from exc

	filtered = []
	name_filter = "" if name_filter is None else name_filter

	for blob in blobs:

		blob_dir, blob_fullname = split(blob.name)
		blob_name, blob_ext = splitext(blob_fullname)

		if src_dir is not None and blob_dir != src_dir:
			continue

		if ext is not None and blob_ext != ext:
			continue

		if re.match(name_filter, blob_name) is None:
			continue

		filtered.append(blob)

	return list(filtered)

def create_blob(
		client: ContainerClient,
		src_file: LocalPath,
		dst_dir: VirtualPath,
		overwrite: bool = False,
		remove: bool = False
	) -> VirtualPath:
	"""
	Uploads a file to the BLOB storage.

	Params:
	-------
	client:
		The client for the container where the BLOB will be created.

	src_file:
		Path to a local file.

	dst_dir:
		Path to the virtual storage directory where
		the file will be uploaded as a BLOB object.

	overwrite:
		If True, and the BLOB already exists in the
		storage, then its contents will be overwritten.
		By default, the BLOB is not overwritten and
		a BlobExistsError is raised instead.

	remove:
		If True, then the local file will be
		removed once the BLOB is created.

	Raises:
	-------
	BlobExistsError:
		If a contents of the file to be uploaded upload already
		exist in the storage as a BLOB object. The warning is
		suppressed by setting the 'overwrite' parameter to True.

	Returns:
	--------
	Path to the BLOB object in the storage.
	"""

	filename = split(src_file)[1]
	dst_dir = dst_dir.rstrip("/")
	blob_path = "/".join([dst_dir, filename])
	blob_client = client.get_blob_client(blob = blob_path)

	if blob_client.exists():
		if not overwrite:
			raise BlobExistsError(
				"A BLOB with the same name already exists in the "
				f"container: {filename}. The file won't be uploaded.")

		g_log.warning(
			"A BLOB with the same name already exists in the "
			f"container: {filename}. The BLOB will be overwritten.")

	with open(src_file, "rb") as stream:
		blob_client.upload_blob(stream, overwrite = True)

	if remove:
		try:
			os.remove(src_file)
		except Exception as exc:
			g_log.exception(exc)

	release_client(blob_client)

	return blob_path

def create_blobs(
		client: ContainerClient,
		src_paths: LocalPaths,
		dst_dir: VirtualPath,
		overwrite: bool = False,
		remove: bool = False
	) -> None:
	"""
	Uploads local files to the BLOB storage.

	Params:
	-------
	client:
		The client for the container where the BLOBs will be created.

	src_paths:
		Path to a local directory containing
		the files to be uploaded.

	dst_dir:
		Path to a storage directory where
		files are uploaded as BLOB objects.

	overwrite:
		If True, and the BLOBs already exist in the
		storage, then their contents will be overwritten.
		By default, the BLOBs are not overwritten.

	remove:
		If True, then the local files will be
		removed once the BLOBs are created.
	"""

	for src_file in src_paths:

		filename = basename(src_file)

		try:
			create_blob(client, src_file, dst_dir, overwrite, remove)
			g_log.info(f"Uploaded file: {filename}")
		except BlobExistsError:
			g_log.warning(
				"A file with the same name already exists in the "
				f"container: '{filename}'. The file won't be uploaded.")
		except Exception as exc:
			g_log.error(f"Failed to upload file: '{filename}'. Details: {str(exc)}")

def list_files(
		src_dir: LocalPath,
		name_filter = None,
		ext: Union[str,list] = None
	) -> list:
	"""
	Creates a list of file names stored in a local directory.

	Params:
	-------
	src_dir:
		Path to a local directory where
		the files objects are stored.

	name_filter:
		Pattern for filtering files by matching
		the pattern string with their names.
		By default, no filtering is performed.

		The pattern may contain simple shell-style wildcards a la
		fnmatch. However, unlike fnmatch, filenames starting with a
		dot are special cases that are not matched by '*' and '?'
		patterns.

	ext:
		File type(s) to list.
		By default, all file types are listed.
		If a file extension is used (e.g. '.pdf', 'json'),
		then only these file types are included in the list.

	Returns:
	--------
	A list of file names stored as strings.
	"""

	file_paths = []
	name_filter = "*" if name_filter is None else name_filter

	for file_ext in _format_extension(ext):
		filename_patt = f"{name_filter}{file_ext}"
		file_paths += glob(join(src_dir, filename_patt))

	return file_paths

def download_blob(
		client: ContainerClient,
		blob_path: VirtualPath,
		dst_dir: LocalPath,
		duplicate: str = "raise",
	) -> LocalPath:
	"""
	Saves the contents of a BLOB object into a local file.

	Params:
	-------
	client:
		The client for the container where the BLOB is stored.

	src_path:
		Virtual path to the BLOB object.

	dst_dir:
		Path to a local directory where the
		downloaded contents will be saved.

	duplicate:
		Action to take if the destination file already exists:
			- "raise": The FileExistsError exception is raised (default behavior).
			- "copy": A copy of the file is created.
			- "overwrite": The destination file is overwritten.

	Raises:
	-------
	FileExistsError:
		If a local file to be created already exists
		in a local directory. The exception is suppressed
		by setting the 'overwrite' parameter to True.

	BlobDownloadError:
		If attempt to download the BLOB fails.

	Returns:
	--------
	Path to the downloaded local file.
	"""

	blob_name = basename(blob_path)
	dst_path = join(dst_dir, blob_name)

	if isfile(dst_path):

		if duplicate not in ("raise", "copy", "overwrite"):
			raise ValueError(f"Unrecognized value of the 'duplicate' argument: '{duplicate}'!")

		if duplicate == "raise":
			raise FileExistsError(f"The specified file already exists: '{dst_path}'")
		if duplicate == "copy":
			dst_path = _compile_file_path(dst_dir, blob_name)
		elif duplicate == "overwrite":
			pass

	blob_client = client.get_blob_client(blob = blob_path)

	if not blob_client.exists():
		raise BlobNotFoundError(f"No such BLOB exists in the storage: '{blob_path}'")

	try:
		with open(dst_path, "wb") as blob_stream:
			download_stream = blob_client.download_blob()
			blob_stream.write(download_stream.readall())
	except Exception as exc:
		raise BlobDownloadError(
			f"Failed to download BLOB: '{blob_path}'. Details: {str(exc)}") from exc

	return dst_path

def download_blobs(
		client: ContainerClient,
		blob_paths: VirtualPaths,
		dst_dir: LocalPath,
		duplicate: str = "raise",
	) -> LocalPaths:
	"""
	Saves the contents of BLOB objects into local files.

	Params:
	-------
	client:
		The client for the container where the BLOBs are stored.

	blob_paths:
		Virtual paths to the BLOB objects to be downloaded.

	dst_dir:
		Path to a local directory where the
		downloaded contents will be saved.

	duplicate:
		Action to take if a destination file already exists:
			- "raise": The FileExistsError exception is raised (default behavior).
			- "copy": Copies of the files are created.
			- "overwrite": The destination files are overwritten.

	Returns:
	--------
	Paths to the downloaded local files.

	Raises:
	-------
	FileExistsError:
		If a local file to be created already exists
		in a local directory. The exception is suppressed
		by setting the 'overwrite' parameter to True.
	"""

	file_paths = []

	for blob_path in blob_paths:
		try:
			file_path = download_blob(client, blob_path, dst_dir, duplicate)
		except BlobDownloadError as exc:
			g_log.error(exc)
		else:
			file_paths.append(file_path)

	return file_paths

def remove_blob(
		client: ContainerClient,
		blob_path: VirtualPath
	) -> None:
	"""
	Removes a BLOB object from the storage.

	Params:
	-------
	client:
		The client for the container where the BLOB is stored.

	blob_path:
		Virtual path to the BLOB object that exists in the storage.
		If the object doesn't exist, a BlobNotFoundError exception
		is raised.

	Raises:
	-------
	BlobNotFoundError:
		When a BLOB object is requested but doesn't exist.
	"""

	blobs = list_blob_paths(client)
	blob_paths = set(blobs).intersection([blob_path])
	assert len(blob_paths) <= 1, "Identical file paths cannot coexist in the blob storage!"

	if len(blob_paths) == 0:
		raise BlobNotFoundError(f"No such BLOB exists in the storage: '{blob_path}'")

	blob_path = list(blob_paths)[0]
	blob_client = client.get_blob_client(blob_path)
	blob_client.delete_blob()

def remove_blobs(
		client: ContainerClient,
		blob_paths: VirtualPaths,
	) -> None:
	"""
	Removes BLOB objects from the storage.

	Params:
	-------
	client:
		The client for the container where the BLOBs are stored.

	blob_paths:
		Virtual paths to the BLOB objects to remove.
		If the object doesn't exist, a BlobNotFoundError
		exception is raised.

	name_filter:
		Pattern for filtering files by matching
		the pattern string with their names.

		The pattern may contain simple shell-style wildcards a la
		fnmatch. However, unlike fnmatch, filenames starting with a
		dot are special cases that are not matched by '*' and '?'
		patterns.

		By default, no filtering is performed.

	ext:
		Type of files to upload.

		By default, files are not filtered by their file type.
		If a file extension is used (e.g. '.pdf', 'json'), then
		only those file types will be uploaded. The parameter is
		not case sensitve. Accepted are extensions prefixed or
		unprefixed with a period.

	Raises:
	-------
	BlobNotFoundError:
		When a BLOB object is requested but doesn't exist.
	"""

	for blob_path in blob_paths:
		try:
			remove_blob(client, blob_path)
			g_log.info(f"BLOB removed: '{blob_path}'")
		except BlobNotFoundError as exc:
			g_log.error(exc)

def get_blob_content(
		client: ContainerClient,
		blob_path: VirtualPath,
		raw: bool = False
	) -> Any:
	"""
	Retrieves the content of a BLOB from the storage.

	Params:
	-------
	client:
		The client for the container where the BLOB is stored.

	blob_path:
		Virtual path to the blob object.

	raw:
		If True, then content of the
		BLOB is returned as raw bytes.

		If False and the BLOB stores one of the following native Python objects
			- dict
			- str
		then the method tries to convert the BLOB bytes to that object.
		If the conversion fails, then the original BLOB bytes are returned.

	Raises:
	-------
	BlobNotFoundError:
		When the BLOB object doesn't exist under the specified path.

	Returns:
	--------
	The contents of the BLOB object.
	If the object format is native to Python and raw is False,
	then the method tries to convert the BLOB bytes to that
	object. If the conversion fails or raw is True, then the
	BLOB bytes are returned.
	"""

	blob_client = client.get_blob_client(blob_path)

	if not blob_client.exists():
		raise BlobNotFoundError(f"No such BLOB exists in the storage: '{blob_path}'")

	blob_data = blob_client.download_blob()

	if raw:
		return blob_data.content_as_bytes()

	if blob_path.lower().endswith(".json"):
		content = blob_data.content_as_text()
		try:
			data = json.loads(content)
		except Exception:
			return content
		else:
			return data
	elif blob_path.lower().endswith((".txt", ".log")):
		return blob_data.content_as_text()

	return blob_data.content_as_bytes()

