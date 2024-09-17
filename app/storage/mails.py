# pylint: disable = C0302, W1203

"""
The 'mails.py' module creates and sends of emails directly via SMTP server.
It also uses the exchangelib library to connect to the Exchange server via
Exchange Web Services (EWS) in order to retrieve messages and save message
attachment under a specified account.
"""

import os
import pickle as pkl
import re
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from os.path import basename, exists, isfile, join, split, splitext
from smtplib import SMTP
from typing import Any, Union, overload, Iterable

import exchangelib as xlib

from exchangelib import (
	Account, Build, Configuration, EWSDateTime,
	ExtendedProperty, FileAttachment, Identity, Message,
	OAuth2Credentials, Version, HTMLBody
)

from exchangelib.errors import (
	ErrorExceededConnectionCount,
	ErrorFolderNotFound
)

from exchangelib.folders import SingleFolderQuerySet
from win32com.client import Dispatch

from .. import logger

Path = str
g_log = logger.get_logger("global")

# custom message classes
class SmtpMessage(MIMEMultipart):
	"""
	Wraps MIMEMultipart objects
	that represent messages to
	sent via an SMTP server.
	"""

class FlagCompleted(ExtendedProperty):
	"""
	Extends properties of
	exchangelib:Message objects.
	"""
	property_tag = 0x1090
	property_type = 'Integer'

# custom exceptions and warnings
class IdenticalFolderWarning(Warning):
	"""
	Message already in the target folder.

	Raised when an attempt is made to move
	a message to a new folder that is identical
	to the original message folder.
	"""

class MultipleMessagesWarning(Warning):
	"""
	Raised when multiple messages
	with the same message ID exist.
	"""

class UndeliveredError(Exception):
	"""Message delivery failes."""

class FolderNotFoundError(Exception):
	"""A local file directory doesn't exist."""

class MessageConversionError(Exception):
	"""Conversion of email body to pdf fails."""

class NoAttachmentError(Exception):
	"""Mesage attachment doesn't exist."""

class InvalidAttachmentsError(Exception):
	"""Attachment of a specific file type doesn't exist."""

class MultipleAttachmentsError(Exception):
	"""
	Multiple attachments of a specific file type
	exist where only a single attachment is expected.
	"""

class DuplicateMessageError(Exception):
	"""More than one message with the same ID exist."""

# in order to implement additional nessage props,
# these must be registereg prior to accessing them
Message.register('flag_completed', FlagCompleted)

def _is_iterable(value: Any, generators: bool = False) -> bool:
	"""
	Check if value is a list-like object.

	Don't match generators and generator-like objects here by default,
	because callers don't necessarily guarantee that they only iterate
	the value once. Take care to not match string types and bytes.

	Parameters:
	-----------
	value:
		Any type of object.

	generators:
		If True, generators will be treated as iterable.
	"""

	if generators:
		if not isinstance(value, (bytes, str)) and hasattr(value, "__iter__"):
			return True
	else:
		if isinstance(value, (tuple, list, set)):
			return True

	return False

def _get_credentials(acc_name: str) -> OAuth2Credentials:
	"""Returns credentials for a given account."""

	cred_dir = join(os.environ["APPDATA"], "bia")
	cred_path = join(cred_dir, f"{acc_name.lower()}.token.email.dat")

	if not isfile(cred_path):
		raise FileNotFoundError(f"Credentials file not found: {cred_path}")

	with open(cred_path, encoding = "utf-8") as stream:
		lines = stream.readlines()

	params = dict(
		client_id = None,
		client_secret = None,
		tenant_id = None,
		identity = Identity(primary_smtp_address = acc_name)
	)

	for line in lines:

		if ":" not in line:
			continue

		tokens = line.split(":")
		param_name = tokens[0].strip()
		param_value = tokens[1].strip()

		if param_name == "Client ID":
			key = "client_id"
		elif param_name == "Client Secret":
			key = "client_secret"
		elif param_name == "Tenant ID":
			key = "tenant_id"

		params[key] = param_value

	# verify loaded parameters
	if params["client_id"] is None:
		raise ValueError("Parameter 'client_id' not found!")

	if params["client_secret"] is None:
		raise ValueError("Parameter 'client_secret' not found!")

	if params["tenant_id"] is None:
		raise ValueError("Parameter 'tenant_id' not found!")

	# params OK, create credentials
	creds = OAuth2Credentials(
		params["client_id"],
		params["client_secret"],
		params["tenant_id"],
		params["identity"]
	)

	return creds

