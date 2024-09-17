# pylint: disable = W0718, W1203

"""Dispatcher service."""

from os.path import join
import sys
import yaml
from .... import logger
from ..base import IService
from ..storage import database as db
from ..storage import mails

log = logger.get_logger()

class Dispatcher(IService):
	"""Move emails form a temporary
	email foldor located under a customer folder, to a destination
	subfolder based on its status. The service chesks database for
	the claim status values:
		- claim_creation_completed
		- claim_creation_failed
		- claim_creation_duplicate
		- claim_case_unmatched

	Then, the messages are collected form mailbox based on mesage_id
	and distributed to:
		- an email folder where messages that failed to create claim are collected.
		and are supposed to be processed manually by users
		- an email folder where messages where claims where create are collected.
		and no furhter  action is expected to be taken form users.

	Once message is moved, the database record status is updated accordingly.
	"""

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

	def _connect_to_mailbox(self, cfg_mails) -> None:
		"""Connect to the mailbox."""

		log.info("Connecting to email account ...")
		account = mails.get_account(
			cfg_mails["connection"]["mailbox"],
			cfg_mails["connection"]["user_account"],
			cfg_mails["connection"]["server"]
		)
		log.info("Connection created.")

		return account

	def _connect_to_database(self, cfg_database) -> None:
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

	def _get_dispatching_rules(self, cfg_subfolders: dict, cfg_processing: dict) -> dict:
		"""Compile routing rules that specify destination elmail folders
		and new states of the moved mails.

		Params:
		-------
		cfg_subfolders: Configuration params: app_config -> mails -> subfolders
		cfg_processing: Configuration params: app_config -> processing

		Returns:
		--------
		A 'dict' of claim states (keys) used as criteria for retrieving
		records from the database, and their dispatch rules (values):
			- 'dst_subfolder': Name of the customer subfolder no move the message.
			- 'new_state': New status value to store to database.

			Example:
			--------
			rules = {
				'completed': {
					'dst_subfolder': 'Done',
					'new_status': 'done'
				},

				'processing_error': {
					'dst_subfolder': 'Manual',
					'new_status': 'manual'
				},
			}
		"""

		mail_states = cfg_processing["mail_states"]
		claim_states = cfg_processing["claim_states"]
		doc_states = cfg_processing["document_states"]

		params = {

			doc_states["document_extraction_failed"]: {
				"dst_subfolder": cfg_subfolders["claim_creation_failed"],
				"new_status": mail_states["mail_extractionerror_moved"]
			},

			claim_states["claim_creation_completed"]: {
				"dst_subfolder": cfg_subfolders["claim_creation_completed"],
				"new_status": mail_states["mail_completed_moved"]
			},

			claim_states["claim_creation_failed"]: {
				"dst_subfolder": cfg_subfolders["claim_creation_failed"],
				"new_status": mail_states["mail_failed_moved"]
			},

			claim_states["claim_creation_duplicate"]: {
				"dst_subfolder": cfg_subfolders["claim_creation_completed"],
				"new_status": mail_states["mail_duplicate_moved"]
			},

			# credit notes that run out of retention time for
			# which the app tries to match them with a DMS case
			claim_states["claim_case_unmatched"]: {
				"dst_subfolder": cfg_subfolders["claim_update_failed"],
				"new_status": mail_states["mail_case_unmatched_moved"]
			}

		}

		return params

	def _disconnect_from_database() -> None:
		"""Disconnect from the database."""

		log.info("Disconnecting from database ...")
		db.disconnect()
		log.info("Connection to database closed.")

	def _dispatch(self, msg, src_mail_folder, dst_mail_folder) -> None:
		"""Move the email to the destination folder."""

		try:
			old_location = mails.get_message_location(msg)[1]
			new_location = mails.move_message(msg, src_mail_folder, dst_mail_folder)
		except mails.IdenticalFolderWarning as wng:
			log.warning(str(wng))
			return
		except Exception as exc:
			log.exception(exc)
			return

		log.info(f"Email moved: '{old_location}' -> '{new_location}'")

		log.info("Writing info message to the user email ...")
		mails.append_text(msg, f"G_ROBOT.RFC (INFO): Message moved to: {new_location}.")
		log.info("Message successfully written.")

	def _update_pdf_status(self, table, record_id, new_status) -> None:
		"""Update the status of the PDF file in the database."""
		log.info("Updating database record ...")
		db.update_record(table, record_id, doc_status = new_status)
		log.info(f"Parameter 'doc_status' updated to: '{new_status}'")

	def run(self) -> None:
		"""Dispatch processed emails.

		Processed messages are moved from a temporary mail folder
		to the target customer subfolders based on the result of
		the claim processing in SAP.
		"""

		cfg = self._load_config()
		table = self._connect_to_database(cfg["database"])
		account = self._connect_to_mailbox(cfg["mails"])

		disp_rules = self._get_dispatching_rules(
			cfg["mails"]["subfolders"], cfg["processing"])

		records = db.get_records(table, "doc_status", value = disp_rules.keys())
		n_total = len(records)

		if n_total == 0:
			log.warning("No documents to dispatch found!\n")
			return

		for nth, rec in enumerate(records, start = 1):

			logger.section_break(log, tag = f" Item {nth} of {n_total} ", n_chars = 12)
			log.info("Item record ID: %d", rec["id"])

			log.info("Identifying item status ...")
			if rec["doc_status"] not in disp_rules:
				log.error(
					"Unrecognized dispatch status '%s'! "
					"The item won't be moved.", rec["doc_status"])
				continue

			dst_subfolder = disp_rules[rec["doc_status"]]["dst_subfolder"]
			new_status = disp_rules[rec["doc_status"]]["new_status"]
			log.info("Item status value: '%s'", rec["doc_status"])

			msgs = mails.get_messages2(account, rec["message_id"])

			if len(msgs) == 0:
				# the message is either deleted or mesage_id has changed
				log.error("Could not find any message with the given message ID!")
				self._update_pdf_status(table, rec["id"], new_status)
				continue

			for nth, msg in enumerate(msgs, start = 1):
				logger.section_break(
					log, tag = f" Email {nth} of {len(msgs)} "
					n_chars = 12, char = "*", sides = "both"
				)
				self._dispatch(msg, rec['subfolder'], dst_subfolder)
				logger.section_break(log, char = "*", n_chars = 25, sides = "both")

			self._update_pdf_status(table, rec["id"], new_status)
			log.info("Item successfully processed.")
			logger.section_break(log, n_chars = 20, end = "\n")

		logger.section_break(log)

		self._disconnect_from_database()