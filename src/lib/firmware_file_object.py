import re
import os
from distutils.version import StrictVersion

from ptcommon.common_ids import FirmwareDeviceID
from ptcommon.firmware_device import FirmwareDevice
from ptcommon.logger import PTLogger


class FirmwareFileObject(object):
    def __init__(self,
                 path: str,
                 error: bool,
                 error_string: str,
                 device_name: str,
                 firmware_version: StrictVersion,
                 schematic_version: int,
                 is_release: bool,
                 timestamp: int = None
                 ):
        self.path = path
        self.error = error
        self.error_string = error_string
        self.device_name = device_name
        self.firmware_version = firmware_version
        self.schematic_version = schematic_version
        self.is_release = is_release
        self.timestamp = timestamp

    @classmethod
    def from_file(cls, path_to_file):
        path = path_to_file

        error = True  # Until we have parsed
        error_string = "Uninitialised"

        device_name = None
        firmware_version = None
        schematic_version = None
        is_release = None
        timestamp = None

        if not os.path.isfile(path):
            error_string = "No file found"
            return cls(
                path,
                error,
                error_string,
                device_name,
                firmware_version,
                schematic_version,
                is_release,
                timestamp
            )

        if not path.endswith(".bin"):
            error_string = "Not a .bin file"
            return cls(
                path,
                error,
                error_string,
                device_name,
                firmware_version,
                schematic_version,
                is_release,
                timestamp
            )

        _, fw_filename = os.path.split(path)

        # e.g. 'pt4_expansion_plate-v21.1-sch2-release.bin'
        filename_fields = fw_filename.replace(".bin", "").split('-')

        if len(filename_fields) < 4:
            error_string = "Less than 4 dash-separated fields in filename"
            return cls(
                path,
                error,
                error_string,
                device_name,
                firmware_version,
                schematic_version,
                is_release,
                timestamp
            )

        # e.g. 'pt4_expansion_plate'
        device_name = filename_fields[0]
        if device_name not in FirmwareDeviceID._member_names_:
            error_string = "Invalid device name string: {}".format(device_name)
            return cls(
                path,
                error,
                error_string,
                device_name,
                firmware_version,
                schematic_version,
                is_release,
                timestamp
            )

        # e.g. 'v21.1'
        version_str = filename_fields[1].replace("v", "")
        if not re.search(r"^\d+.\d+$", version_str):
            error_string = "Invalid firmware version string: {}".format(version_str.replace("v", ""))
            return cls(
                path,
                error,
                error_string,
                device_name,
                firmware_version,
                schematic_version,
                is_release,
                timestamp
            )

        # e.g. 'sch2'
        schematic_version_str = filename_fields[2].replace("sch", "")
        if not str.isdigit(schematic_version_str):
            error_string = "Invalid schematic version string: {}".format(schematic_version_str.replace("sch", ""))
            return cls(
                path,
                error,
                error_string,
                device_name,
                firmware_version,
                schematic_version,
                is_release,
                timestamp
            )

        # e.g. 'preview'
        release_type_str = filename_fields[3]
        if release_type_str != "release" and release_type_str != "preview":
            error_string = "Invalid release type string: {}".format(release_type_str)
            return cls(
                path,
                error,
                error_string,
                device_name,
                firmware_version,
                schematic_version,
                is_release,
                timestamp
            )

        # e.g. '1591708039'
        timestamp = None
        if len(filename_fields) >= 5:
            timestamp = filename_fields[4]
            if not str.isdigit(timestamp):
                error_string = "Invalid timestamp string: {}".format(timestamp)
                return cls(
                    path,
                    error,
                    error_string,
                    device_name,
                    firmware_version,
                    schematic_version,
                    is_release,
                    timestamp
                )

        firmware_version = StrictVersion(version_str)
        schematic_version = int(schematic_version_str)
        is_release = (release_type_str == "release")

        error_string = ""
        error = False

        return cls(
            path,
            error,
            error_string,
            device_name,
            firmware_version,
            schematic_version,
            is_release,
            timestamp
        )

    @classmethod
    def from_device(cls, device_object):
        path = None
        error = False
        error_string = ""
        device_name = device_object.str_name
        firmware_version = StrictVersion(device_object.get_fw_version())
        schematic_version = device_object.get_sch_hardware_version_major()
        is_release = None
        timestamp = None
        if device_object.has_extended_build_info():
            is_release = device_object.get_is_release_build()
            timestamp = device_object.get_raw_build_timestamp()

        return cls(
            path,
            error,
            error_string,
            device_name,
            firmware_version,
            schematic_version,
            is_release,
            timestamp
        )

    def verify(self, device_name, schematic_board_rev) -> bool:
        if self.error:
            PTLogger.error(
                (
                    "{} - Invalid format for firmware file {}: {}. Skipping..."
                ).format(device_name, self.path, self.error_string)
            )
            return False

        if self.device_name != device_name:
            PTLogger.warning(
                (
                    "{} - Firmware file '{}' device name does not match current device '{}'. Skipping..."
                ).format(device_name, self.path, device_name)
            )
            return False

        if self.schematic_version != schematic_board_rev:
            PTLogger.warning(
                (
                    "{} - Firmware file '{}' schematic version '{}' does not match current device '{}'. Skipping..."
                ).format(device_name, self.path, self.schematic_version, schematic_board_rev)
            )
            return False

        PTLogger.debug("{} - {} has a valid version ({})".format(device_name, self.path, self.firmware_version))
        return True

    @staticmethod
    def is_newer(reference: FirmwareDevice, candidate: FirmwareDevice, quiet: bool = False):
        if reference is None or candidate is None:
            return False
        if reference.error or candidate.error:
            return None

        if not quiet:
            PTLogger.info("{} - Firmware Versions: Current = {}, Candidate = {}".format(
                reference.device_name, reference.firmware_version, candidate.firmware_version)
            )

        if candidate.firmware_version > reference.firmware_version:
            if not quiet:
                PTLogger.info(
                    "{} - Candidate firmware version is newer.".format(reference.device_name))
            return True
        elif candidate.firmware_version < reference.firmware_version:
            if not quiet:
                PTLogger.info(
                    "{} - Candidate firmware version is not newer. Skipping...".format(reference.device_name))
            return False
        else:
            if not quiet:
                PTLogger.info(
                    (
                        "{} - Candidate firmware version matches current firmware version. "
                        "Checking build metadata to determine if candidate is a newer build."
                    ).format(reference.device_name)
                )

            if reference.is_release is not None:
                if not quiet:
                    PTLogger.info("{} - Reference firmware has 'is release build' property".format(reference.device_name))
                # Assume all candidates have this
                if candidate.is_release and not reference.is_release:
                    if not quiet:
                        PTLogger.info(
                            "{} - Candidate firmware version is release build, and current is not.".format(reference.device_name))
                    return True
            if reference.timestamp is not None and candidate.timestamp is not None:
                if not quiet:
                    PTLogger.info("{} - Both reference and candidate firmware has 'timestamp' property".format(reference.device_name))
                if candidate.timestamp > reference.timestamp:
                    if not quiet:
                        PTLogger.info(
                            "{} - Candidate firmware is newer build.".format(reference.device_name))
                    return True

        if not quiet:
            PTLogger.info(
                "{} - Candidate firmware is not newer. Skipping...".format(reference.device_name))
        return False
