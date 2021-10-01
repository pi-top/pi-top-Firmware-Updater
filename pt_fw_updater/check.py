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

from .utils import (
    default_firmware_folder,
    find_latest_firmware,
    i2c_addr_found,
    is_valid_fw_object,
    processed_firmware_files,
)

devices_notified_this_session: List[str] = list()
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


def already_notified_this_session(device_str: str) -> bool:
    return device_str in devices_notified_this_session


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

    while True:
        for device_enum, device_info in FirmwareDevice.device_info.items():
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