def _sanitize_emails(addr: Union[str,list]) -> list:
	"""
	Trims email address(es) and checks if their name
	format complies to the company's naming standards.
	"""

	mails = []
	validated = []

	if isinstance(addr, str):
		mails = [addr]
	elif isinstance(addr, list):
		mails = addr
	else:
		raise TypeError(f"Argument 'addr' has invalid type: {type(addr)}")

	for mail in mails:

		stripped = mail.strip()
		validated.append(stripped)

		# check if email is Ledvance-specific
		if re.search(r"\w+\.\w+@ledvance.com", stripped) is None:
			raise ValueError(f"Invalid email address format: '{stripped}'")

	return validated

def create_message(
		from_addr: str,
		to_addr: Union[str,list],
		subj: str,
		body: str,
		att: Union[str,list] = None
	) -> SmtpMessage:
	"""
	Creates a SMTP message.

	Params:
	-------
	from_addr:
		Email address of the sender.

	to_addr:
		Recipient address(es).
		If a string email address is used, the message will be sent to that specific address.
		If multiple addresses are used, then the message will be sent to all of the recipients.

	subj:
		Message subject.

	body:
		Message body in HTML format.

	att:
		Any valid path(s) to message atachment file(s).
		If None is used (default value), then a message without
		any file attachments will be created. If a file path is used,
		then this file will be attached to the message. If multiple
		paths are used, these will be attached as multiple attachments
		to the message. If any of the attachment paths used is not found,
		then an AttachmentNotFoundError exception is raised.

	Returns:
	--------
	A SmtpMessage object representing the message.
	"""

	# check input
	if len(to_addr) == 0:
		raise ValueError("No message recipients provided in 'to_addr' argument!")

	if att is None:
		att_paths = []
	elif isinstance(att, list):
		att_paths = att
	elif isinstance(att, str):
		att_paths = [att]
	else:
		raise TypeError(f"Argument 'att' has invalid type: {type(att)}")

	for att_path in att_paths or []:
		if not isfile(att_path):
			raise FileNotFoundError(
				f"Attachment not found: {att_path}"
			)

	# sanitize input
	recips = _sanitize_emails(to_addr)

	# process
	email = SmtpMessage()
	email["Subject"] = subj
	email["From"] = from_addr
	email["To"] = ";".join(recips)
	email.attach(MIMEText(body, "html"))

	for att_path in att_paths:

		with open(att_path, "rb") as stream:
			payload = stream.read()

		# The content type "application/octet-stream" means
		# that a MIME attachment is a binary file
		part = MIMEBase("application", "octet-stream")
		part.set_payload(payload)
		encoders.encode_base64(part)

		# get file name
		file_name = split(att_path)[1]

		# Add header
		part.add_header(
			"Content-Disposition",
			f"attachment; filename = {file_name}"
		)

		# Add attachment to the message
		# and convert it to a string
		email.attach(part)

	return email

