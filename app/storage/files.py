# pylint: disable = C0302, R0903, W0718, W1203

"""
The module provides a tailored interface for
operations with files throughout the application.
"""

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Collection
from datetime import datetime
from glob import glob
from os.path import basename, isfile, join, split, splitext, dirname, exists
from typing import Any, Union, overload, Callable
import yaml
import pandas as pd
from pandas import DataFrame
from .. import logger

# used thrughout the app
PathOrName = str
DirPath = str
FilePath = str
FilePaths = list
PathsOrNames = list
Path = Union[DirPath,FilePath]

# used mainly by the azure package
VirtualPath = str
LocalPaths = str
LocalPath = str
VirtualPaths = list

APP_ROOT = sys.path[0]

g_log = logger.get_global_logger()

class UnsuportedFileFormatError(Exception):
	"""Operation on a file format that is not supoorted."""

class FileNameFormatError(Exception):
	"""File name format is incorrect."""

class FolderNotFoundError(Exception):
	"""A folder doesn't exist."""

class CaseID:
	"""Represents a case ID number."""

	def __init__(self, val: int) -> None:
		"""
		Constructor of class: `CaseID`.

		Params:
		-------
		val: Case ID value.
		"""

		if not isinstance(val, int):
			raise TypeError(f"Expeted an 'int' value, but got '{type(val)}'!")

		self._val = val

	def __str__(self) -> str:
		return str(self._val)

	def __int__(self) -> int:
		return int(self._val)

class RecordID:
	"""Represents a record ID number."""

	def __init__(self, val: int) -> None:
		"""
		Constructor of class: `RecordID`.

		Params:
		-------
		val: Record ID value.
		"""

		if not isinstance(val, int):
			raise TypeError(f"Expeted an 'int' value, but got '{type(val)}'!")

		self._val = val

	def __str__(self) -> str:
		return str(self._val)

	def __int__(self) -> int:
		return int(self._val)

class Paths:
	"""Operations with paths."""

	@staticmethod
	def get_relpath(src: Path, level: int = 1) -> str:
		"""
		Compiles a relative path from an absolute path.

		Params:
		-------
		src:
			Path to a directory or file.

		level:
			Depth of the relative path with respect to the last element of the source.

		Returns:
		--------
		The compiled path.
		"""

		# get directory path and file name
		dir_path, file_name = split(src)

		# get foldr names from the directory path
		tokens = dir_path.split(os.sep)
		relpath_tokens = [os.pardir]

		# if the file path is a net path,
		# remove empty string tokens from the list
		while "" in tokens:
			tokens.remove("")

		# get the depth of the ralative path
		depth = 1 if level < 1 else level
		rel_depth = min(depth, len(tokens))
		relpath_tokens.extend(tokens[-rel_depth:])

		# append the file name to the relative path tokens
		relpath_tokens.append(file_name)

		# compile the replative path and return the result
		return os.sep.join(relpath_tokens)

	@staticmethod
	def strip_extension_period(ext: Union[str,list]) -> Union[str,list]:
		"""Strips dot/period separator from file extensions."""

		if isinstance(ext, str):
			stripped = ext.lstrip(".")
		elif isinstance(ext, list):
			stripped = [e.lstrip(".") for e in ext]
		else:
			raise TypeError(type(ext))

		return stripped

	@staticmethod
	def get_file_format(file: FilePath) -> str:
		"""Identifies file format."""

		ext = splitext(file)[1]
		fmt = Paths.strip_extension_period(ext)

		return fmt.lower()

	@staticmethod
	def compile_file_path(src_path: FilePath, dst_dir: DirPath) -> str:
		"""Compiles a new file path if a given file exists."""

		max_copies = 1000
		nth = 0
		filename, ext = splitext(src_path)

		while True:
			nth += 1
			new_filename = filename + f" Copy ({nth})" + ext
			dst_path = join(dst_dir, new_filename)

			if not isfile(dst_path):
				return dst_path

			assert nth < max_copies, (
				"Cannot compile the file path! The number of "
				f"copies exceeded the limit {max_copies}.")

	@staticmethod
	def get_basename(files: PathsOrNames) -> str:
		"""
		Identifies base name of file names.

		Params:
		------
		names:
			File paths or names. Supported are only file names with identical extension.

		Returns:
		--------
		Common characters than represnt the base name.
		"""

		names = list(map(basename, files))

		if len(names) == 1:
			return names[0]

		exts = list(map(Paths.get_file_format, files))

		if len(set(exts)) != 1:
			raise ValueError("Mixing file extensions is not allowed!")

		ext = list(exts)[0]
		name_lengths = list(map(len, names))
		min_length = min(name_lengths)
		min_idx = name_lengths.index(min_length)
		shortest = names.pop(min_idx)

		for idx, char in enumerate(shortest):
			for name in names:
				if char != name[idx]:
					return ".".join([shortest[:idx-1], ext])

		return shortest

