"""The Dispatcher service."""

import argparse
import sys
from os.path import join
from . import Dispatcher
from .. import logger

log = logger.get_logger()

def main() -> int:
	"""Runs the Dispatcher service.

	Returns:
	--------
	One of the following exit codes:
		- 0: If program successfully completes.
		- 1: If program fails due to a critical error.
	"""

	try:
		Dispatcher().run()
	except Exception as exc:
		log.exception(exc)
		log.critical("Unhandled exception!")
		return 1

	return 0

if __name__ ==  "__main__":

	parser = argparse.ArgumentParser()

	parser.add_argument(
		"--order_str", required = True,
		help = "ID of the task in Task Manager.",
	)

	args = vars(parser.parse_args())

	log_path = logger.get_log_path(
		args["order_str"],
		subdir = "services",
		task = "Dispatcher"
	)

	log_cfg = join(sys.path[0], "log_config.yaml")
	logger.initialize(log_path, log_cfg)
	logger.cleanup(n_weeks = 12)  # delete obsolete logs

	exit_code = main()
	log.info(f"=== System shutdown with return code: {exit_code} ===")
	sys.exit(exit_code)