def send_smtp_message(msg: SmtpMessage, host: str, port: int) -> None:
	"""
	Sends a message using an SMTP server.

	Params:
	-------
	msg:
		An exchengelib.Message object representing the Message to be sent.

	host:
		Name of the SMTP host server used for message sending.

	port:
		Number o the SMTP server port.

	Raises:
	-------
	UndeliveredError:
		When message fails to reach all the required recipients.

	InvalidSmtpHostError:
		When an invalid host name is used for SMTP connection.

	TimeoutError:
		When attempt to connect to the SMTP server times out.
	"""

	with SMTP(host, port, timeout = 30) as smtp_conn:
		smtp_conn.set_debuglevel(0) # off = 0; verbose = 1; timestamped = 2
		send_errs = smtp_conn.sendmail(msg["From"], msg["To"].split(";"), msg.as_string())

	if len(send_errs) != 0:
		failed_recips = ';'.join(send_errs.keys())
		raise UndeliveredError(f"Message undelivered to: {failed_recips}")

def get_message_location(msg: Message) -> tuple:
	"""
	Identifies message location in the mailbox.

	Params:
	-------
	msg:
		An exchengelib:Message object.

	Returns:
	--------
	A tuple of (str, str, str):
		first param: message's absolute path in the mailbox
		second param: message's relative path in the mailbox
		third param: name of the message's parent folder
	"""

	folders = SingleFolderQuerySet(
		account = msg.account,
		folder = msg.account.root
	)

	folder_id = msg.account.root.get(id = msg.id).parent_folder_id.id
	folder = folders.get(id = folder_id)

	absolute_path = folder.absolute
	relative_path = absolute_path.replace("/root/Top of Information Store/", "")

	return (absolute_path, relative_path, folder.name)

def move_message(msg: Message, *folders: str) -> str:
	"""
	Moves message to a destination folder
	located at a path defined by a sequence
	of subfolders.

	Params:
	-------
	msg:
		A exchangelib:Message object
		representing the message to move.

	folders:
		A sequence of subfolder names that defines
		the path to the destination subfolder.

	Example:
	--------
	>>> move_message(msg, "MARKANT_DE", "done")
	>>> "Inbox/MARKANT_DE/done"

	Returns:
	--------
	Path to the detination folder in the mailbox.

	Raises:
	-------
	IdenticalFolderWarning:
		When the message is already in the target folder.
	"""

	acc = msg.account
	dst_location = acc.inbox

	for fol in folders:
		dst_location = dst_location // fol

	curr_loc_abs, curr_loc_rel, _ = get_message_location(msg)

	if curr_loc_abs == dst_location.absolute:
		raise IdenticalFolderWarning(
			"The message is already in the "
			f"target location: '{curr_loc_rel}'")

	msg.move(dst_location)
	msg.account.root.update_folder(dst_location)

	dst_location.refresh()
	msg.account.inbox.refresh()
	acc.root.refresh()

	try:
		acc.public_folders_root.refresh()
	except ErrorExceededConnectionCount as exc:
		g_log.error(str(exc))
		g_log.warning(
			"The exception is being intentionally ignored. "
			"If the messages are successfully moved without "
			"calling the 'Account.public_folders_root.refresh()' "
			"procedure, then the entire statement may be removed "
			"from the production version."
		)

	newpath_abs, newpath_rel, _ = get_message_location(msg)
	assert dst_location.absolute == newpath_abs, "Moving failed!"

	return newpath_rel

def move_messages(acc: Account, ids: list, *folders: str) -> list:
	"""
	Moves message to a destination folder
	located at a path defined by a sequence
	of subfolders.

	Params:
	-------
	msg:
		A excchangelib.Message object
		representing the message to move.

	folders:
		A sequence of subfolder names that defines
		the path to the destination subfolder.

	Returns:
	--------
	Path to the detination folder in the mailbox.

	Raises:
	-------
	MessageInLocationWarning:
		When the message is already in the target folder.
	"""

	dst_folder = acc.inbox

	for fol in folders:
		dst_folder = dst_folder // fol

	new_ids = acc.bulk_move(ids, dst_folder)

	return new_ids