class Directory:
	"""Operations with directories."""

	def __init__(self, folder: DirPath) -> None:
		"""
		Constructor of class: `Directory`.

		Params:
		-------
		folder: Path to the folder to be manipulated.
		"""

		if not exists(folder):
			raise FolderNotFoundError(f"Directory not found: '{folder}'!")

		self._folder = folder

	def __str__(self) -> str:
		"""Action on casting to a `str` type."""
		return self._folder

	def is_empty(self) -> bool:
		"""Checks if a directory contains any files."""
		return len(self.list_dir()) == 0

	@property
	def path(self) -> str:
		"""Directory path."""
		return self._folder

	@property
	def name(self) -> str:
		"""Directory name."""
		return basename(self._folder)

	@overload
	def list_dir(self, recursive = False) -> list:
		"""
		Scans a directory for all files in a case-insensitive manner.

		Returns:
		--------
		A list of file paths.
		"""

	@overload
	def list_dir(self, ext: str, recursive = False) -> list:
		"""
		Scans a directory for files with a specific
		format in a case-insensitive manner.

		Params:
		-------
		rec_id:
			Database record ID number that identifies the files to be moved.
			The ID should be included in the file names.

		Returns:
		--------
		A list of file paths.
		"""

	@overload
	def list_dir(self, rec_id: int, recursive = False) -> list:
		"""
		Scans a directory for files with a specific
		record ID in a case-insensitive manner.

		Params:
		-------
		ext:
			File type extension (e.g. '.pdf').
			If `None` is used (default value),
			then all files in a directory will be listed.

		Returns:
		--------
		A list of file paths.
		"""

	@overload
	def list_dir(self, rec_id: int, ext: str, recursive = False) -> list:
		"""
		Scans a directory for files with a specific
		record ID and format in a case-insensitive manner.

		Params:
		-------
		rec_id:
			Database record ID number that identifies the files to be moved.
			The ID should be included in the file names.

		ext:
			File type extension (e.g. '.pdf').
			If `None` is used (default value),
			then all files in a directory will be listed.

		Returns:
		--------
		A list of file paths.
		"""

	def list_dir(self, rec_id: int = None, ext: str = None, recursive = False) -> list:
		"""
		Scans a directory for files in a case-insensitive manner.

		Params:
		-------
		rec_id:
			Database record ID number that identifies the files to be moved.
			The ID should be included in the file names.

		ext:
			File type extension (e.g. '.pdf').
			If `None` is used (default value),
			then all files in a directory will be listed.

		recursive:
			If true, then any files and zero or more \n
			directories and subdirectories will be matched.

		Returns:
		--------
		A list of file paths.
		"""

		return self.list_files(rec_id, ext, recursive)

	def list_files(self, rec_id: int = None, ext: str = None, recursive = False) -> list:
		"""
		Scans a directory for files in a case-insensitive manner.

		Params:
		-------
		rec_id:
			Database record ID number that identifies the files to be moved.
			The ID should be included in the file names.

		ext:
			File type extension (e.g. '.pdf').
			If `None` is used (default value),
			then all files in a directory will be listed.

		recursive:
			If true, then any files and zero or more \n
			directories and subdirectories will be matched.

		Returns:
		--------
		A list of file paths.
		"""

		if ext is not None:
			ext = Paths.strip_extension_period(ext)

		if rec_id is None:
			rec_patt = ""
			ext_patt = "*.*" if ext is None else f"*.{ext}"
		else:
			rec_patt = f"*_id={rec_id}"
			ext_patt = ".*" if ext is None else f".{ext}"

		patt = f"{rec_patt}{ext_patt}"

		if recursive:
			file_paths = glob(join(self._folder, "**", patt), recursive = True)
		else:
			file_paths = glob(join(self._folder, patt))

		return file_paths

	def list_dirs(self) -> list:
		"""
		Scans a directory for subfolders
		in a case-insensitive manner.

		Returns:
		--------
		A list of sub-directory paths.
		"""

		dir_paths = []

		for dir_name in os.listdir(self._folder):
			dir_paths.append(join(self._folder, dir_name))

		return dir_paths

	def clear(self) -> None:
		"""
		Removes the contents of the directory
		including files and subfolders.
		"""

		# remove all files
		file_paths = self.list_dir(recursive = True)

		for file_path in file_paths:
			try:
				File(file_path).remove()
			except Exception as exc:
				g_log.error(exc)

		# remove all subfolders
		subdir_paths = self.list_dirs()

		for subdir in subdir_paths:
			try:
				os.rmdir(subdir)
			except Exception as exc:
				g_log.error(exc)

