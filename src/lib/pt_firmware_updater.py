#!/usr/bin/python3
import os
from typing import Tuple

from pitop.utils.command_runner import run_command
from pitop.utils.common_ids import FirmwareDeviceID
from pitop.utils.firmware_device import PTInvalidFirmwareDeviceException
from pitop.utils.firmware_device import FirmwareDevice
from pitop.utils.lock import PTLock
from pitop.utils.logger import PTLogger

from core.firmware_file_object import FirmwareFileObject
from core.firmware_updater import FirmwareUpdater, PTInvalidFirmwareFile, PTUpdatePending
from core.notification_manager import NotificationManager, UpdateStatusEnum


def i2c_addr_found(device_address: int) -> bool:
    try:
        run_command(f"pt-i2cdetect {device_address}", timeout=1, check=True)
        is_connected = True
    except:
        is_connected = False
    return is_connected


def get_device_data(device_str: str):
    id = FirmwareDevice.str_name_to_device_id(device_str)
    addr = FirmwareDevice.device_info[id]['i2c_addr']
    return id, addr


def create_firmware_device(device_id: FirmwareDeviceID):
    try:
        return FirmwareDevice(device_id)
    except (ConnectionError, AttributeError) as e:
        PTLogger.warning('{} - Exception when attempting to create firmware device: {}'.format(device_id.name, e))
        raise
    except PTInvalidFirmwareDeviceException as e:
        # Probably just probing for the wrong device at the same address - nothing to worry about
        PTLogger.debug('{} - Invalid firmware device exception: {}'.format(device_id.name, e))
        raise
    except Exception as e:
        PTLogger.error('{} - Generic exception when attempting to create firmware device: {}'.format(device_id.name, e))
        raise


def create_fw_updater_object(device_id: FirmwareDeviceID):
    fw_device = create_firmware_device(device_id)
    try:
        return FirmwareUpdater(fw_device)
    except (ConnectionError, AttributeError, PTInvalidFirmwareDeviceException) as e:
        PTLogger.warning('Exception while checking for update: {}'.format(e))
        raise
    except Exception as e:
        PTLogger.error('Generic exception while checking for update: {}'.format(e))
        raise


def stage_update(fw_updater: FirmwareUpdater, path_to_fw_file: str, force: bool):
    try:
        fw_file = FirmwareFileObject.from_file(path_to_fw_file)
        fw_updater.stage_file(fw_file, force)
    except PTInvalidFirmwareFile as e:
        PTLogger.info('Skipping update: no valid candidate firmware')
        raise
    except PTUpdatePending as e:
        PTLogger.info('Skipping update: {}'.format(e))
        raise


def apply_update(fw_updater: FirmwareUpdater) -> Tuple:
    try:
        if fw_updater.has_staged_updates():
            return fw_updater.install_updates()
    except (ConnectionError, AttributeError, PTInvalidFirmwareDeviceException) as e:
        PTLogger.warning('Exception while trying to update: {}'.format(e))
        raise
    except Exception as e:
        PTLogger.error('Generic exception while trying to update: {}'.format(e))
        raise


def main(parsed_args) -> None:
    PTLogger.setup_logging(logger_name="pt-firmware-updater",
                           logging_level=parsed_args.log_level, log_to_journal=parsed_args.no_journal is False)
    PTLogger.debug("Starting pt-firmware-updater")

    if not os.path.isfile(parsed_args.path):
        raise ValueError(f"{parsed_args.path} isn't a valid file.")

    device_id, device_addr = get_device_data(parsed_args.device)
    if not i2c_addr_found(device_addr):
        raise ConnectionError(f"Device {parsed_args.device} not detected")

    fw_updater = create_fw_updater_object(device_id)
    stage_update(fw_updater, parsed_args.path, parsed_args.force)

    if parsed_args.notify_user:
        notification_manager = NotificationManager()
        user_response = notification_manager.notify_user(UpdateStatusEnum.PROMPT, device_id)
        if "OK" not in user_response:
            PTLogger.info("User declined upgrade... exiting")
            return
        notification_manager.notify_user(UpdateStatusEnum.ONGOING, device_id)

    lock_file = PTLock(parsed_args.device)
    with lock_file:
        success, requires_restart = apply_update(fw_updater)

    if success:
        PTLogger.info(f"Operation finished successfully")
        if requires_restart and device_id == FirmwareDeviceID.pt4_hub:
            PTLogger.info(f"Restart your pi-top to apply changes")
        else:
            PTLogger.info(f"Disconnect and reconnect your device to apply changes")
    else:
        PTLogger.error(f"A problem was encountered while attempting to upgrade. Please reboot and try again")

    if parsed_args.notify_user:
        status = UpdateStatusEnum.FAILURE
        if success and requires_restart:
            status = UpdateStatusEnum.SUCCESS_REQUIRES_RESTART
        elif success:
            status = UpdateStatusEnum.SUCCESS
        notification_manager.notify_user(status, device_id)