def set_message_property(msg: Message, name: str) -> None:
	"""
	Sets a message property value.

	Params:
	-------
	msg:
		An exchange.Message object
		representing the message to modify.

	name:
		Name of the property to set. Available properties:
		- 'read': Marks message as read
		- 'unread': MArks message as unread.
		- 'completed': Tags message with the "Completion" flag.
		- 'not_completed': Untags the "Completion" flag from the message.
	"""

	if name == "read":
		msg.is_read = True
		msg.save(update_fields=['is_read'])
	elif name == "unread":
		msg.is_read = False
		msg.save(update_fields=['is_read'])
	elif name == "completed":
		msg.flag_completed = True
		msg.save(update_fields=['flag_completed'])
	elif name == "not_completed":
		msg.flag_completed = False
		msg.save(update_fields=['flag_completed'])
	else:
		raise ValueError(f"Unrecognized message flag: {name}")

def contains_attachment(msg: Message, ext: str = None) -> bool:
	"""
	Checks if a message contains any attachment.

	Params:
	-------
	msg:
		An exchangelib:Message object representing the email.

	ext:
		File extension, that determines which attachment types to consider.
		If None is used, (default value), then any attachment will be considered.
		If a file extension is used (e. g. '.pdf'), then attached files of that particular
		type will be considered only.

	Returns:
	--------
	True if any attachment is found, False if not.
	"""

	if ext is None and len(msg.attachments) > 0:
		return True

	for att in msg.attachments:
		if att.name.lower().endswith(ext):
			return True

	return False

def get_attachments(msg: Message, ext: str) -> dict:
	"""
	Fetches message attachments.

	Params:
	-------
	msg:
		An exchangelib:Message object representing the email.

	ext:
		Type of attachment file type, case insensitive, with
		or without a period (e.g. 'pdf', 'docx', '.xlsx', ...).

	Returns:
	--------
	Names of message attachments and their binary contents.
	"""

	if len(msg.attachments) == 0:
		return {}

	atts = {}

	if not ext.startswith("."):
		ext = "".join([".", ext])

	for att in msg.attachments:

		if not isinstance(att, FileAttachment):
			g_log.warning(
				f"Object '{att.name}' is not a 'FileAttachment' "
				"type and won't be downloaded.")
			continue

		if not att.name.lower().endswith(ext):
			g_log.warning(
				f"Unsupported attachment type '{att.name}' "
				"won't be downloaded.")
			continue

		atts.update({att.name: att.content})

	return atts

def download_attachment(
		msg: Message,
		dst_folder: str,
		ext: str,
		overwrite: bool = False
	) -> str:
	"""
	Stores a message attachment to a .pdf file.

	Params:
	-------
	msg:
		An exchangelib:Message object representing the email.

	dst_folder:
		Path to the folder where the pdf will be stored.

	overwrite:
		If True, then an existing file should be overwritten.
		If False, then a new copy of the file will be created.

	Returns:
	--------
	Path to the stored pdf file.
	"""

	if ext != ".pdf":
		raise ValueError(f"Unsupported file type: {ext}")

	if len(msg.attachments) == 0:
		raise NoAttachmentError(f"The message contains no {ext} attachment.")

	valid_count = 0
	valid_idx = 0

	for att in msg.attachments:

		if not isinstance(att, FileAttachment):
			g_log.warning(
				f"Object '{att.name}' is not a 'FileAttachment' "
				"type and won't be downloaded.")
			valid_idx += 1
			continue

		if not att.name.lower().endswith(ext):
			g_log.warning(f"Attachment '{att.name}' won't be downloaded.")
			valid_idx += 1
			continue

		old_ext = splitext(att.name)[1]
		new_ext = old_ext.lower()
		file_name = att.name.replace(old_ext, "")
		full_file_name = "".join([file_name, new_ext])

		valid_count += 1
		break

	if valid_count == 0:
		raise InvalidAttachmentsError(
			f"The message contains no {ext} attachment "
			"and therefore cannot be processed."
		)

	if valid_count > 1:
		raise MultipleAttachmentsError(
			f"The message contains more than one {ext} "
			"attachment and therefore cannot be processed. "
			"Currently, supported are messages with a single "
			"attached file only."
		)

	file_path = join(dst_folder, full_file_name)
	n_files = 1

	while isfile(file_path) and not overwrite:
		copy_flag = f"_copy_{str(1).zfill(3)}"
		full_file_name = "".join([file_name, copy_flag, new_ext])
		file_path = join(dst_folder, full_file_name)
		n_files += 1

	att = msg.attachments[valid_idx]

	with open(file_path, "wb") as stream:
		stream.write(att.content)

	return file_path