class File:
	"""Operations with files."""

	_file = None

	def __init__(self, file: FilePath) -> None:
		"""
		Constructor of class `File`.

		Params:
		-------
		file: Path to the file to be manipulated.
		"""
		self._file = file

	def __str__(self) -> str:
		"""Action on casting to a `str` type."""
		return self._file

	@property
	def path(self) -> str:
		"""File path."""
		return self._file

	@property
	def dir_path(self) -> str:
		"""Directory path."""
		return dirname(self.path)

	@property
	def name(self) -> str:
		"""File name without extension."""
		name = self.fullname
		return splitext(name)[0]

	@property
	def fullname(self) -> str:
		"""File name with extension."""
		return basename(self._file)

	@property
	def dir_name(self) -> str:
		"""Name of the file directory."""
		return basename(dirname(self.path))

	def is_file(self, ext: str = None) -> bool:
		"""Checks if the represented file
		exists. If the file extension is
		specified, check whether a file with
		the same short name as the represented
		file exists.

		Params:
		-------
		ext: Extension to check (default None).

		By default, the existence of the represented file is checked.
		If an extension is used, then the existence of this file format
		with the short name identical with the represented file in the same
		directory is checked.
		"""
		if ext is None:
			return isfile(self._file)

		ext = Paths.strip_extension_period(ext)
		curr_ext = splitext(self.fullname)[1]

		return isfile(self._file.replace(curr_ext, curr_ext))

	def exists(self, ext: str = None) -> bool:
		"""Checks if the represented file exists.
		Synonym of the is_file() procedure."""

		return self.is_file(ext)

	def encode(self) -> None:
		"""Encodes the file contents to the
		Base64 encoded `bytes-like` object.
		"""

		content = self.read_bytes()
		content = base64.b64encode(content)
		Writer(self._file).write_bytes(content)

	def decode(self) -> str:
		"""Decodes the Base64 encoded
		bytes-like object or ASCII text."""

		content = self.read_bytes()
		decoded = base64.b64decode(content)

		return decoded.decode("utf-8")

	def read(self) -> Any:
		"""Reads file content."""
		return Reader(self._file).read()

	def read_bytes(self) -> bytes:
		"""Reads file binary content."""
		return Reader(self._file).read_bytes()

	def extract_record_id(self) -> RecordID:
		"""
		Extracts database record ID from a file name.

		Params:
		-------
		file: Path or name of file.

		Returns:
		--------
		ID number of the database record.
		"""

		match = re.search(r"_id=(\d+)", self._file)

		if match is None:
			raise FileNameFormatError(
				f"The file name '{self._file}' "
				"contains no record ID!")

		str_id = match.group(1)

		if len(str_id) < 4:
			raise FileNameFormatError(
				f"The file name '{self._file}' "
				f"contains incorrect record ID: {str_id}!")

		return RecordID(int(str_id))

	def calculate_hash(self) -> str:
		"""Calculates SHA256 hash value from the file content."""

		file_hash = hashlib.sha256()

		with open(self._file, "rb") as stream:
			content = stream.read()

		file_hash.update(content)
		hash_val = file_hash.hexdigest()

		return hash_val

	def rename(self, customer: str, rec_id: int) -> None:
		"""
		Renames the file using specific naming format.

		Params:
		-------
		customer: Name of the customer to whom the file relates.
		rec_id: ID number of the corresponding database record.
		"""
		folder_path, full_file_name = split(self._file)
		ext = splitext(full_file_name)[1]

		tag = f"_id={rec_id}"
		new_name = "".join([customer.lower(), "_document", tag, ext])
		new_path = join(folder_path, new_name)

		if new_path == self._file:
			return

		if isfile(new_path):
			os.remove(new_path)

		os.rename(self._file, new_path)
		self._file = new_path

	def remove(self) -> None:
		"""Removes the file."""
		os.remove(self._file)
		self._file = None

	def move(self, dst: DirPath) -> str:
		"""
		Moves the file to a destination directory.
		Any existing destination file will be
		overwritten with the source file.

		Params:
		-------
		dst: Path to the destination directory.

		Returns:
		--------
		Path to the new file destination.
		"""
		dst_file = join(dst, self.fullname)

		if isfile(dst_file):
			os.remove(dst_file)

		shutil.move(self._file, dst_file)

		return dst_file

	def copy(self, dst: DirPath) -> None:
		"""
		Copies the file to a destination directory.

		Params:
		-------
		dst: Path to the destination folder.
		"""

		file_name = split(self._file)[1]
		dst_file = join(dst, file_name)
		nth = 1

		while isfile(dst_file):
			name, ext = splitext(file_name)
			copy_name = f" - Copy {str(nth).zfill(3)}"
			new_name = "".join([name, copy_name, ext])
			dst_file = join(dst, new_name)
			nth += 1

		shutil.copyfile(self._file, dst_file)

