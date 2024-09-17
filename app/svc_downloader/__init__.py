# pylint: disable = W0718, W1203

"""Downloader service."""

from os.path import join
from typing import Union
from .... import logger
from ....base import Service
from ....resources import database as db
from ....resources import mails
from ....resources.azure import storage
from ....resources.mails import Message
from ....resources.files import File, Paths, FileManager, Directory, APP_ROOT

g_log = logger.get_global_logger()

class Downloader(Service):
	"""Save documents received from customers."""

	_database = None
	_account = None
	_container = None
	_table = None
	_cfg = None
	_temp_dir = None
	_merger_path = None

	def __init__(self, cfg: dict) -> None:
		"""Initialize the downloading service."""

		g_log.info("=== Initializing service ===")

		self._temp_dir = Directory(join(APP_ROOT, "temp"))

		self._merger_path = join(
			APP_ROOT, "engine","resources",
			"pdf", "pdfunite.exe")

		self._cfg = cfg.copy()

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

		g_log.info("Connecting to Azure Blob Storage ...")
		client = storage.get_service_client(
			acc_name = self._cfg["blob"]["account_name"],
			acc_key = self._cfg["blob"]["account_key"],
			endpoint_protocol = self._cfg["blob"]["endpoints_default_protocol"],
			endpoint_suffix = self._cfg["blob"]["endpoint_suffix"]
		)

		container_name = self._cfg["blob"]["container_name"]
		self._container = storage.get_container_client(client, container_name)
		g_log.info("Connection created.")

		g_log.info("=== Service initialized ===\n")

	def __del__(self) -> None:
		"""Release resources allocated by the service."""

		g_log.info("=== Ending service ===")
		g_log.info("Disconnecting from database ...")
		db.disconnect()
		g_log.info("Connection to database closed.")
		g_log.info("=== Service ended ===\n")

	def _save_message_data(
			self, msg: Message, pdf_dir: str,
			pdf_count: Union[None, str],
			attach_merged: bool, merged_attname: str,
			file_type: str = ".pdf") -> File:
		"""Save message attachment/body to a PDF file."""

		if not pdf_count in ("zero_or_one", "one", "one_or_two"):
			raise ValueError(f"Unecognized pdf count: '{pdf_count}'")

		default_filename = "document.pdf"

		if pdf_count == "zero_or_one":
			if not mails.contains_attachment(msg, ext = file_type):
				g_log.info("Saving message body to pdf ...")
				pdf_path = join(pdf_dir, default_filename)
				mails.convert_message(msg, pdf_path)
			else:
				g_log.info(f"Saving '{file_type}' attachment ...")
				pdf_path = mails.download_attachment(
				msg, dst_folder = pdf_dir,
				ext = file_type, overwrite = True)
		else:
			g_log.info(f"Saving '{file_type}' attachment ...")
			if pdf_count == "one":
				pdf_path = mails.download_attachment(
					msg, dst_folder = pdf_dir,
					ext = file_type, overwrite = True)
			elif pdf_count == "one_or_two":

				pdf_docs = mails.download_attachments(
					msg, self._temp_dir.path, ext = file_type)

				# sort the docs alhabetically so that they
				# appear in correct order in teh merged file
				pdf_docs.sort()
				pdf_path = join(pdf_dir, default_filename)

				g_log.info("Merging the saved attachents ...")
				FileManager.merge_pdf(self._merger_path, pdf_docs, pdf_path)

				if attach_merged:

					if merged_attname == "default":
						att_name = default_filename
					elif merged_attname == "base":
						att_name = Paths.get_basename(pdf_docs)
					else:
						raise ValueError(
							"Unrecognized value used in the 'attachment_name' parameter: "
							f"'{att_name}' contained in the 'app_config.yaml' file!")

					g_log.info("Attaching the merged PDF ...")
					mails.remove_attachments(msg, ext = ".pdf")
					mails.attach_file(msg, pdf_path, att_name)
					g_log.info("PDF successfully attached.")

				g_log.info("Removing the saved attachents ...")
				self._temp_dir.clear()

			else:
				raise RuntimeError(
					"The message contains no attachments "
					"but at least one PDF is expected!")

		g_log.info("PDF file created successfully.")

		return File(pdf_path)

	def _get_message_category(self, msg, msg_categs, ctrl_categs) -> tuple:
		"""
		Return a specific message category name by comparing all
		message categories against the expected category names.
		"""

		categs = [] if msg.categories is None else list(msg.categories)
		valid_categs = msg_categs + ctrl_categs
		# get only valid categories
		categs = list(set(categs).intersection(valid_categs))

		if len(categs) == 0:
			categ = None
			control = None
		elif len(categs) == 1:
			if categs[0] in ctrl_categs:
				categ = None
				control = categs[0]
			else:
				categ = categs[0]
				control = None
		elif len(categs) == 2:
			# one category for document categorization
			# and one for the processing control
			if categs[0] in ctrl_categs and categs[1] in msg_categs:
				categ = categs[1]
				control = categs[0]
			elif categs[1] in ctrl_categs and categs[0] in msg_categs:
				categ = categs[0]
				control = categs[1]
			else:
				raise RuntimeError(f"Invalid message category combination: {categs}!")
		else:
			raise RuntimeError(f"Invalid message category combination: {categs}!")

		if categ is None:
			g_log.info("The message does not have a user-assigned category.")
		else:
			g_log.info(f"Message category detected: '{categ}'")

		if control is not None:
			g_log.info(f"Control category detected: '{control}'")

		return (categ, control)

	def _download_emails_data(
			self, emails: tuple, msg_categs: list,
			ctrl_categs: list, dst_dir: str, cust_folder: str,
			cust_subfolders: dict, doc_states: dict, table: db.Table
		) -> None:
		"""Save email PDF attachments or entire bodies as PDF files."""

		n_saved = 0  # use a separate counter as enumerate is computationally expensive
		temp_folder = cust_subfolders["claim_creation_ready"]
		failed_folder = cust_subfolders["claim_creation_failed"]
		done_folder = cust_subfolders["claim_creation_completed"]
		pdf_count = self._cfg["customers"][cust_folder]["pdf_count"]
		attach_merged = self._cfg["customers"][cust_folder]["attach_merged"]
		merged_attname = self._cfg["customers"][cust_folder]["attachment_name"]

		for msg in emails:

			n_saved += 1

			logger.section_break(g_log, tag = f" Message {n_saved} of {len(emails)} ")

			try:
				pdf_file = self._save_message_data(
					msg, dst_dir, pdf_count,
					attach_merged, merged_attname)
			except mails.InvalidAttachmentsError as exc:
				g_log.error(str(exc))
				g_log.info(f"Moving message to: 'Inbox/{cust_folder}/{failed_folder}' ...")
				mails.move_message(msg, cust_folder, failed_folder)
				g_log.info("Writing error message to user email ...")
				mails.append_text(msg, "G.ROBOT_RFC (ERROR): Invalid message attachment!")
				g_log.info("Message successfully written.")
				continue
			except Exception as exc:
				g_log.error(exc)
				g_log.info("Writing error message to user email ...")
				mails.append_text(msg, f"G.ROBOT_RFC (ERROR): {str(exc)}")
				g_log.info("Message successfully written.")
				continue

			try:
				categ, control = self._get_message_category(msg, msg_categs, ctrl_categs)
			except (ValueError, RuntimeError) as exc:
				g_log.error(str(exc))
				pdf_file.remove()
				mails.move_message(msg, cust_folder, failed_folder)
				g_log.info("Writing error message to user email ...")
				mails.append_text(msg, f"G.ROBOT_RFC (ERROR): {str(exc)}")
				g_log.info("Message successfully written.")
				continue

			g_log.info("Searching email for PDF hash ...")
			file_hash = mails.find_hash_value(msg, key_patt = r"hash = (\S+)")

			if file_hash is not None:
				g_log.info("Hash value found.")
			else:
				g_log.info("Hash value not found.")
				g_log.info("Calculating document hash ...")
				file_hash = pdf_file.calculate_hash()
				g_log.info("Writing the hash value to user mail ...")
				mails.append_text(msg, f"G.ROBOT_RFC (INFO): hash = {file_hash}")

			g_log.info("Checking document history ...")
			recs = db.get_records(table, col = "doc_hash", value = file_hash)

			if len(recs) > 1:
				pdf_file.remove()
				g_log.error(
					f"Duplicate records with the same file " 
					f"hash as the downloaded PDF detected: '{file_hash}'")
				g_log.warning("The message will not be further processed.")
				g_log.info("Writing message text to user email ...")
				mails.append_text(
						msg, "G.ROBOT_RFC (ERROR): More than one copy of the file "
					  	"found in database!\nContact the LBS automation team for support.")
				g_log.warning("The downloaded file will be removed.")
				pdf_file.remove()
				continue

			if len(recs) == 0:
				g_log.info("No previous DB record detected.")
				g_log.info("Creating a database record ...")
				rec_id = db.create_record(
					table,
					message_id = msg.message_id,
					subfolder = cust_folder,
					message_category = categ,
					control_category = control,
					doc_status = doc_states["document_registration_success"],
					doc_hash = file_hash
				)
				g_log.info(f"Record with ID: {rec_id} successfully created.")
			elif len(recs) == 1:

				rec_id = recs[0]["id"]
				prev_status = recs[0]["doc_status"]
				prev_msg_id = recs[0]["message_id"]

				g_log.warning(
					"The file is already recorded in the database under "
					f"the ID: {rec_id} with document status: '{prev_status}'. "
					"No new record will be created.")

				# If the user moves the message to another folder in the meantime,
				# ensure the 'subfolder' parameter of  the record is updated, as well.
				db.update_record(table, rec_id, subfolder = cust_folder)

				if control == "IGNORE_ALREADY_EXISTING":
					g_log.warning(
						"The message will be downloaded and "
						"processed regardless of its status.")
					g_log.debug(f"Updating the 'control_category' value in DB to: '{control}'")
					db.update_record(table, rec_id, control_category = control)
				elif prev_status in ("completed", "done", "duplicate"):
					location = mails.move_message(msg, cust_folder, done_folder)
					g_log.info(f"Message moved to: '{location}'")
					pdf_file.remove()
					g_log.info("The saved file has been removed.")
					continue

				prev_categ = db.get_value(table, rec_id, "message_category")
				new_status = doc_states["document_registration_success"]

				if prev_categ != categ:
					g_log.warning(
						f"The previously used message category '{prev_categ}' "
						f"will be overwritten with the newer value: {logger.quotify(categ)}")

					g_log.debug(
						"Updating the 'message_category' value "
						f"in DB to: {logger.quotify(categ)}")
					db.update_record(table, rec_id, message_category = categ)

				if prev_status != new_status:
					g_log.debug(f"Updating the 'doc_status' value in DB to: '{new_status}'")
					db.update_record(table, rec_id, doc_status = new_status)

				if prev_msg_id != msg.message_id:
					g_log.warning(f"Updating the 'message_id' value in DB to: '{msg.message_id}'")
					db.update_record(table, rec_id, message_id = msg.message_id)
					g_log.warning(f"The original message with ID: '{prev_msg_id}' will be removed.")
					mails.delete_message(mails.get_message(self._account, prev_msg_id))

			try:
				pdf_file.rename(cust_folder, rec_id)
			except Exception as exc:
				g_log.error(str(exc))
				g_log.info("Writing message text to user email ...")
				mails.append_text(msg, f"G.ROBOT_RFC (ERROR): {str(exc)}")
				g_log.info("Message successfully written.")
				continue

			g_log.debug(f"Updating the 'link' value in DB to: '{Paths.get_relpath(pdf_file.path)}'")
			db.update_record(table, rec_id, link = pdf_file.path)

			try:
				location = mails.move_message(msg, cust_folder, temp_folder)
			except RuntimeWarning as wng:
				g_log.warning(wng)
			else:
				g_log.info(f"Message moved to: '{location}'")

			g_log.info("Writing message to user email ...")
			mails.append_text(msg, "G.ROBOT_RFC (INFO): Message attachment downloaded.")
			g_log.info("Message successfully written.")

			if self._cfg["customers"][cust_folder]["extractor"].upper() != "AI":
				continue

			# NOTE: added storing of pdf files to azure blob and data extraction using Forms recognizer
			virt_dir = self._cfg["blob"]["virtual_dir"].replace("$customer$", cust_folder)

			try:
				g_log.info("Uploading file to the Azure Blob Storage ...")
				storage.create_blob(self._container, pdf_file.path, virt_dir, overwrite = True)
			except Exception as exc:
				g_log.exception(exc)
			else:
				g_log.info("File successfully uploaded.")

		logger.section_break(g_log)

	def provide(self) -> None:
		"""Save received debit/credit notes as pdf files into a folder."""

		for cust_folder in self._cfg["customers"]:

			g_log.info(f"Processing email folder: '{cust_folder}'")

			g_log.info("Collecting emails ...")
			emails = mails.get_messages(self._account, cust_folder)
			g_log.info(f"Found {len(emails)} emails to process.")

			if len(emails) == 0:
				g_log.info("Folder processed.\n")
				continue

			g_log.info("Downloading data from emails ...")
			try:
				self._download_emails_data(
					emails,
					msg_categs = self._cfg["mails"]["categories"]["documents"],
					ctrl_categs = self._cfg["mails"]["categories"]["control"],
					dst_dir = self._cfg["dirs"]["input"],
					cust_folder = cust_folder,
					cust_subfolders = self._cfg["mails"]["subfolders"],
					doc_states = self._cfg["processing"]["document_states"],
					table = self._table
				)
			except Exception as exc:
				g_log.exception(exc)
				continue  # try processing next folder instead of returning from func

			g_log.info(f"Folder '{cust_folder}' successfully processed.\n")
