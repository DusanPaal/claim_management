"""Contains base classes and class interfaces."""

import os
from os.path import join
from ... import logger
from resources.files import Reader, APP_ROOT, File, Parser
from .dispatcher import Dispatcher
from .downloader import Downloader
from .archiver import Archiver
from .extractor import Extractor, DocumentsNotFoundWarning
from abc import ABC, abstractmethod

g_log = logger.get_global_logger()

class IService(ABC):
    """Interface of a service."""

    @abstractmethod
    def run(self) -> None:
        """Provide a service."""

class IManager(ABC):
    """Interface for context managers."""

    @abstractmethod
    def execute(self) -> None:
        """Execute an operation."""


class ServiceManager(IManager):
	"""Manage execution of services."""

	_cfg = None
	_svc_name = None

	_services = {
		"downloader": Downloader,
		"dispatcher": Dispatcher,
		"archiver": Archiver,
		"extractor": Extractor,
	}

	def __init__(self, svc: str, order_str: str) -> None:
		"""
		Initialize the service control manager.

		Params:
		-------
		svc: Name of the service to request.
		order_str: Task order identification string in the Task Manager.
		"""

		log_path = logger.get_log_path(order_str, subdir = "services", task = svc)
		log_cfg = join(APP_ROOT, "log_config.yaml")
		logger.initialize(log_path, log_cfg)

		g_log.info("=== Initializing service control manager ===")

		g_log.info(f"Verifying the requested service '{svc}' ...")
		if svc not in self._services:
			raise ValueError(f"The requested service '{svc}' doesn't exist!")
		g_log.info("The service is available.")

		self._svc_name = svc
		self._cfg = self._load_app_config()

		g_log.info("=== Service control manager initialized ===")

	def __del__(self) -> None:
		"""Release the service control manager."""

		g_log.info("=== Releasing service control manager ===")
		del self._cfg
		g_log.info("=== Service control manager released ===\n")

	def _load_app_config(self) -> dict:
		"""
		Load application configuration.

		Returns:
		--------
		A dict of configuration parameters
		and and their respective values.
		"""

		g_log.info("Loading application configuration ...")

		# read app config
		cfg_path = join(APP_ROOT, "app_config.yaml")
		cfg = Reader(cfg_path).read()

		# read connection params for Azure blob storage
		blob_params_path = cfg["blob"]["connection_params_path"]
		del cfg["blob"]["connection_params_path"]

		blob_creds_path = join(os.environ["APPDATA"], blob_params_path)
		blob_creds = Parser.parse_credentials(File(blob_creds_path))
		cfg["blob"].update(blob_creds)

		# read connection params for MS forms recognizer
		recognizer_params_path = cfg["form_recognizer"]["connection_params_path"]
		del cfg["form_recognizer"]["connection_params_path"]

		recognizer_creds_path = join(os.environ["APPDATA"], recognizer_params_path)
		recognizer_creds = Parser.parse_credentials(File(recognizer_creds_path))
		cfg["form_recognizer"].update(recognizer_creds)

		g_log.info("Configuration loaded.")

		return cfg

	def execute(self) -> None:
		"""Execute the requested service."""

		g_log.info("The service control manager is starting the service ...")
		svc = self._services[self._svc_name]

		try:
			svc(self._cfg).provide()
		except DocumentsNotFoundWarning as wng:
			g_log.warning(wng)
		except Exception as exc:
			g_log.error(
				"The service control manager encountered "
				"an unhandled error in the running service.")
			del svc
			raise RuntimeError(str(exc)) from exc
		else:
			del svc # To end the service here, its destructor must be called explicitly.
			g_log.info("The service control manager has completed the service.")