class FileManager:
	"""Manages bulk operations with files."""

	@staticmethod
	@overload
	def move_files(
		src: Union[DirPath, Directory], dst: Union[DirPath, Directory],
		rec: RecordID, ext: Union[str,Collection] = None) -> None:
		"""
		Moves files with a specified record ID in their name to a destination folder \n
		and return the new file locations. Any existing destination file will be overwritten.

		Params:
		-------
		src: Path to the source folder containing the files to be moved.
		dst: Path to the destination folder where the files will be moved.
		rec: ID number of the file-related record in the database.
		ext: File type(s) to move (default None). By default, all file types are moved.

		Returns:
		--------
		A dictionary of file types and new file paths if files are
		moved successfully, or the original paths if the move fails.
		"""

	@staticmethod
	@overload
	def move_files(
		src: Union[DirPath, Directory], dst: Union[DirPath, Directory],
		case: CaseID, ext: Union[str,Collection] = None) -> None:
		"""
		Moves files with a specified record ID in their name to a destination folder \n
		and return the new file locations. Any existing destination file will be overwritten.

		Params:
		-------
		src: Path to the source folder containing the files to be moved.
		dst: Path to the destination folder where the files will be moved.
		case: ID number of the file-related case in DMS.
		ext: File type(s) to move (default None). By default, all file types are moved.

		Returns:
		--------
		A dictionary of file types and new file paths if files are
		moved successfully, or the original paths if the move fails.
		"""

	@staticmethod
	def move_files(
		src: Union[DirPath, Directory], dst: Union[DirPath, Directory],
		id_num: Union[RecordID, CaseID], ext: Union[str,Collection] = None)-> dict:
		"""
		Moves files with a specified record ID in their name to a destination folder \n
		and return the new file locations. Any existing destination file will be overwritten.

		Params:
		-------
		src: Path to the source folder containing the files to be moved.
		dst: Path to the destination folder where the files will be moved.
		id_num: ID number of either the file-related case in DMS or the database record.
		ext: File type(s) to move (default None). By default, all file types are moved.

		Returns:
		--------
		A dictionary of file types and new file paths if files are
		moved successfully, or the original paths if the move fails.
		"""

		# sanitize input
		exts = ["*"] if ext is None else Paths.strip_extension_period(ext)

		if isinstance(id_num, RecordID):
			search_patt = f"*_id={str(id_num)}"
		elif isinstance(id_num, CaseID):
			search_patt = f"*{str(id_num)}*"
		else:
			raise TypeError("Argument 'id_num' has incorrect type!")

		if isinstance(exts, str):
			exts = [exts]

		if isinstance(src, DirPath):
			src = Directory(src)

		if isinstance(dst, DirPath):
			dst = Directory(dst)

		new_paths = {}

		for f_ext in exts:

			src_paths = glob(join(str(src), f"{search_patt}.{f_ext}"))
			n_files = len(src_paths)

			if n_files == 0:
				continue

			for src_path in src_paths:

				orig_ext = splitext(src_path)[1]
				file_fmt = Paths.strip_extension_period(orig_ext)
				dst_path = join(str(dst), basename(src_path))

				src_relpath = Paths.get_relpath(src_path)
				dst_relpath = Paths.get_relpath(dst_path)

				g_log.info(f"Moving file: '{src_relpath}' -> '{dst_relpath}'")

				try:
					if isfile(dst_path):
						os.remove(dst_path)
					shutil.move(src_path, dst_path)
				except Exception as exc:
					g_log.exception(exc)
					new_paths.update({file_fmt: src_path})
				else:
					new_paths.update({file_fmt: dst_path})

		return new_paths

	@staticmethod
	def remove_files(src: Union[DirPath, Directory], rec_id: int) -> None:
		"""
		Removes files that contain a specific record ID in their name.

		Params:
		-------
		src:
			Path to the folder with the files to be renamed.

		rec_id:
			ID number of the database record.
			This ID is used to recognize the files to be moved \n
			and must be contained in the file names.
		"""

		if isinstance(src, DirPath):
			src = Directory(src)

		file_paths = src.list_dir(rec_id)
		n_files = len(file_paths)

		for nth, file_path in enumerate(file_paths, start = 1):
			rel_path = Paths.get_relpath(file_path)
			g_log.info(f"Removig file ({nth} of {n_files}): '{rel_path}'")
			os.remove(file_path)

	@staticmethod
	def rename_files(
		src: Union[DirPath, Directory],
		new_name: str, rec_id: int, id_tag = False,
		ext: Union[str, Collection] = None) -> dict:
		"""
		Renames document-related files. The new name is composed \n
		using the format: '%new_basename%_id=%record_id%.extension'.

		Params:
		-------
		src:
			Path to the folder with the files to be renamed.

		new_name:
			Base name of new document name without extension.

		rec_id:
			ID number of the database record.
			This ID is used to recognize the files to be moved \n
			and must be contained in the file names.

		id_tag:
			If True, then an record ID tag "_id=%rec_id%" will
			be appended to the new name, where the placeholder
			will be resolved to the specified record ID.

		ext:
			List of file formats to consider for renaming (default: None).
			By default, files are not filtered by their format.
			If extensions are used (".pdf"), then only the files specified
			by that format wil be renamed.
		"""

		# sanitize input
		exts = ["*"] if ext is None else Paths.strip_extension_period(ext)

		if isinstance(exts, str):
			exts = [exts]

		new_name = splitext(new_name)[0]

		if isinstance(src, DirPath):
			src = Directory(src)

		orig_paths = []

		for f_ext in exts:
			orig_paths.extend(src.list_dir(rec_id, f_ext))

		new_paths = {}

		for orig_path in orig_paths:

			orig_ext = splitext(orig_path)[1]
			tag = f"_id={rec_id}" if id_tag else ""
			new_fullname = f"{new_name}{tag}{orig_ext}"
			new_path = join(str(src), new_fullname)
			file_fmt = Paths.strip_extension_period(orig_ext)

			orig_relpath = Paths.get_relpath(orig_path)
			new_relpath = Paths.get_relpath(new_path)

			g_log.info(f"Renaming file: '{orig_relpath}' -> '{new_relpath}'")

			try:
				os.rename(orig_path, new_path)
			except FileNotFoundError:
				g_log.error(f"File not found: '{orig_path}'")
			except FileExistsError:
				g_log.warning("The file with such name already exists and will be removed.")
				os.remove(orig_path)
			except Exception as exc:
				g_log.error(str(exc))
				new_paths.update({file_fmt: orig_path})
			else:
				new_paths.update({file_fmt: new_path})

		return new_paths

	@staticmethod
	def merge_pdf(
			merger_path: FilePath,
			src_paths: FilePaths,
			dst_path: FilePath
		) -> None:
		"""
		Merges PDF files into a single PDF file.

		If a signle source PDF path is passed,
		then the PDF will be written to the
		specified destination path. An existing
		destination file will be overwritten.

		Params:
		-------
		merger_path:
			Path to the merger executable.

		src_paths:
			Paths to the PDF files to merge.

		dst_path:
			Path to the merged file.
		"""

		if not isfile(merger_path):
			raise FileNotFoundError(f"Merger executable not found: '{merger_path}'!")

		if len(src_paths) == 0:
			raise ValueError("Merging requires at least one PDF file!")

		if len(src_paths) == 1:
			content = File(src_paths[0]).read_bytes()
			Writer(dst_path).write_bytes(content)
			return

		for src_path in src_paths:
			if not isfile(src_path):
				raise FileNotFoundError(f"Source file not found: '{src_path}'!")
			if not src_path.endswith((".pdf", ".PDF")):
				raise ValueError("Only PDF files are supported!")

		if not exists(dirname(dst_path)):
			raise FolderNotFoundError(f"Destination folder noto found: '{dst_path}'!")

		if not dst_path.endswith((".pdf", ".PDF")):
			raise ValueError("Only PDF files are supported!")

		args = []
		args.append(merger_path) # path to the merger
		args.extend(src_paths)   # merger command line args - source PDFs
		args.append(dst_path)    # merger command line args - destination PDF

		result = subprocess.run(
			args,
			text = True,
			capture_output = True,
			stdin = subprocess.PIPE,
			check = True
		)

		if result.returncode != 0:
			raise RuntimeError(result.stderr)

