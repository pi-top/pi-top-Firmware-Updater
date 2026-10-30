#!/usr/bin/python3
import logging
import os
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from pitop.common.common_ids import FirmwareDeviceID
from pitop.common.firmware_device import (
    FirmwareDevice,
    PTInvalidFirmwareDeviceException,
)
from pitop.common.lock import PTLock

from .core.firmware_file_object import FirmwareFileObject
from .core.firmware_updater import (
    FirmwareUpdater,
    PTInvalidFirmwareFile,
    PTUpdatePending,
)
from .core.notification_manager import NotificationManager, UpdateStatusEnum
from .utils import (
    default_firmware_folder,
    find_latest_firmware,
    i2c_addr_found,
    is_valid_fw_object,
)

logger = logging.getLogger(__name__)


def get_device_data(device_str: str):
    id = FirmwareDevice.str_name_to_device_id(device_str)
    addr = FirmwareDevice.device_info[id]["i2c_addr"]
    return id, addr


def create_firmware_device(device_id: FirmwareDeviceID, interval: float):
    try:
        return FirmwareDevice(device_id, send_packet_interval=interval)
    except (ConnectionError, AttributeError) as e:
        logger.warning(
            "{} - Exception when attempting to create firmware device: {}".format(
                device_id.name, e
            )
        )
        raise
    except PTInvalidFirmwareDeviceException as e:
        # Probably just probing for the wrong device at the same address - nothing to worry about
        logger.debug(
            "{} - Invalid firmware device exception: {}".format(device_id.name, e)
        )
        raise
    except Exception as e:
        logger.error(
            "{} - Generic exception when attempting to create firmware device: {}".format(
                device_id.name, e
            )
        )
        raise


def create_fw_updater_object(device_id: FirmwareDeviceID, interval: float = 0.1):
    fw_device = create_firmware_device(device_id, interval)
    try:
        return FirmwareUpdater(fw_device)
    except (ConnectionError, AttributeError, PTInvalidFirmwareDeviceException) as e:
        logger.warning("Exception while checking for update: {}".format(e))
        raise
    except Exception as e:
        logger.error("Generic exception while checking for update: {}".format(e))
        raise


def stage_update(fw_updater: FirmwareUpdater, path_to_fw_file: str, force: bool):
    try:
        fw_file = FirmwareFileObject.from_file(path_to_fw_file)
        fw_updater.stage_file(fw_file, force)
    except PTInvalidFirmwareFile:
        logger.info("Skipping update: no valid candidate firmware")
        raise
    except PTUpdatePending as e:
        logger.info("Skipping update: {}".format(e))
        raise


def apply_update(
    fw_updater: FirmwareUpdater, on_progress: Optional[Callable]
) -> Tuple[bool, bool]:
    try:
        if fw_updater.has_staged_updates():
            return fw_updater.install_updates(on_progress)
    except (ConnectionError, AttributeError, PTInvalidFirmwareDeviceException) as e:
        logger.warning(f"Exception while trying to update: {e}")
        raise
    except Exception as e:
        logger.error(f"Generic exception while trying to update: {e}")
        raise
    return True, False


@dataclass
class FwUpdateResult:
    device: str
    success: bool
    requires_reboot: bool = False
    error: bool = False


def notify(
    notification_manager: NotificationManager,
    device_id: int,
    notification_enum: UpdateStatusEnum,
) -> bool:
    if notification_enum == UpdateStatusEnum.PROMPT:
        user_response = notification_manager.notify_user(
            UpdateStatusEnum.PROMPT, device_id
        )
        logger.info(f"User response: {user_response}")
        if "OK" not in user_response:
            logger.info("User declined upgrade... exiting")
            return False
        notification_manager.notify_user(UpdateStatusEnum.ONGOING, device_id)
        return True

    notification_manager.notify_user(notification_enum, device_id)
    return False


def get_path_to_binary(device: str, path: str = "") -> str:
    if path == "":
        logger.info("No path specified - finding latest...")

        fw_file_object = find_latest_firmware(
            default_firmware_folder(device),
            FirmwareDevice(FirmwareDevice.str_name_to_device_id(device)),
        )

        if not is_valid_fw_object(fw_file_object):
            raise PTInvalidFirmwareFile("No valid firmware object found")

        path = fw_file_object.path

    if not os.path.isfile(path):
        raise ValueError(f"{path} isn't a valid file.")

    return path


def is_updatable(device: str) -> bool:
    try:
        # Check if there's a binary available
        get_path_to_binary(device)

        # Check if the device is connected
        device_id, device_addr = get_device_data(device)
        if not i2c_addr_found(device_addr):
            raise ConnectionError(f"Device {device} not detected")

        # Check if we can create a firmware updater object
        create_fw_updater_object(device_id)

        return True
    except Exception:
        return False


def main(
    device,
    force,
    interval=0.1,
    path="",
    notify_user=True,
    on_progress: Optional[Callable] = None,
) -> FwUpdateResult:
    path = get_path_to_binary(device, path)

    device_id, device_addr = get_device_data(device)
    if not i2c_addr_found(device_addr):
        raise ConnectionError(f"Device {device} not detected")

    fw_updater = create_fw_updater_object(device_id, interval)
    stage_update(fw_updater, path, force)

    if notify_user:
        notification_manager = NotificationManager()
        if not notify(notification_manager, device_id, UpdateStatusEnum.PROMPT):
            return FwUpdateResult(
                device=device,
                success=False,
                requires_reboot=False,
                error=False,
            )

    lock_file = PTLock(device)
    with lock_file:
        success, requires_restart = apply_update(fw_updater, on_progress)

    if success:
        logger.info("Operation finished successfully")
        if requires_restart and device_id == FirmwareDeviceID.pt4_hub:
            logger.info(
                "Run '"
                "touch /tmp/.com.pi-top.pi-topd.pt-poweroff.reboot-on-shutdown && sudo shutdown -h now"
                "' to perform a full system restart and apply changes"
            )
        else:
            logger.info("Disconnect and reconnect your device to apply changes")
    else:
        logger.error(
            "A problem was encountered while attempting to upgrade. Please reboot and try again"
        )

    if notify_user:
        status = UpdateStatusEnum.SUCCESS if success else UpdateStatusEnum.FAILURE
        if success and requires_restart:
            status = UpdateStatusEnum.SUCCESS_REQUIRES_RESTART
        notify(notification_manager, device_id, status)

    return FwUpdateResult(
        device=device, success=success, requires_reboot=requires_restart
    )
