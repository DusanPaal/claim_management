# pylint: disable = R0913, W0718

"""Manager for application logging system."""

import json
import logging
import logging.config
import os
import re
import shutil
import sys
from datetime import datetime, timedelta
from glob import glob
from logging import Logger
from os.path import basename, isfile, join
from typing import Any, Union
import yaml

FilePath = str

g_log = logging.getLogger("global")

# archive logs from prev days
log_patts = [
	"*extractor",
	"*downloader",
	"*archiver",
	"*dispatcher",
	"*claims"
]

def get_logger() -> Logger:
	"Return the global logger of the engine."
	return g_log


def _get_filehandler_index(logger: Logger) -> Union[int,None]:
	"""Identifies the file handler index of in logger handlers."""

	for i, handler in enumerate(logger.handlers):
		if isinstance(handler, logging.FileHandler):
			return i

	return None

def initialize(file: FilePath, cfg: FilePath) -> None:
	"""Intializes application logging system.

	Parameters:
	-----------
	file:
		Path to the log file.

	cfg:
		Path to the logging configuration file.
	"""

	with open(cfg, encoding = "utf-8") as stream:
		content = yaml.safe_load(stream)

	logging.config.dictConfig(content)
	change_filehandler(g_log, file)

def section_break(
		log: Logger, n_chars: int = 20, tag:
		str = "", char: str = "-", end = "",
		sides: str = "both") -> None:
	"""Prints a section break line into a log.

	Parameters:
	-----------
	log:
		Logger used to print the section break.

	n_chars:
		Number of characters used for the indentation from both sides (default: 20).

	tag:
		A text to insert before the counter of the section line (default: "").

	char:
		The character used to create the indentation sequence (default: "-").

	end:
		Ending character of the line (default: "").

	sides:
		Sides to indent:
		- "both": Both sides are indented (default behavior).
		- "left": The left side only is indented.
		- "right": The right side only is indented.
	"""

	indentation = char * n_chars

	if sides.lower() == "both":
		log.info("".join([indentation, tag, indentation, end]))
	elif sides.lower() == "left":
		log.info("".join([indentation, tag, end]))
	elif sides.lower() == "right":
		log.info("".join([tag, indentation, end]))
	else:
		raise ValueError(f"Unrecognozed value for argument 'sides': '{sides}'")

def print_data(
		data: Any, desc: str = "", row_list: bool = False,
		top_brackets = True, compact: bool = False) -> None:
	"""Prints an arbitrary Python data structure.

	Parameters:
	-----------
	data:
		Data to print.

	desc:
		Descriptior of the printed data.

	row_list:
		If True, the values in a list are printed in one line.

	top_brackets: 
		If True, the data wrapping brackets are printed.

	compact:
		If True, the data is compacted befre printing (doplnit ako ...)
		Any exception eccured while compacting the data ignored and the original data is printed.
	"""

	data_cpy = {}

	if compact:
		try:
			for rec in data:
				data_cpy.update({rec["ATTR_ID"]:rec["ATTR_VALUE"]})
		except Exception:
			pass # ignore errors and print the orig data
	else:
		data_cpy = data

	text = json.dumps(data_cpy, indent = 4)

	if row_list:

		lists = re.findall(r"\[(.*)\]", text, re.DOTALL)

		for lst in lists:
			tokens = lst.split(",")
			tokens = [tok.strip() for tok in tokens]
			fmt = ", ".join(tokens)
			text = text.replace(f"[{lst}]", f"[{fmt}]")

	if not top_brackets:
		text = re.sub(r"\A{\n", "", text)
		text = re.sub(r"\n}\Z", "", text)

	text = "\n".join([desc, text])

	g_log.debug(text)

def get_logger(name: str, log: FilePath = None) -> Logger:
	"""Returns a logging object.

	Parameters:
	-----------
	name:
		Name of the logger.

	log:
		Path to the log file (default: None).
		
		If a valid path is provided, then the logger's
		file handler will be updated with that path.
	"""

	logger = logging.getLogger(name)

	if log is not None:
		change_filehandler(logger, log)

	return logger

def get_global_logger() -> Logger:
	"""Fetches the global logger.
	
	Returns:
	--------
	The instance of the global Logger-like object.
	"""
	return get_logger("global")

