import logging
from time import sleep
from typing import Dict, List

from pitop.common.command_runner import run_command
from pitop.common.firmware_device import (
    FirmwareDevice,
    PTInvalidFirmwareDeviceException,
)
from pitop.common.lock import PTLock

from .utils import (
    default_firmware_folder,
    find_latest_firmware,
    i2c_addr_found,
    is_valid_fw_object,
    processed_firmware_files,
)

logger = logging.getLogger(__name__)

devices_notified_this_session: List[str] = list()
fw_device_cache: Dict[str, FirmwareDevice] = dict()


def already_notified_this_session(device_str: str) -> bool:
    return device_str in devices_notified_this_session


def run_firmware_updater(
    device_str: str, path_to_fw_object: str, force: bool = False
) -> None:
    FW_UPDATER_BINARY = "/usr/bin/pt-firmware-updater"
    command_str = f"{FW_UPDATER_BINARY} --path {path_to_fw_object} {'' if force else '--notify-user'} {device_str}"
    logger.info(f"Running command: {command_str}")
    run_command(command_str, timeout=None)
    devices_notified_this_session.append(device_str)


def check_and_update(device_enum, force=False):
    lock = PTLock(device_enum.name)
    if lock.is_locked():
        logger.warning(
            f"Already running an operation on {device_enum.name}... skipping"
        )
        return

    device_str = device_enum.name
    path_to_fw_folder = default_firmware_folder(device_str)

    fw_device = fw_device_cache.get(device_enum.name)
    if fw_device_cache.get(device_enum.name) is None:
        fw_device = FirmwareDevice(device_enum)
        fw_device_cache[device_str] = fw_device

    fw_file_object = find_latest_firmware(path_to_fw_folder, fw_device)
    if is_valid_fw_object(fw_file_object):
        run_firmware_updater(device_str, fw_file_object.path, force)


def main(force=False, loop_time=3) -> None:
    while True:
        for device_enum, device_info in FirmwareDevice.device_info.items():
            device_str = device_enum.name
            device_address = device_info.get("i2c_addr")

            if i2c_addr_found(device_address):
                if already_notified_this_session(device_str):
                    continue
                try:
                    check_and_update(device_enum, force)
                except PTInvalidFirmwareDeviceException as e:
                    # Probably just probing for the wrong device at the same address - nothing to worry about
                    logger.debug(f"{device_str} error: {e}")
                except Exception as e:
                    logger.warning(f"{device_str} error: {e}")
            else:
                if device_str in processed_firmware_files:
                    processed_firmware_files[device_str] = list()
                if device_str in devices_notified_this_session:
                    devices_notified_this_session.remove(device_str)
                if device_str in fw_device_cache:
                    processed_firmware_files[device_str] = list()

        if force:
            break
        logger.debug(f"Sleeping for {loop_time} secs before next check.")
        sleep(loop_time)