def download_attachments(
		msg: object,
		folder_path: str,
		ext: str = None
	) -> list:
	"""
	Saves message attachment(s) to file(s).

	Params:
	-------
	msg:
		An exchangelib:Message object containing attachment(s).

	folder_path:
		Path to the folder where attachments will be stored.

	ext:
		If None is used (default), then all attachments will be downloaded,
		regardless of their file type. If a file extension (e.g. '.pdf') is used,
		then only attachmnets of that particular file type will be downloaded.
		The parameter is case insensitive.

	Returns:
	--------
	A list of file paths to the stored attachments.
	"""

	if not exists(folder_path):
		raise FolderNotFoundError(f"Folder does not exist: {folder_path}")

	file_paths = []

	for att in msg.attachments:

		file_path = join(folder_path, att.name)

		if not (ext is None or file_path.lower().endswith(ext)):
			continue

		with open(file_path, 'wb') as stream:
			stream.write(att.content)

		if not isfile(file_path):
			raise FileNotFoundError(f"Error writing attachment data to file: {file_path}")

		file_paths.append(file_path)

	return file_paths

def download_message(msg: Message, file_path: str) -> None:
	"""
	Stores an exchangelib:Message object to a local file.
	The message object is serialized to a binary .pkl format
	before saving.

	Params:
	-------
	msg:
		An exchangelib:Message object to pickle.

	file_path:
		Path to the file to store the message.
	"""

	if not file_path.endswith(".pkl"):
		raise ValueError(f"Unsupported file type: {file_path} !")

	# Avoid primitives locking that
	# are present only in Account object
	# by disconnecting the message from
	# its account.
	acc = msg.account
	msg.account = None

	# now serialize the account object.
	with open(file_path, 'wb') as stream:
		stream.write(pkl.dumps(msg))

	# restore account reference
	msg.account = acc

def load_pickled_message(file_path: str) -> Message:
	"""
	Loads a serielized exchangelib:Message
	object from a pickle file.

	Params:
	-------
	file_path:
		Path to the .pkl file.

	Returns:
	--------
	An exchangelib:Message object
	representing the message content.
	"""

	if not file_path.endswith(".pkl"):
		raise ValueError(f"Unsupported file type used: {file_path}")

	with open(file_path, 'rb') as stream:
		content = stream.read()

	msg = pkl.loads(content)

	return msg

