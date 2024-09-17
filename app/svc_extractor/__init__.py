# pylint: disable = W0718, W1203

"""Extractor service."""

import os
from os.path import join, split
from typing import Union
from . import parsers
from .... import logger
from ....base import Service
from ....resources import mails
from ....resources import database as db
from ....resources.files import (
	APP_ROOT, Directory, File, FileManager,
	FileNameFormatError, Reader, Writer)
from .categorizers import Categorizer, CategoryNotFoundError
from .converter import Converter, ServerError

g_log = logger.get_global_logger()


class DocumentsNotFoundWarning(Warning):
	"""Document input directory is empty."""

class InvalidCategoryAppliedError(Exception):
	"""
	The message category applied by user
	is not applicable for the document.
	"""

class Extractor(Service):
	"""Data extraction service for the "Claims"
	component of the application."""

	_cfg: dict = None
	_table: db.Table = None
	_template_map: dict = None
	_converters: dict = {}
	_database = None
	_account = None

	def __init__(self, cfg: dict) -> None:
		"""Initialize the data extraction service."""

		g_log.info("=== Initializing service ===")
		self._cfg = cfg.copy()
		self._check_input_directory()

		g_log.info("Connecting to database ...")
		db.connect(
			self._cfg["database"]["host"],
			self._cfg["database"]["port"],
			self._cfg["database"]["name"],
			self._cfg["database"]["user"],
			self._cfg["database"]["password"],
			self._cfg["database"]["debug"]
		)
		g_log.info("Connection created.")

		g_log.info("Fetching data table ...")
		self._table = db.get_table(
			self._cfg["database"]["table"],
			self._cfg["database"]["schema"]
		)
		g_log.info("Table fetched.")

		g_log.info("Connecting to email account ...")
		self._account = mails.get_account(
			self._cfg["mails"]["connection"]["mailbox"],
			self._cfg["mails"]["connection"]["user_account"],
			self._cfg["mails"]["connection"]["server"]
		)
		g_log.info("Connection created.")

		g_log.info("Loading document templates ...")
		self._template_map = self._load_templates()
		g_log.info("Templates loaded.")

		g_log.info("Initializing converters ...")
		self._converters = self._initialize_converters(self._cfg["converter"])
		g_log.info("Converters successfully initialized.")

		g_log.info("=== Service initialized ===\n")

	def __del__(self) -> None:
		"""Release resources allocated by the service."""

		g_log.info("=== Ending service ===")
		g_log.info("Disconnecting from database ...")
		db.disconnect()
		g_log.info("Connection to database closed.")
		g_log.info("=== Service ended ===\n")

	def _load_templates(self) -> dict:
		"""Load document data extraction templates."""

		templ_map = {}
		used_tpl_codes = []
		templates_dir = join(
			APP_ROOT, "engine", "claim",
			"Services", "extractor", "templates")

		for subf in os.listdir(templates_dir):

			templates = []
			subf_dir = Directory(join(templates_dir, subf))

			for tpl_path in subf_dir.list_dir(ext = ".yml"):

				g_log.debug(f"Loading template: '{File(tpl_path).fullname}' ...")

				try:
					template = parsers.create_template(tpl_path)
				except Exception as exc:
					g_log.error(str(exc))
					continue

				template_id = template["template_id"]

				if template_id in used_tpl_codes:
					raise RuntimeError(f"The tempate code '{template_id}' already used!")

				used_tpl_codes.append(template_id)
				templates.append(template)

			templ_map.update({subf: templates})

		return templ_map

	def _initialize_converters(self, conv_cfg: dict) -> dict:
		"""Initialize PDF converters."""

		convs = {}

		for key, val in conv_cfg["routes"].items():
			convs.update({key: Converter(
				url = conv_cfg["url"],
				route = val,
				access_token = conv_cfg["secret"],
				n_attempts = conv_cfg["attempts"],
				timeout = conv_cfg["timeout"],
				debugging = conv_cfg["debugging"]
			)})

		return convs

	def _check_input_directory(self) -> None:
		"""Check if the input directory contains documents."""

		g_log.info("Checking the input directory for existing documents ...")
		if Directory(self._cfg["dirs"]["input"]).is_empty():
			raise DocumentsNotFoundWarning("No documents to process found.")
		g_log.info("Checking OK, the directory is not empty.")

	def _get_pdf_list(self) -> list:
		"""List PDF files located in a directory."""

		g_log.info("Creating list of pdf documents ...")
		pdf_dir = self._cfg["dirs"]["input"]
		pdf_paths = Directory(pdf_dir).list_dir(ext = ".pdf")
		g_log.info(f"Found {len(pdf_paths)} documents to process.")

		return pdf_paths

	def _extract_data(self, txt_path: str, extracted_str: str, templates: list) -> dict:
		"""Extract relevant data from the text of a document."""

		g_log.info("Matching data with templates ...")
		for tmpl in templates:

			optimized_str = tmpl.prepare_input(extracted_str)

			if not tmpl.matches_keywords(optimized_str):
				continue

			g_log.info("Matched template with ID: '%s'", tmpl["template_id"])

			g_log.info("Writing optimized document strings to text file ...")
			Writer(txt_path).write(optimized_str, duplicate="overwrite")
			g_log.info("Strings successfully written.")

			g_log.info("Extracting data ...")
			data = tmpl.extract(optimized_str)
			g_log.info("Data extraction completed.")

			return data

		g_log.info("Writing extracted document strings to text file ...")
		Writer(txt_path).write(extracted_str, duplicate="overwrite")
		g_log.info("Strings successfully written.")
		raise parsers.TemplateNotFoundError("No template matched the document text!")

	def _identify_category(self, msg_categ: str, data: dict) -> Union[str, None]:
		"""Identify the document category and return it's name if applicable."""

		g_log.info("Identifying document category ...")

		if data["kind"] not in ("debit", "credit"):
			raise ValueError(f"Unrecognized document kind: '{data['kind']}'!")

		if data["kind"] == "credit":
			g_log.warning(
				"Document categorization does not apply to credit notes in the "
				f"current process. The message category {logger.quotify(msg_categ)} "
				"will therefore not be included in the extracted data.")
			return None

		data_categ = data["category"]

		if msg_categ == "REBUILD_WITHOUT_RETURN":
			msg_categ = "rebuild"
		elif msg_categ == "PENALTY":
			msg_categ = "penalty_general"

		if not isinstance(data_categ, (str, list)):
			raise TypeError(f"Unrecognized category type: '{type(data_categ)}'!")

		if msg_categ is None:
			if isinstance(data_categ, list):
				new_categ = Categorizer().categorize(data)
			elif isinstance(data_categ, str):
				new_categ = data_categ
		else:
			msg_categ = msg_categ.lower()
			if isinstance(data_categ, list):
				data_categs = data_categ
			elif isinstance(data_categ, str):
				data_categs = [data_categ]

			if msg_categ not in data_categs:
				raise InvalidCategoryAppliedError(
					"The message category applied by the user "
					"isn't applicable for the document!")

			new_categ = msg_categ

			g_log.info(
				f"The existing document category: {data_categ} "
				f"will be overridden to '{new_categ}'.")

		g_log.info(f"Document category: {logger.quotify(new_categ)}")

		return new_categ

	def provide(self) -> None:
		"""
		Manages the conversion of PDF documents into
		text files and then extracts data from the
		the converted text into JSON files.
		"""

		g_log.info("Processing documents ...")

		conv_cfg = self._cfg["converter"]
		cust_cfg = self._cfg["customers"]
		dirs_cfg = self._cfg["dirs"]

		pdf_paths = self._get_pdf_list()
		file_types = ["pdf", "log", "txt", "json"]

		for nth, pdf_path in enumerate(pdf_paths, start = 1):

			logger.section_break(
				tag = f" Document {nth}/{len(pdf_paths)} ",
				log = g_log, n_chars = 13)

			pdf_dirpath, pdf_name = split(pdf_path)
			pdf_dir = Directory(pdf_dirpath)
			g_log.info(f"File name: '{pdf_name}'")

			log_path = pdf_path.replace(".pdf", ".log")
			txt_path = pdf_path.replace(".pdf", ".txt")
			json_path = pdf_path.replace(".pdf", ".json")

			try:
				rec_id = File(pdf_path).extract_record_id()
				g_log.info(f"Database record ID of the document: {rec_id}")
				rec = db.get_record(self._table, int(rec_id))
			except (FileNameFormatError, db.RecordNotFoundError) as exc:
				g_log.error(str(exc))
				# leave the problematic file in the input folder for
				# further investigation and continue with next document
				continue

			customer = rec["subfolder"]
			msg_categ = rec["message_category"]

			if customer not in cust_cfg:
				g_log.error(f"No configuration exists for customer '{customer}'!")
				continue

			g_log.info(f"Customer: '{customer}'")
			g_log.info(f"Message category: {logger.quotify(msg_categ)}")
			pdf_type = cust_cfg[customer]["pdf_type"]
			extractor = cust_cfg[customer]["extractor"]

			if extractor.upper() == "AI":
				g_log.warning(
					"File skipped. Data extraction will be performed by the "
					"MS Forms Recognizer instead of the templating engine.")
				continue

			if not (conv_cfg["force"] or rec["extracted_text"] is None):
				extracted_str = rec["extracted_text"]
			else:
				try:
					g_log.info("Converting pdf to text ...")
					extracted_str = self._converters[pdf_type].convert(
						pdf_path, clean = True, header = True)
					g_log.info("Conversion completed.")
				except ServerError as err:
					if conv_cfg["ignore_server_errors"]:
						g_log.error(err)
						g_log.warning("The OCR server error is ignored.")
						continue

					raise # let the error propagate up the call stack

			if customer not in self._template_map:
				g_log.error(f"No templates exist for customer '{customer}'!")
				continue

			data = None
			templates = self._template_map[customer]
			doc_log = logger.get_logger("document", log_path)

			try:

				data = self._extract_data(txt_path, extracted_str, templates)
				data["category"] = self._identify_category(msg_categ, data)

				g_log.info("Writing data to JSON ...")
				Writer(json_path).write(data, duplicate = "overwrite")
				g_log.info("Data successfully written.")
				logger.close_filehandler(doc_log)

				FileManager.rename_files(
					pdf_dir, data["name"].lower(), rec_id,
					id_tag = True, ext = file_types)

			except parsers.TemplateNotFoundError as exc:
				g_log.error(exc)
				doc_log.error(exc)
				status = "extraction_error"
				dst_folder = dirs_cfg["template_err"]
				user_msg = "G.ROBOT_RFC (ERROR): Could not extract document data!"
			except parsers.PatternMatchError as exc:
				g_log.exception(exc)
				status = "extraction_error"
				dst_folder = dirs_cfg["template_err"]
				user_msg = "G.ROBOT_RFC (ERROR): Could not extract document data!"
			except NotImplementedError as exc:
				g_log.exception(exc)
				status = "extraction_error"
				dst_folder = dirs_cfg["template_err"]
				user_msg = (
					"G.ROBOT_RFC (ERROR): Could not categorize the document!\n"
					"Apply the category manually, and move the message again to the "
					f"customer folder: '{customer}'.")
			except InvalidCategoryAppliedError as exc:
				g_log.error(exc)
				status = "extraction_error"
				dst_folder = dirs_cfg["template_err"]
				user_msg = (
					"G.ROBOT_RFC (ERROR): The message category you've "
					"applied is not applicable for the document!")
			except CategoryNotFoundError as exc:
				g_log.error(exc)
				status = "extraction_error"
				dst_folder = dirs_cfg["template_err"]
				user_msg = (
					"G.ROBOT_RFC (ERROR): Could not categorize the document!\n"
					"Apply the category manually, and move the message again to the "
					f"customer folder: '{customer}'.")
			except Exception as exc:
				g_log.exception(exc)
				status = "extraction_error"
				dst_folder = dirs_cfg["template_err"]
				user_msg = "G.ROBOT_RFC (ERROR): Could not extract document data!"
			else:
				status = "extracted"
				dst_folder = dirs_cfg["upload"]
				user_msg = "G.ROBOT_RFC (INFO): Document data extraction OK."
			finally:
				logger.close_filehandler(doc_log)

			new_paths = FileManager.move_files(
				pdf_dir, dst_folder,rec_id, file_types)

			g_log.info("Updating database record ...")
			db.update_record(
				self._table, int(rec_id),
				doc_status = status,
				link = new_paths["pdf"],
				extracted_text = extracted_str,
				output_file = data,
				log_file = Reader(new_paths["log"]).read()
			)
			g_log.info("Database record successfully updated.")

			g_log.info("Writing message to user email ...")
			msg = mails.get_message(self._account, rec["message_id"])

			if msg is None:
				g_log.error("Message not found! The text cannot be written.")
			else:
				mails.append_text(msg, user_msg)
				g_log.info("Message successfully written.")

			logger.section_break(g_log, n_chars = 21, end = "\n")

		g_log.info("=== Processing OK ===\n")
