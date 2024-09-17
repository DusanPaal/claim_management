"""File archivation service."""

import sys
from datetime import datetime
from os.path import join
import yaml

from .... import logger
from ..base import IService
from ..storage import database as db
from ..storage import mails
from ..storage.files import Directory, File, FileManager

log = logger.get_logger()

class Archiver(IService):
	"""Archivation service of the application."""

	def _load_config(self) -> dict:
		"""Load service configuration.

		Returns:
		--------
		A dict of configuration parameters
		and and their respective values.
		"""

		log.info("Loading service configuration ...")
		cfg_path = join(sys.path[0], "app_config.yaml")

		with open(cfg_path, "r", encoding = "ascii") as fstream:
			cfg = yaml.safe_load(fstream)

		log.info("Configuration loaded.")

		return cfg

	def _connect_to_mailbox(self, cfg_mails):
		"""Connect to the mailbox."""

		log.info("Connecting to email account ...")
		account = mails.get_account(
			cfg_mails["connection"]["mailbox"],
			cfg_mails["connection"]["user_account"],
			cfg_mails["connection"]["server"]
		)
		log.info("Connection created.")

		return account

	def _connect_to_database(self, cfg_database):
		"""Connect to the database."""

		log.info("Connecting to database ...")

		db.connect(
			cfg_database["host"],
			cfg_database["port"],
			cfg_database["name"],
			cfg_database["user"],
			cfg_database["password"],
			cfg_database["debug"]
		)
		log.info("Connection created.")

		log.info("Fetching data table ...")
		table = db.get_table(
			cfg_database["table"],
			cfg_database["schema"]
		)
		log.info("Table fetched.")

		return table

	def _disconnect_from_database():
		"""Disconnect from the database."""

		log.info("Disconnecting from database ...")
		db.disconnect()
		log.info("Connection to database closed.")

	def _list_pdf_files(self, folder):
		"""Scan the folder for files to archive."""
		log.info(f"Scanning folder '{folder.name}' ...")		
		return folder.list_dir(ext = ".pdf")

	def _should_skip_file(self, doc_kind, doc_date, retention_time) -> bool:
		"""Check if the file should be skipped."""

		curr_date = datetime.now().date()

		if doc_kind == "debit":
			# skip all debit notes and the related files waiting to be processed in SAP
			log.info(
			"The document is a debit note waiting to be processed "
			"in SAP and is therefore excluded from archiving.")
			return True

		if doc_kind == "credit" and (curr_date - doc_date).days < retention_time:
			# skip credit notes that are not older than a specfied retention time
			log.info(f"File skipped. Retention time {retention_time} days not yet exceeded.")
			return True

		return False

	def _move_files(
			self, src_dir, dst_dir, retention_time,
			account, user_notes, claim_states, db_table, record) -> None:
		"""Move files to the archivation folder."""
			
		doc_date = record["created_at"].date()
		doc_kind = record["output_file"]["kind"]
		skip_file = self._should_skip_file(doc_kind, doc_date, retention_time)

		if src_dir.path == dst_dir and skip_file:
			return

		# move pdf files to archive, remove the rest of the file types, then update DB
		new_paths = FileManager.move_files(src_dir, dst_dir, record["id"], ext = ".pdf")
		FileManager.remove_files(src_dir, record["id"])
		new_status = claim_states["claim_case_unmatched"]

		db.update_record(
			db_table, int(record["id"]),
			doc_status = new_status,
			link = new_paths["pdf"]
		)

		if src_dir.path == dst_dir:
			msg = mails.get_message(account, record["message_id"])
			mails.append_text(msg, user_notes["repeated_dispute_creation_failure"])

		logger.section_break(log, end = "\n")

	def _get_retention_days(cfg_times):
		"""Calculates the credit note retention
		time from the configuration file."""

		credit_retention_time = cfg_times["credit_retention_time"]
		return max(credit_retention_time, 0) # cap to 0 if negative value is used

	def run(self) -> None:
		"""Move files from a folder to an archiving folder."""

		cfg = self._load_config()
		account = self._connect_to_mailbox(cfg["mails"])
		table = self._connect_to_database(cfg["database"])
			
		src_dirs = map(Directory, cfg["dirs"]["source"])
		upload_dir = map(Directory, cfg["dirs"]["destination"])

		retention_time = self._get_retention_days(cfg["times"])
		assert len(upload_dir) == 1, "Only one upload directory is allowed."
		user_notes = cfg["user_notes"]
		states = cfg["states"]["claim_states"]

		for src_dir in src_dirs:

			file_paths = self._list_pdf_files(
				src_dir, upload_dir, retention_time)

			n_files = len(file_paths)

			if n_files == 0:
				log.warning("The folder contains no files to archive.")
				continue

			log.info(f"Number of PDF files found: {n_files}")
			for nth, pdf in enumerate(file_paths, start = 1):

				section_tag = f" Document {nth} of {len(file_paths)} "
				logger.section_break(log, tag = section_tag)

				try:
					rec_id = File(pdf).extract_record_id()
				except ValueError:
					log.error(f"File skipped. Invalid file name format: {pdf}")
					continue
			
				record = db.get_record(table, rec_id)

				self._move_files(
					pdf, src_dir, upload_dir, retention_time, 
					account, user_notes, states, table, record
				)
			
			log.info("Folder archivation completed.\n")

		self._disconnect_from_database()