def convert_message(msg: Message, pdf_path: str) -> None:
	"""
	Converts a message body to a landscape-oriented .pdf file
	while preserving the original document layout and formatting.

	Params:
	-------
	msg:
		An exchangelib:Message object representing the email.

	file_path:
		Path to the output pdf file.

	remove_text:
		If True, any notes written by the automation to the
		message body during document processing are removed.
	"""

	folder_path, file_name = split(pdf_path)

	if not file_name.endswith(".pdf"):
		raise ValueError("Unsupported file format used!")

	if not exists(folder_path):
		raise FolderNotFoundError(f"Destination folder not found: {folder_path}")

	# COM Word constants
	wd_orient_landscape = 1
	wd_export_format_pdf = 17
	wd_do_not_save_changes = 0

	# write the text content to a temporary .mht file
	mht_path = join(folder_path, file_name.replace(".pdf", ".mht"))

	with open(mht_path, 'w', encoding = "UTF-8") as stream:
		stream.write(msg.text_body)

	# # open the .mht archive in MS Word app, adjust page layout
	# pdf_path = join(folder_path, file_name.replace(".msg", ".pdf"))

	word = Dispatch("word.application")
	doc = word.Documents.Open(FileName = mht_path, Visible = False)

	doc.PageSetup.Orientation = wd_orient_landscape
	doc.PageSetup.LeftMargin = 36
	doc.PageSetup.TopMargin = 18
	doc.PageSetup.BottomMargin = 18

	# the font size of tables needs to be decresed
	# in order to fit into the page width
	for tbl in doc.Tables:
		for row in tbl.Rows:
			for cell in row.Cells:
				cell.Range.Font.Size = 10

	# Export the document to a pdf file, then close the word.
	try:
		doc.ExportAsFixedFormat(pdf_path, wd_export_format_pdf)
	except Exception as exc:
		raise MessageConversionError(str(exc)) from exc
	finally:
		doc.Close(wd_do_not_save_changes)

	# remove the temporary .mht file
	os.remove(mht_path)

def get_account(
		mailbox: str,
		name: str,
		x_server: str
	) -> Account:
	"""
	Returns an account for a shared mailbox.

	Params:
	-------
	mailbox:
		Name of the shared mailbox.

	name:
		Name of the account for which
		the credentails will be obtained.

	x_server:
		Name of the MS Exchange server.

	Returns:
	--------
	An exchangelib:Account object.
	"""

	build = Build(major_version = 15, minor_version = 20)

	cfg = Configuration(
		_get_credentials(name),
		server = x_server,
		auth_type = xlib.OAUTH2,
		version = Version(build)
	)

	acc = Account(
		mailbox,
		config = cfg,
		autodiscover = False,
		access_type = xlib.IMPERSONATION
	)

	return acc

def get_message(
		acc: Account,
		email_id: str,
		duplicate: str = "ingore"
	) -> Message:
	"""
	Returns a message from an account.

	Params:
	-------
	acc:
		Account object containing the message.

	email_id:
		String ID of the message to fetch.

	duplicate:
		Action to take if messages sharing the same ID exist:
		- "ignore": The duplicate messages are ignored and only
					one copy is returned (default behavior).
		- "remove": The duplicated messages and only one copy is kept.
		- "raise": An explicit DuplicateMessageError exception is raised.

	Returns:
	--------
	An exchangelib:Message object representing the mesage.
	If no message is found, then None is returned.
	"""

	# sanitize input
	if not email_id.startswith("<"):
		email_id = "".join(["<", email_id])

	if not email_id.endswith(">"):
		email_id = "".join([email_id, ">"])

	# process
	emails = acc.inbox.walk().filter(message_id = email_id).only(
		'subject', 'body', 'text_body', 'headers', 'sender',
		'attachments', 'datetime_received', 'message_id'
	)

	if emails.count() == 0:
		return None

	msg = emails[0]

	if emails.count() > 1:
		if duplicate == "remove":
			for email in emails[1:]:
				delete_message(email)
		elif duplicate == "ignore":
			pass
		elif duplicate == "raise":
			raise DuplicateMessageError()

	return msg

def get_messages(
		acc: Account,
		cust_dir: str,
		include_subfolders = False,
		from_date: datetime = None
	) -> tuple:
	"""
	Collects message objects from a given mailbox.

	Params:
	-------
	acc:
		Account object that contains reference to a mailbox.

	cust_dir:
		Customer-related folder contained in the account inbox.

	include_subfolders:
		If True, then subfolders of a parent folder are searched.
		If False, then only the parent folder is searched.

	from_date:
		The received date from which (including) emails are searched.

	Returns:
	--------
	A tuple of `exchangelib:Message` objects that represent the collected
	emails. The emails are sorted form oldest (first) to newest (last).
	"""

	folder = acc.inbox // cust_dir

	acc.inbox.refresh()
	folder.refresh()

	if not include_subfolders:
		emails = folder.all().only(
			"subject", "sender", "attachments",
			"message_id", "text_body", "categories"
		).order_by("datetime_received")
	else:
		if from_date is None:
			emails = folder.walk().all()
		else:
			timezone = acc.default_timezone
			start = EWSDateTime.from_datetime(from_date).astimezone(timezone)
			end = EWSDateTime.from_datetime(datetime.now()).astimezone(timezone)
			emails = folder.walk().filter(datetime_received__range = (start, end))

	return tuple(emails)

