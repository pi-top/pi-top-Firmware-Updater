import os
from typing import Dict, List

from pitop.common.command_runner import run_command
from pitop.common.firmware_device import FirmwareDevice
from pitop.common.logger import PTLogger

from .core.firmware_file_object import FirmwareFileObject

processed_firmware_files: Dict[str, List[str]] = dict()


def default_firmware_folder(device_str: str) -> str:
    DEFAULT_FIRMWARE_FOLDER_BASE = "/lib/firmware/pi-top/"
    return DEFAULT_FIRMWARE_FOLDER_BASE + device_str


def i2c_addr_found(device_address: int) -> bool:
    try:
        run_command(
            f"i2cping {device_address}", timeout=1, check=True, log_errors=False
        )
        is_connected = True
    except Exception:
        is_connected = False
    return is_connected


def find_latest_firmware(
    path_to_fw_folder: str, firmware_device: FirmwareDevice
) -> FirmwareFileObject:
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


def already_processed_file(file_path: str, device_str: str) -> bool:
    processed_files = processed_firmware_files.get(device_str)
    if processed_files is None:
        processed_firmware_files[device_str] = list()
    elif file_path in processed_files:
        return True
    processed_firmware_files[device_str].append(file_path)
    return False