class Reader:
	"""Reads file data."""

	def __init__(self, file: FilePath) -> None:
		"""
		Creates a file reader.

		Params:
		-------
		file:
			Path to the file to be read.
			Supported file formats:
			- txt
			- log
			- yml/yaml
			- json
			- xlsx
		"""
		self._file = file

	def read(self) -> Any:
		"""
		Reads the contents of a file.

		Returns:
		--------
		Content of a text file as a `str`.
		content of a log file as a `str`.
		Content of a yml/yaml file as a `dict`.
		Content of a json file as a `dict`.

		Content of an xlsx file as a `pandas.DataFrame`
		object where all columns are strings.
		"""

		fmt = Paths.get_file_format(self._file)
		reader = self._get_reader(fmt)

		return reader(self._file)

	def read_bytes(self) -> bytes:
		"""
		Reads the binary contents of a file.

		Returns:
		--------
		File binaries.
		"""
		reader = self._get_reader()
		return reader(self._file)

	def _get_reader(self, file_format: str = None) -> Callable:
		"""Identify file reader based on the file format."""

		if file_format is None:
			return self._read_bytes
		if file_format in ("txt", "log", "dat"):
			return self._read_txt_file
		if file_format in ("yaml", "yml"):
			return self._read_yaml_file
		if file_format == "xlsx":
			return self._read_xlsx_file
		if file_format == "json":
			return self._read_json_file

		raise UnsuportedFileFormatError(file_format)

	def _read_txt_file(self, file: FilePath) -> str:
		"""Reads the contents of a text file."""

		with open(file, encoding = "utf-8") as stream:
			content = stream.read()

		return content

	def _read_yaml_file(self, file: FilePath) -> dict:
		"""Reads the contents of a yml/yaml file."""

		with open(file, encoding = "utf-8") as stream:
			content = yaml.safe_load(stream)

		return content

	def _read_json_file(self, file: FilePath) -> dict:
		"""Reads the contents of a json file."""

		with open(file, encoding = "utf-8") as stream:
			content = json.load(stream)

		return content

	def _read_xlsx_file(self, file: FilePath) -> pd.DataFrame:
		"""Reads the contents of an xlsx file."""

		content = pd.read_excel(file, dtype = "string")

		return content

	def _read_bytes(self, file: FilePath) -> bytes:
		"""Reads the binary ontents of a file."""

		with open(file, "rb") as stream:
			content = stream.read()

		return content