@overload
def get_messages2(
		acc: Account,
		from_date: datetime = None,
		subfolders: list = None,
		refresh: bool = False
	) -> list:
	"""
	Retrieves messages from an inbox.

	Params:
	-------
	acc:
		Account object containing the message.

	from_date:
		Message received date from which the messages
		are retrieved.

	subfolders:
		Sequence of subfolder names that define the
		path to the target subfolder to be searched.

	refresh:
		If True, the source folder is refreshed before
		the message is retrieved.

	Returns:
	--------
	A list of retrieved emails.

	The email fields are filtered to fetch
	only the specified field names:
		- "attachments"
		- "message_id"
		- "text_body"
		- "categories"

	All other item fields will be 'None'.
	"""

@overload
def get_messages2(
		acc: Account,
		email_id: Union[str,list],
		subfolders: list = None,
		refresh: bool = False
	) -> list:
	"""
	Retrieves messages from an inbox.

	Params:
	-------
	acc:
		Account object containing the message.

	email_id:
		String ID of the message to retrieve.

	refresh:
		If True, the source folder is refreshed before
		the message is retrieved.

	subfolders:
		Sequence of subfolder names that define the
		path to the target subfolder to be searched.

	Returns:
	--------
	A list of retrieved emails.

	The email fields are filtered to fetch
	only the specified field names:
		- "attachments"
		- "message_id"
		- "text_body"
		- "categories"

	All other item fields will be 'None'.
	"""

def get_messages2(
		acc: Account,
		email_id: Union[str,list] = None,
		from_date: datetime = None,
		subfolders: list = None,
		refresh: bool = False
	) -> list:
	"""
	Retrieves messages from an inbox.

	Params:
	-------
	acc:
		Account object containing the message.

	email_id:
		String ID of the message to retrieve.

	from_date:
		Message received date from which the messages
		are retrieved.

	subfolders:
		Sequence of subfolder names that define the
		path to the target subfolder to be searched.

	refresh:
		If True, the source folder is refreshed before
		the message is retrieved.

	Returns:
	--------
	A list of retrieved emails.

	The email fields are filtered to fetch
	only the specified field names:
		- "attachments"
		- "message_id"
		- "text_body"
		- "categories"

	All other item fields will be 'None'.
	"""

	folder = acc.inbox

	if subfolders is not None:

		if "Inbox" in subfolders:
			subfolders.remove("Inbox")

		while len(subfolders) != 0:
			try:
				folder = folder // subfolders.pop(0)
			except ErrorFolderNotFound:
				folder = acc.inbox
				break

	if refresh:
		folder.refresh()

	if email_id is not None:

		# sanitize input
		if not email_id.startswith("<"):
			email_id = "".join(["<", email_id])

		if not email_id.endswith(">"):
			email_id = "".join([email_id, ">"])

		# gather emails
		emails = folder.walk().filter(message_id = email_id)

	else:

		# gather emails
		if len(folder.children) == 0:
			emails = folder.all()
		else:
			emails = folder.walk().all()

	if emails.count() == 0:
		return []

	# NOTE: the filter must always contain fields:
	# "attachments", "message_id", "text_body", "categories" !!!
	emails = emails.only("attachments", "message_id", "text_body", "categories")

	if from_date is not None:
		timezone = acc.default_timezone
		start = EWSDateTime.from_datetime(from_date).astimezone(timezone)
		end = EWSDateTime.from_datetime(datetime.now()).astimezone(timezone)
		emails = emails.filter(datetime_received__range = (start, end))

	return list(emails)

