import logging
from os import geteuid
from sys import exit

import click
import click_logging
from pitop.common.firmware_device import FirmwareDevice
from pitop.system import device_type
from systemd.journal import JournalHandler

from . import check, update

logger = logging.getLogger()
click_logging.basic_config(logger)


def is_root() -> bool:
    return geteuid() == 0


def handle_exit_cases():
    if device_type() != "pi-top [4]":
        logger.error("This program only runs on a pi-top [4]")
        exit(0)

    if not is_root():
        logger.error("This program requires root privileges. Run as root using 'sudo'.")
        exit(1)


@click.command()
@click.option(
    "-f",
    "--force",
    help="Forces firmware update check and applies to all devices.",
    is_flag=True,
)
@click.option(
    "--loop-time",
    help="Sets the time interval in seconds that the script will wait before each update check.",
    default=3,
    type=click.IntRange(1, 300),
)
@click_logging.simple_verbosity_option(logger)
@click.version_option()
def do_check(force, loop_time):
    handle_exit_cases()
    try:
        check.main(force, loop_time)
    except Exception as e:
        logger.error(f"{e}")
        exit(1)


@click.command()
@click.argument(
    "device", type=click.Choice([dev.name for dev in FirmwareDevice.valid_device_ids()])
)
@click.option("-f", "--force", help="Skip internal checks of fw file", is_flag=True)
@click.option(
    "-i",
    "--interval",
    type=float,
    help="Set the interval speed at which packages will be sent to the device "
    "during an update.",
    default=0.1,
)
@click.option(
    "-p",
    "--path",
    type=str,
    help="Path to the binary file to install. If not provided, updates will be "
    "searched in system folders",
    default="",
    required=True,
)
@click.option(
    "-n",
    "--notify-user",
    help="Make update interactive by displaying desktop notifications to the user",
    is_flag=True,
)
def do_update(device, force, interval, path, notify_user):
    handle_exit_cases()

    logger.addHandler(JournalHandler())

    try:
        update.main(device, force, interval, path, notify_user)
    except Exception as e:
        logger.error(f"{e}")
        exit(1)


if __name__ == "__main__":
    do_check(prog_name="pt-firmware-updater")
