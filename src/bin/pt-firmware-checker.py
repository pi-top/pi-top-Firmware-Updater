#!/usr/bin/python3

import os
from argparse import ArgumentParser
from sys import exit
from sys import path
from time import sleep

from ptcommon.common_ids import DeviceID
from ptcommon.firmware_device import FirmwareDevice
from ptcommon.logger import PTLogger
from ptcommon.sys_info import get_host_device_version
path.append("/usr/lib/pt-firmware-updater/")
from notification_manager import NotificationManager, UpdateStatusEnum
from firmware_device_manager import FirmwareDeviceManager


parser = ArgumentParser(description="pi-top firmware update checker")
parser.add_argument(
    "-a",
    "--all",
    action="store_true",
    help="Find all connected pi-top devices, and apply firmware upgrades "
         "if necessary",
)
parser.add_argument(
    "--no-journal",
    help="Prints output to stdout instead of journal.",
    action="store_true"
)
parser.add_argument(
    "--log-level",
    type=int,
    help="Set the logging level from 10 (more verbose) to 50 (less verbose).",
    default=20,
)
parser.add_argument(
    "--loop-time",
    type=float,
    help="Sets the time interval in seconds that the script will wait before each update check.",
    default=3
)


def is_root() -> bool:
    return os.geteuid() == 0


def main() -> None:
    args = parser.parse_args()
    PTLogger.setup_logging(
        "pt-firmware-updater",
        args.log_level,
        args.no_journal is False)

    if get_host_device_version() != DeviceID.pi_top_4.name:
        PTLogger.error("This program only runs on a pi-top[4]")
        exit(1)

    if not is_root():
        PTLogger.error(
            "This program requires root privileges. Run as root using 'sudo'.")
        exit(1)

    devices = FirmwareDevice.valid_device_ids()

    fw_device_manager = FirmwareDeviceManager(devices)
    fw_device_manager.force_update_if_available()
    fw_device_manager.start_file_supervisor()

    notification_manager = NotificationManager()
    while True:
        fw_device_manager.scan()

        for device_id in fw_device_manager.connected_devices():
            if fw_device_manager.was_notified(device_id):
                PTLogger.info("{} - User already notified for updates. Skipping...".format(device_id))
                continue

            if fw_device_manager.has_update(device_id):
                # notify user about update
                path_to_binary = fw_device_manager.path_to_binary(device_id)
                notification_manager.notify_user(UpdateStatusEnum.WARNING, device_id, path_to_binary)
                fw_device_manager.set_notification_status(device_id, True)

        if fw_device_manager.new_files_in_folder():
            PTLogger.info('New binary files found. Will notify the user.')

        if args.loop_time < 0:
            break
        PTLogger.info('Sleeping for {} secs before next check.'.format(args.loop_time))
        sleep(args.loop_time)


if __name__ == '__main__':
    main()