def get_message_ids(acc: Account, *folders: str) -> tuple:
	"""
	Returns message ID strings for specific messages.

	Params:
	-------
	acc:
		Account object containing reference to a mailbox.

	cust_dir:
		Customer-specific folder contained in the account's inbox.

	Returns:
	--------
	A tuple of strings that represent the message ID strings.
	"""

	id_strings = []

	root = acc.inbox

	for folder in folders:
		root = root // folder

	emails = root.all()

	for email in emails:
		id_strings.append(email.message_id)

	return tuple(id_strings)

def find_hash_value(msg: Message, key_patt: str) -> Union[str,None]:
	"""
	Finds a hash key in the message body and returns its value.

	Params:
	-------
	msg: Message to check.
	key_patt: A regex pattern that matches the hash key.

	Returns:
	--------
	The hash value if the message body contains the "hash" key.
	If the key is not found in the message body text, then None
	is returned.
	"""

	if msg.text_body is None:
		return None

	matches = re.findall(key_patt, msg.text_body)

	if len(matches) == 0:
		return None

	return matches[0].strip()

def append_text(
		msg: Message,
		text: str,
		sep: str = "-",
		sep_len: int = 100
	) -> None:
	"""
	Appends text to the body of a message.

	Params:
	-------
	msg:
		Represents an email message.

	text:
		Text to append.

	sep:
		Character that is used to crate a section line
		that separates the appended text from the original body.

	sep_len:
		Number repeated chars that buils the section break line.
	"""

	text = text.replace("\r\n", "<br>").replace("\n", "<br>")

	if msg.body is not None:
		msg.body = HTMLBody("<br>".join([msg.body, sep * sep_len, text]))
	elif msg.text_body is not None:
		html_body = msg.text_body.replace("\r\n", "<br>")
		msg.body = HTMLBody("<br>".join([html_body, sep * sep_len, text]))
	else:
		msg.body = HTMLBody("<br>".join([sep * sep_len, text]))

	msg.save(update_fields = ["body"])

def delete_message(msg: Message) -> None:
	"""
	Deletes a message.

	Params:
	-------
	msg:
		Email message to delete.
	"""

	msg.delete()

def attach_files(msg: Message, att: Iterable) -> None:
	"""
	Attaches files to a message.

	Parameters:
	-----------
	msg:
		Email to which the file is attached.

	att:
		Path to the file to attach.
	"""

	if not _is_iterable(att):
		raise TypeError("Attachments not an iterable!")

	for att_path in att:

		with open(att_path, "rb") as stream:
			payload = stream.read()

		file_name = basename(att_path)
		attachment = FileAttachment(name = file_name, content = payload)
		msg.attach(attachment)
		msg.save()

def attach_file(msg: Message, att: Path, name: str = None) -> None:
	"""
	Attaches file to a message.

	Parameters:
	-----------
	msg:
		Email to which the file is attached.

	att:
		Path to the file to attach.
	"""

	with open(att, "rb") as stream:
		payload = stream.read()

	att_name = basename(att) if name is None else name
	attachment = FileAttachment(name = att_name, content = payload)
	msg.attach(attachment)

def remove_attachments(msg: Message, ext: str = None) -> tuple:
	"""
	Removes file attachments form a message.

	Params:
	-------
	msg:
		Email with attachments to remove.

	Returns:
	--------
	Detached files as FileAttachment objects.
	"""

	detached = []

	if not (ext is None or ext.startswith(".")):
		ext = "".join([".", ext.lower()])

	for att in msg.attachments:

		if not (ext is None or att.name.lower().endswith(ext)):
			continue

		if isinstance(att, FileAttachment):
			detached.append(att)

	msg.detach(detached)

	return tuple(detached)
