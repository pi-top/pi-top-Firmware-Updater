from argparse import ArgumentParser
from os import geteuid
from sys import exit

import click
from pitop.common.firmware_device import FirmwareDevice
from pitop.common.logger import PTLogger
from pitop.system import device_type

from . import check, update


def is_root() -> bool:
    return geteuid() == 0


@click.command()
@click.option(
    "--log-level",
    type=int,
    help="Set the logging level from 10 (more verbose) to 50 (less verbose).",
    default=20,
)
@click.option(
    "--loop-time",
    type=int,
    help="Sets the time interval in seconds that the script will wait before each update check.",
    default=3,
    choices=range(1, 300),
)
@click.option(
    "-f",
    "--force",
    help="Forces firmware update check and applies to all devices.",
    action="store_true",
)
@click.option(
    "-t",
    "--wait-timeout",
    type=int,
    help="Amount of time (in seconds) to wait for web portal to report that firmware updates can start, excluding an OS (system packages) upgrade.",
    default=300,
    choices=range(0, 999),
)
@click.option(
    "-m",
    "--max-wait-timeout",
    type=int,
    help="Maximum time (in seconds) to wait for web portal to report that firmware updates can start, including an OS (system packages) upgrade.",
    default=3600,
    choices=range(0, 9999),
)
def do_check():
    if device_type() != "pi-top [4]":
        PTLogger.error("This program only runs on a pi-top [4]")
        exit(0)

    if not is_root():
        PTLogger.error(
            "This program requires root privileges. Run as root using 'sudo'."
        )
        exit(1)

    parsed_args = parser.parse_args()
    PTLogger.setup_logging(
        logger_name="pt-firmware-updater", logging_level=parsed_args.log_level
    )
    try:
        check.main(parsed_args)
    except Exception as e:
        PTLogger.error(f"{e}")
        exit(1)


parser = ArgumentParser(description="pi-top firmware updater")
parser.add_argument(
    "device",
    help="pi-top firmware device to apply firmware update to. "
    "Valid devices are {}".format(
        [dev.name for dev in FirmwareDevice.valid_device_ids()]
    ),
)
parser.add_argument(
    "-f", "--force", help="Skip internal checks of fw file", action="store_true"
)
parser.add_argument(
    "--log-level",
    type=int,
    help="Set the logging level from 10 (more verbose) to 50 (less verbose).",
    default=20,
)
parser.add_argument(
    "-i",
    "--interval",
    type=float,
    help="Set the interval speed at which packages will be sent to the device "
    "during an update.",
    default=0.1,
)
parser.add_argument(
    "-p",
    "--path",
    type=str,
    help="Path to the binary file to install. If not provided, updates will be "
    "searched in system folders",
    default="",
    required=True,
)
parser.add_argument(
    "-n",
    "--notify-user",
    help="Make update interactive by displaying desktop notifcations to the user",
    action="store_true",
)


def do_update():
    if device_type() != "pi-top [4]":
        PTLogger.error("This program only runs on a pi-top [4]")
        exit(1)

    if not is_root():
        PTLogger.error(
            "This program requires root privileges. Run as root using 'sudo'."
        )
        exit(1)

    parsed_args = parser.parse_args()
    try:
        update.main(parsed_args)
    except Exception as e:
        PTLogger.error(f"{e}")
        exit(1)


if __name__ == "__main__":
    do_check(prog_name="pt-firmware-updater")
