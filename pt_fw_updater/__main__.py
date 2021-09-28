from os import geteuid
from sys import exit

import click
from pitop.common.firmware_device import FirmwareDevice
from pitop.common.logger import PTLogger
from pitop.system import device_type

from . import check, update


def is_root() -> bool:
    return geteuid() == 0


def handle_exit_cases():
    if device_type() != "pi-top [4]":
        PTLogger.error("This program only runs on a pi-top [4]")
        exit(0)

    if not is_root():
        PTLogger.error(
            "This program requires root privileges. Run as root using 'sudo'."
        )
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
@click.option(
    "-t",
    "--wait-timeout",
    help="Amount of time (in seconds) to wait for web portal to report that firmware updates can start, excluding an OS (system packages) upgrade.",
    default=300,
    type=click.IntRange(0, 999),
)
@click.option(
    "-m",
    "--max-wait-timeout",
    help="Maximum time (in seconds) to wait for web portal to report that firmware updates can start, including an OS (system packages) upgrade.",
    default=3600,
    type=click.IntRange(0, 9999),
)
def do_check(force, loop_time, wait_timeout, max_wait_timeout):
    handle_exit_cases()
    PTLogger.setup_logging(logger_name="pt-firmware-updater")
    try:
        check.main(loop_time, wait_timeout, max_wait_timeout)
    except Exception as e:
        PTLogger.error(f"{e}")
        exit(1)


@click.command()
@click.option(
    "device",
    help="pi-top firmware device to apply firmware update to. "
    "Valid devices are {}".format(
        [dev.name for dev in FirmwareDevice.valid_device_ids()]
    ),
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
    help="Make update interactive by displaying desktop notifcations to the user",
    is_flag=True,
)
def do_update(device, force, interval, path, notify_user):
    handle_exit_cases()
    PTLogger.setup_logging(
        logger_name="pt-firmware-updater",
        log_to_journal=True,
    )
    try:
        update.main(device, force, interval, path, notify_user)
    except Exception as e:
        PTLogger.error(f"{e}")
        exit(1)


if __name__ == "__main__":
    do_check(prog_name="pt-firmware-updater")
