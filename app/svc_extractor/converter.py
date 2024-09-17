# pylint: disable = R0903, R0913

"""
Converts content of pdf documents to strings and extracts relevant
accounting data to dictionaries using pre-defined .yml regex templates.
The extracted strings as well as data dicts can be stored as local
.txt files, or .json files respectively.
"""

from time import sleep
import requests
import urllib3
from ....resources.files import FilePath
from .... import logger

g_log = logger.get_global_logger()

# custom errors
class ServerError(Exception):
	"""Error communicating with the OCR server."""


class Converter:
	"""Converts pdf to raw text."""

	BAD_GATEWAY = 502
	RESPONSE_OK = 200

	def __init__(
		self, url: str, route: str, access_token: str,
		n_attempts: int = 10, wait_attempt: int = 2,
		timeout: int = 30, debugging: bool = False) -> None:
		"""
		Create a PDF converter.

		Params:
		-------
		url:
			URL address of the OCR server.

		route:
			Name of the route used to scan a specific type \n
			of pdf document:
			- v2/pdf_file: for textual pdf files
			- v2/scanned_pdf_file: for scanned pdf files

		access_token:
			Token-based authentication (secret) to allow accessing the OCR API.

		n_attempts:
			Number of attempts to communicate with the server
			if no response is received.

		wait_attempt:
			Elapsed seconds between each reattempt to send the request.

		timeout:
			Time in seconds to wait for the server
			to send data before giving up.

		debugging:
			If true, debug messages are loggged.

		Raises:
		-------
		ValueError:
		"""

		self._url = url
		self._route = route
		self._access_token = access_token
		self._n_attempts = n_attempts
		self._timeout = timeout
		self._wait_attempt = wait_attempt
		self._debugging = debugging

		urllib3.disable_warnings()

	def _debug(self, response) -> None:
		"""Logs debugging data."""

		if not self._debugging:
			return

		msg = "Server response:"
		params = response.__dict__.items()

		for param, val in params:

			if param.startswith("_") or param in ("connection", "raw"):
				continue

			line = ": ".join([f"'{param}'", str(val)])
			msg = "\n\t".join([msg, line])

		g_log.info(msg)

	def convert(self, pdf: FilePath, clean: bool = False, header: bool = False) -> str:
		"""
		Convert PDF to raw text using an OCR technology.

		Params:
		-------
		pdf:
			Path to the PDF file to convert.

		clean:
			If `True`, then redundant form feed characters
			are removed from the resulting text.

		header:
			If `True`, then the conversion info header
			will be printed on top of the resulting text.

		Returns:
		--------
		Text extracted from the PDF file.
		"""
		content = open(pdf, 'rb')

		pdf_content = {"pdf": content}
		headers = {"access_token": self._access_token}
		url_address = f"{self._url}/{self._route}"
		nth = 0

		while nth < self._n_attempts:

			try:
				response = requests.post(
					url_address,
					files = pdf_content,
					headers = headers,
					verify = False,
					timeout = self._timeout
				)
			except Exception as exc:
				content.close()
				raise ServerError(str(exc)) from exc

			if response.status_code != self.BAD_GATEWAY:
				nth = 0
				break

			nth += 1
			sleep(self._wait_attempt)

		content.close()

		if nth != 0:
			self._debug(response)
			raise ServerError("Attemps to communicate with the server run out.")

		# if response.status_code != self.RESPONSE_OK:
		if not response.ok:
			self._debug(response)
			raise ServerError(f"OCR server error {response.status_code}: {response.reason}")

		text = response.text

		if clean:
			text = text.replace("\x0c", "")

		if not header:
			return text

		# tag the text with the pdf conversion OCR route for better clarity
		header_text = f"-------------- OCR route: {self._route} --------------"
		text = "\n\n".join([header_text, text])

		return text
