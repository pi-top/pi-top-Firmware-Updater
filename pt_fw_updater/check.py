import os
from pathlib import Path
from subprocess import getoutput
from time import sleep
from typing import Dict, List

from pitop.common.command_runner import run_command
from pitop.common.firmware_device import (
    FirmwareDevice,
    PTInvalidFirmwareDeviceException,
)
from pitop.common.lock import PTLock
from pitop.common.logger import PTLogger

from .core.firmware_file_object import FirmwareFileObject

devices_notified_this_session: List[str] = list()
processed_firmware_files: Dict[str, List[str]] = dict()
fw_device_cache: Dict[str, FirmwareDevice] = dict()


def wait_for_pt_web_portal_if_required(
    wait_timeout: int, max_wait_timeout: int
) -> None:
    web_portal_is_active = getoutput("systemctl is-active pt-os-web-portal") == "active"
    web_portal_is_enabled = (
        getoutput("systemctl is-enabled pt-os-web-portal") == "enabled"
    )
    wait_for_web_portal = web_portal_is_active or web_portal_is_enabled
    PTLogger.info("pt-os-web-portal is active? {}".format(web_portal_is_active))
    PTLogger.info("pt-os-web-portal is enabled? {}".format(web_portal_is_enabled))
    PTLogger.info(
        "Wait for pt-os-web-portal to report that it is ready to start a firmware update? {}".format(
            wait_for_web_portal
        )
    )

    if not wait_for_web_portal:
        PTLogger.info("Nothing to wait for - continuing...")
        return

    PTLogger.info("Waiting {} seconds.".format(wait_timeout))
    ready_breadcrumb = Path(
        "/tmp/.com.pi-top.pt-os-web-portal.pt-firmware-updater.ready"
    )
    extend_timeout_breadcrumb = Path(
        "/tmp/.com.pi-top.pt-os-web-portal.pt-firmware-updater.extend-timeout"
    )
    wait_time = 0
    was_using_extended_timeout = extend_timeout_breadcrumb.is_file()

    # Wait no longer than max wait time
    while wait_time <= max_wait_timeout:
        is_using_extended_timeout = extend_timeout_breadcrumb.is_file()

        if is_using_extended_timeout and not was_using_extended_timeout:
            PTLogger.info(
                "Extending timeout - using 'max-wait-timeout', not 'wait-timeout'"
            )

        if wait_time <= wait_timeout or is_using_extended_timeout:
            PTLogger.debug("Wait time: {}s/{}s".format(wait_time, max_wait_timeout))
            if ready_breadcrumb.is_file():
                PTLogger.info("Found 'ready' breadcrumb")
                break
        else:
            PTLogger.info("Wait time expired, and have not been told to extend timeout")
            break

        was_using_extended_timeout = is_using_extended_timeout
        wait_time += 1
        sleep(1)

    if ready_breadcrumb.is_file():
        PTLogger.info(
            "pt-os-web-portal has reported that it is ready for pi-top firmware checks. Wait time: {}s/{}s".format(
                wait_time, wait_timeout
            )
        )
        PTLogger.info("Reason: {}".format(ready_breadcrumb.read_text()))
    else:
        PTLogger.info(
            "pt-os-web-portal did not report that it is ready for pi-top firmware checks - timed out."
        )


def get_pi_top_fw_devices() -> dict:
    return FirmwareDevice.device_info


def i2c_addr_found(device_address: int) -> bool:
    try:
        run_command(
            f"i2cping {device_address}", timeout=1, check=True, log_errors=False
        )
        is_connected = True
    except Exception:
        is_connected = False
    return is_connected


def already_notified_this_session(device_str: str) -> bool:
    return device_str in devices_notified_this_session


def already_processed_file(file_path: str, device_str: str) -> bool:
    processed_files = processed_firmware_files.get(device_str)
    if processed_files is None:
        processed_firmware_files[device_str] = list()
    elif file_path in processed_files:
        return True
    processed_firmware_files[device_str].append(file_path)
    return False


def default_firmware_folder(device_str: str) -> str:
    DEFAULT_FIRMWARE_FOLDER_BASE = "/lib/firmware/pi-top/"
    return DEFAULT_FIRMWARE_FOLDER_BASE + device_str


def find_latest_firmware(
    path_to_fw_folder: str, firmware_device: FirmwareDevice
) -> str:
    if not os.path.exists(path_to_fw_folder):
        raise FileNotFoundError(
            "Firmware path {} doesn't exist.".format(path_to_fw_folder)
        )

    firmware_object = FirmwareFileObject.from_device(firmware_device)

    candidate_latest_fw_object = None
    with os.scandir(path_to_fw_folder) as i:
        for entry in i:
            if already_processed_file(entry.path, firmware_device.str_name):
                continue
            fw_object = FirmwareFileObject.from_file(entry.path)
            if fw_object.verify(
                firmware_object.device_name, firmware_object.schematic_version
            ):
                if candidate_latest_fw_object is None or FirmwareFileObject.is_newer(
                    candidate_latest_fw_object, fw_object, quiet=True
                ):
                    candidate_latest_fw_object = fw_object
                    PTLogger.debug(
                        f"Current latest firmware available is version {candidate_latest_fw_object.firmware_version}"
                    )

    if candidate_latest_fw_object:
        PTLogger.info(
            f"Latest firmware available is version {candidate_latest_fw_object.firmware_version}"
        )
    return candidate_latest_fw_object


def is_valid_fw_object(fw_file_object: FirmwareFileObject) -> bool:
    return not (fw_file_object is None or fw_file_object.error)


def run_firmware_updater(device_str: str, path_to_fw_object: str) -> None:
    FW_UPDATER_BINARY = "/usr/bin/pt-firmware-updater"
    command_str = (
        f"{FW_UPDATER_BINARY} --path {path_to_fw_object} --notify-user {device_str}"
    )
    PTLogger.info(f"Running command: {command_str}")
    run_command(command_str, timeout=None)
    devices_notified_this_session.append(device_str)


def check_and_update(device_enum):
    lock = PTLock(device_enum.name)
    if lock.is_locked():
        PTLogger.warning(
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
        run_firmware_updater(device_str, fw_file_object.path)


def main(force, loop_time, wait_timeout, max_wait_timeout) -> None:
    if not force:
        wait_for_pt_web_portal_if_required(wait_timeout, max_wait_timeout)

    pi_top_fw_devices_data = get_pi_top_fw_devices()
    while True:
        for device_enum, device_info in pi_top_fw_devices_data.items():
            device_str = device_enum.name
            device_address = device_info.get("i2c_addr")

            if i2c_addr_found(device_address):
                if already_notified_this_session(device_str):
                    continue
                try:
                    check_and_update(device_enum)
                except PTInvalidFirmwareDeviceException as e:
                    # Probably just probing for the wrong device at the same address - nothing to worry about
                    PTLogger.debug(f"{device_str} error: {e}")
                except Exception as e:
                    PTLogger.warning(f"{device_str} error: {e}")
            else:
                if device_str in processed_firmware_files:
                    processed_firmware_files[device_str] = list()
                if device_str in devices_notified_this_session:
                    devices_notified_this_session.remove(device_str)
                if device_str in fw_device_cache:
                    processed_firmware_files[device_str] = list()

        PTLogger.debug("Sleeping for {} secs before next check.".format(loop_time))
        sleep(loop_time)