def change_filehandler(logger: Logger, log: FilePath) -> None:
	"""Changes the file handler of a logger.

	Any existing log files specified by the log path are removed.

	Parameters:
	-----------
	log_path:
		Path to the new log file.

	logger:
		The instance of the Logger-like object.
	"""

	if isfile(log):
		os.remove(log)

	idx = _get_filehandler_index(logger)

	if idx is None:
		return

	prev_handler = logger.handlers.pop(idx)
	new_handler = logging.FileHandler(log, encoding = prev_handler.encoding)
	new_handler.setFormatter(prev_handler.formatter)
	logger.addHandler(new_handler)

def close_filehandler(logger: Logger) -> None:
	"""Closes the file handler of a logger.

	Parameters:
	-----------
	logger: 
		The logger object.
	"""

	for i, handler in enumerate(logger.handlers):
		if isinstance(handler, logging.FileHandler):
			logger.handlers[i].close()
			logger.removeHandler(i)

def get_current_date() -> str:
	"""Returns the current date."""
	return datetime.now().strftime("%Y-%m-%d")

def cleanup(n_weeks: int) -> None:
	"""Removes obsolete logs from the
	archive as soon as an archiving
	period has expired.

	Parameters:
	-----------
	n_weeks:
		The archiving period in weeks.
	"""

	log_files = glob(join(sys.path[0], "logs", "archive", "*.log"))
	curr_date = datetime.now().date()

	for src_log in log_files:

		log_name = basename(src_log)
		date_token = log_name.split("_")[0]
		log_date = datetime.strptime(date_token, "%Y-%m-%d").date()
		thresh_date = curr_date - timedelta(weeks = n_weeks)

		if log_date < thresh_date:
			try:
				g_log.info(f"Removing obsolete log file: {src_log} ...")
				os.remove(src_log)
			except PermissionError as exc:
				g_log.error(str(exc))

def archive(patt: str = "*") -> None:
	"""Archive logs from previous days.

	By default, logs from all components are archived.

	Parameters:
	-----------
	patt:
		Pattern to match in a log name (default: "*").

		The pattern may contain simple shell-style wildcards a la
		fnmatch. However, unlike fnmatch, filenames starting with a
		dot are special cases that are not matched by "*" and "?"
		patterns.
	"""

	log_files = []
	logs_dir = join(sys.path[0], "logs")

	for subdir in os.listdir(logs_dir):
		if subdir == "archive":
			continue
		log_files += glob(join(logs_dir, subdir, f"{patt}.log"))

	curr_date = datetime.now().date()

	for src_log in log_files:

		log_name = basename(src_log)
		date_token = log_name.split("_")[0]
		log_date = datetime.strptime(date_token, "%Y-%m-%d").date()

		if log_date == curr_date:
			continue

		dst_log = join(sys.path[0], "logs", "archive", log_name)

		try:
			if isfile(dst_log):
				os.remove(dst_log)
			shutil.move(src_log, dst_log)
		except PermissionError as exc:
			g_log.error(str(exc))

def get_log_path(order_str: str, subdir: str, task: str = "") -> FilePath:
	"""Compiles path to a log file.

	Parameters:
	-----------
	order_str: 
		String ID of the ordered task in Task Manager.

	subdir:
		Name of the subdirectory in the root "logs" directory.

	task:
		Name of the task to be logged.

		By default, no task name is used in the log file name.

	Returns:
	--------
	The compiled log gile path.
	"""

	log_dir = join(sys.path[0], "logs", subdir)
	log_date = get_current_date()

	if task != "":
		task = f"_{task}"

	nth = 1

	while True:

		nth_file = str(nth).zfill(3)
		log_name = f"{log_date}_{order_str}_{nth_file}{task}.log"
		log_path = join(log_dir, log_name)

		if not isfile(log_path):
			break

		nth += 1

	return log_path

def quotify(val: Union[Any,list]) -> Union[Any,list]:
	"""Places quotation marks around the passed value(s).

	Parameters:
	-----------
	val: 
		Value or a list of values to quotify.

		If `None` is passed, then the original value is returned.

	Returns:
	--------
	The quotified value or list of values.	
	"""

	if val is None:
		return val

	if not isinstance(val, list):
		return f"'{val}'"

	return [f"'{v}'" for v in val]
