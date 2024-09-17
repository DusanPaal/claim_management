# pylint: disable = C0103, W0718

"""Task cancellation."""

import sys
import engine
from engine.controller import Lock, ClaimLocks

g_log = engine.get_logger()


import sys
from enum import Enum
from os import remove
from os.path import isfile, join
from . import logger

g_log = logger.get_global_logger()


class ClaimLocks(Enum):
    """Available locks for the 'claim' component."""
    MANAGER = "claim_manager"
    DOWNLOADER = "claim_downloader"
    ARCHIVER = "claim_archiver"
    DISPATCHER = "claim_dispatcher"
    EXTRACTOR = "claim_exractor"


class CreditLocks(Enum):
    """Available locks for the 'credit' component."""
    MANAGER = "credit_manager"


class Lock:
    """Task lock."""

    def __init__(self, name: ClaimLocks) -> None:
        """
        Create a task execution lock.

        Params:
        -------
        name: Name of the task.
        """
        lock_dir = join(sys.path[0], "engine", "control")
        self._lock_path = join(lock_dir, f"cancel_{name.value}.txt")

    def release(self) -> None:
        """
        Release a task execution lock by deleting the
        respective lock file from the controlling directory.
        """
        if self.exists():
            remove(self._lock_path)

    def exists(self) -> bool:
        """Check if a task execution lock exists."""
        return isfile(self._lock_path)

    def activate(self) -> None:
        """
        Activate a task execution lock by creating
        a lock file in the controlling directory.
        """

        if self.exists():
            return

        with open(self._lock_path, "w", encoding = "ascii"):
            pass


def main() -> int:
	"""
	Cancels a running SAP processing task.

	Returns:
	--------
	One of the following exit codes:
	- 0: If program successfully completes.
	- 1: If program fails due to a critical error.
	"""

	try:
		lock = Lock(ClaimLocks.MANAGER)
		g_log.info("Activating task execution lock ...")
		lock.activate()
		g_log.info("Lock activated.")
	except Exception as exc:
		g_log.exception(exc)
		g_log.critical("Unhandled exception!")
		return 1

	return 0


if __name__ == "__main__":
	exit_code = main()
	g_log.info("=== System shutdown with return code: %d ===", exit_code)
	sys.exit(exit_code)
