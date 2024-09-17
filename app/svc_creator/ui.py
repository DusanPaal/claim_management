# pylint: disable = W0718, W1203

"""The Creator service."""

import argparse
import sys
import engine
from engine.claim.core import ClaimManager

g_log = engine.get_logger()

def main(args: dict) -> int:
    """Runs the Creator service.

	args:
	-----
	order_str: `str`
		ID (order string) of the task in Task Manager.

	Returns:
	--------
	One of the following exit codes:
		- 0: If program successfully completes.
		- 1: If program fails due to a critical error.
    """

    try:
        ClaimManager(args["order_str"]).execute()
    except Exception as exc:
        g_log.exception(exc)
        g_log.critical("Unhandled exception!")
        return 1

    return 0


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--order_str", required = True,
        help = "ID of the task in Task Manager."
    )

    exit_code = main(vars(parser.parse_args()))
    g_log.info(f"=== System shutdown with return code: {exit_code} ===")
    sys.exit(exit_code)