class Writer:
	"""Writes data to file."""

	_file: FilePath = None

	def __init__(self, file: FilePath) -> None:
		"""
		Creates a file writer.

		Params:
		-------
		file:
			Path to the file to be written.
			Supported file formats:
			- txt
			- log
			- yml
			- yaml
			- json
			- xlsx
		"""

		self._file = file

	def write(self, data: Any, duplicate: str = "raise") -> None:
		"""
		Writes data to a file.

		Params:
		-------
		data:
			Data to write.

			The data writer is selected automatically based on the file format used. \n
			The structure of the data must be compatible with the file format to use \n
			for data writing.

		duplicate:
			Action to take if the destination file already exists:
			- "raise": The FileExistsError exception is raised (default behavior).
			- "copy": A copy of the file is created.
			- "overwrite": The destination file is overwritten.
			- "ignore": The original file won't be modified.
		"""

		if isfile(self._file):

			duplicate = duplicate.lower()

			if duplicate not in ("raise", "copy", "overwrite", "ignore"):
				raise ValueError(f"Unrecognized value of the 'duplicate' argument: '{duplicate}'!")

			if duplicate == "ignore":
				return

			if duplicate == "raise":
				raise FileExistsError(f"The specified file already exists: '{self._file}'")

			if duplicate == "copy":
				dst_dir = dirname(dst_path)
				dst_path = Paths.compile_file_path(self._file, dst_dir)
			elif duplicate == "overwrite":
				pass

		fmt = Paths.get_file_format(self._file) # extension
		writer = self._get_writer(fmt)
		writer(data, self._file)

	def write_bytes(self, data: bytes) -> None:
		"""Writes binary data as string to a file."""

		writer = self._get_writer()
		writer(data, self._file)

	def _get_writer(self, file_format: str = None) -> Callable:
		"""Identifies file writer based on the file format."""

		if file_format is None:
			return self._write_to_file
		if file_format == "json":
			return self._write_to_json
		if file_format in ("txt", "dat"):
			return self._write_to_txt

		raise ValueError(file_format)

	def _validate_data(self, data, expected) -> None:
		"""Validates data fomat."""

		if not isinstance(data, expected):
			raise TypeError(
				f"Expected data with the '{expected}', "
				f"but got the '{type(data)}' type!")

	def _write_to_json(self, data: dict, file) -> None:
		"""Saves a `dict` object to a json file."""

		self._validate_data(data, (dict, list))

		def time_serializer(val) -> Union[str,None]:
			"""Serialize a value of the 'datetime' type."""

			if isinstance(val, datetime):
				return str(val)

			return None

		with open(file, "w", encoding = "utf-8") as stream:
			json.dump(
				data, stream,
				indent = 4,
				sort_keys = False,
				default = time_serializer,
				ensure_ascii = False,
				allow_nan = True
			)

	def _write_to_file(self, data: bytes, file) -> None:
		"""Saves a `bytes` object to a file."""

		with open(file, "wb") as stream:
			stream.write(data)

	def _write_to_txt(self, data: Union[str, bytes], file) -> None:
		"""Saves a `str` to a plain text file."""

		self._validate_data(data, (str, bytes))

		with open(file, "w", encoding = "utf-8") as stream:
			if isinstance(data, str):
				stream.write(data)
			elif isinstance(data, bytes):
				stream.write(data.decode("utf-8"))

	def _write_to_yaml(self, data: dict, file) -> None:
		"""Saves a `dict` object to a plain text file."""

		self._validate_data(data, dict)

		with open(file, "w", encoding = "utf-8") as stream:
			yaml.dump(data, stream)

	def _write_to_xlsx(self, data: DataFrame, file: FilePath) -> None:
		"""Saves a `pandas.DataFrame` object to an xlsx file."""

		self._validate_data(data, DataFrame)
		data.to_excel(file)

class Parser:
	"""Parses file content."""

	@staticmethod
	def parse_credentials(file: File) -> dict:
		"""
		Parses the content of a .dat
		file containing credentials.

		Params:
		-------
		file: File object to parse.

		Returns:
		--------
		Credentials parameter names and their values.
		"""

		result = {}
		content = file.read()

		newine = "\r\n" if "\r\n" in content else "\n"

		for line in content.split(newine):
			key, val = line.split(":", maxsplit = 1)
			result.update({key.strip(): val.strip()})

		return result
