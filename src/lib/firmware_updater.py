import re
import os
import shutil
import hashlib
from time import sleep
from distutils.version import StrictVersion

from ptcommon.common_ids import FirmwareDeviceID
from ptcommon.firmware_device import DeviceInfo, FirmwareDevice
from ptcommon.logger import PTLogger
from packet_manager import PacketManager, PacketType


class PTInvalidFirmwareFile(Exception):
    pass


class PTUpdatePending(Exception):
    pass


class FirmwareObject(object):
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
    def is_newer(reference: FirmwareDevice, candidate: FirmwareDevice):
        #############################################
        # TODO: (2) ONLY evaluate by using internal vars of this class
        #############################################
        if reference.error or candidate.error:
            return None

        PTLogger.info("{} - Firmware Versions: Current = {}, Candidate = {}".format(
            reference.device_name, candidate.firmware_version, fw_file.firmware_version)
        )

        if candidate.firmware_version > reference.firmware_version:
            PTLogger.info(
                "{} - Candidate firmware version is newer.".format(reference.device_name))
            return True
        elif candidate.firmware_version < reference.firmware_version:
            PTLogger.info(
                "{} - Candidate firmware version is not newer. Skipping...".format(reference.device_name))
            return False
        else:
            PTLogger.info(
                (
                    "{} - Candidate firmware version matches current firmware version. "
                    "Checking build metadata to determine if candidate is a newer build."
                ).format(reference.device_name)
            )

            if reference.is_release is not None:
                PTLogger.debug("{} - Reference firmware has 'is release build'".format(reference.device_name))
                # Assume all candidates have this
                if candidate.is_release and not reference.is_release:
                    PTLogger.info(
                        "{} - Candidate firmware version is release build, and current is not.".format(reference.device_name))
                    return True
            if reference.timestamp is not None:
                PTLogger.debug("{} - Reference firmware has 'timestamp'".format(reference.device_name))
                # Assume all candidates have this
                if reference.timestamp is not None and candidate.timestamp > reference.timestamp:
                    PTLogger.info(
                        "{} - Candidate firmware is newer build.".format(reference.device_name))
                    return True

        PTLogger.info(
            "{} - Candidate firmware is not newer. Skipping...".format(reference.device_name))
        return False


class FirmwareUpdater(object):
    fw_file_location = ""
    fw_file_hash = ""
    FW_SAFE_LOCATION = "/tmp/pt-firmware-updater/bin/"
    FW_INITIAL_LOCATION = "/lib/firmware/pi-top/"

    def __init__(self, fw_device: FirmwareDevice) -> None:
        self.device = fw_device
        self.device_info = FirmwareObject.from_device(self.device)
        self._packet = PacketManager()
        self.__processed_firmware_files = list()

    def has_staged_updates(self) -> bool:
        return os.path.isfile(self.fw_file_location) and \
            self.__read_hash_from_file(self.fw_file_location) == self.fw_file_hash

    def stage_file(self, fw_file: FirmwareObject) -> None:
        PTLogger.debug('{} - Verifying file {}'.format(self.device_info.device_name, fw_file.path))

        if self.fw_downloaded_successfully():
            raise PTUpdatePending("There's a binary uploaded to {} waiting to be installed".format(self.device_info.device_name))

        if not self.__firmware_file_is_valid(fw_file):
            raise PTInvalidFirmwareFile('{} is not a valid candidate firmware file'.format(fw_file.path))

        self.__prepare_firmware_for_install(fw_file)
        PTLogger.info("{} - {} is valid and was staged to be updated.".format(self.device_info.device_name, fw_file.path))

    def search_updates(self) -> None:
        path_to_fw_folder = os.path.join(self.FW_INITIAL_LOCATION, self.device_info.device_name)
        fw_file = self.__get_latest_fw_file_for_current_device(path_to_fw_folder)
        if fw_file is None or fw_file.error:
            return

        self.stage_file(fw_file)
        PTLogger.info("{} - Firmware update found: {}".format(self.device_info.device_name, fw_file.path))

    def install_updates(self) -> bool:
        self.__send_staged_firmware_to_device()

        time_wait_mcu = 0.1

        PTLogger.debug(
            "{} - Sleeping for {} secs before verifying update".format(self.device_info.device_name, time_wait_mcu))
        sleep(time_wait_mcu)  # Wait for MCU before verifying

        if self.fw_downloaded_successfully():
            PTLogger.info("{} - Successfully applied update.".format(self.device_info.device_name))
            return True
        PTLogger.error("{} - Failed to update.".format(self.device_info.device_name))
        return False

    def __send_staged_firmware_to_device(self) -> None:
        if not self.has_staged_updates():
            PTLogger.error("There isn't a firmware staged to be installed on")
            return

        if self.fw_file_hash != self.__read_hash_from_file(self.fw_file_location):
            PTLogger.error(
                "{} - Binary file didn't pass the sanity check."
                    .format(self.device_info.device_name))
            return

        self._packet.set_fw_file_to_install(self.fw_file_location)

        starting_packet = self._packet.create_packets(PacketType.StartingPacket)
        self.device.send_packet(DeviceInfo.FW__UPGRADE_START, starting_packet)

        fw_packets = self._packet.create_packets(PacketType.FwPackets)
        PTLogger.info('{} - Sending packages to device, please wait.'.format(self.device_info.device_name))
        for i in range(len(fw_packets)):
            packet = fw_packets[i]
            self.device.send_packet(DeviceInfo.FW__UPGRADE_PACKET, packet)

            if i == len(fw_packets) - 1:
                PTLogger.info("{} - Finished.".format(self.device_info.device_name))

    def fw_downloaded_successfully(self) -> bool:
        PTLogger.debug("Checking if device has previously loaded firmware ready to be installed")
        check_fw_packet = self.device.get_check_fw_okay()
        return self._packet.read_fw_download_verified_packet(check_fw_packet)

    def __candidate_fw_version_is_newer_than_current(self, fw_file: FirmwareObject):
        PTLogger.debug("Checking if candidate firmware version is newer than device")
        return FirmwareObject.is_newer(fw_file, self.device_info)

    def __firmware_file_is_valid(self, fw_file: FirmwareObject):
        verified = fw_file.verify(self.device_info.device_name, self.device_info.schematic_version)
        if not verified:
            return False

        newer = self.__candidate_fw_version_is_newer_than_current(fw_file)
        return newer

    def __get_latest_fw_file_for_current_device(self, fw_path: str) -> FirmwareObject:
        """
        Looks for the latest firmware version in a specified folder
        :param fw_path: path to the folder where the latest update
        will be searched
        :return: FirmwareObject representing the binary corresponding to the latest
        available version of the firmware.
        """

        PTLogger.debug("{} - Looking for binaries in: {}".format(self.device_info.device_name, fw_path))

        if not os.path.exists(fw_path):
            raise FileNotFoundError("Firmware path {} doesn't exist.".format(fw_path))

        candidate_latest_fw_file = None
        has_processed_new_fw_file = False
        with os.scandir(fw_path) as i:
            for entry in i:
                if entry.path in self.__processed_firmware_files:
                    continue
                has_processed_new_fw_file = True
                self.__processed_firmware_files.append(entry.path)

                fw_file = FirmwareObject.from_file(entry.path)
                if fw_file.verify(self.device_info.device_name, self.device_info.schematic_version):
                    if candidate_latest_fw_file is None or \
                            FirmwareObject.is_newer(fw_file, candidate_latest_fw_file):
                        candidate_latest_fw_file = fw_file

        if candidate_latest_fw_file is None:
            if has_processed_new_fw_file:
                PTLogger.warning("{} - No firmware found in folder: {}.".format(
                    self.device_info.device_name, fw_path)
                )
        else:
            PTLogger.debug("{} - Latest firmware available is version {}".format(
                self.device_info.device_name, candidate_latest_fw_file.firmware_version)
            )

        return candidate_latest_fw_file

    def __read_hash_from_file(self, filename: str) -> str:
        """
        Computes the MD5 hash of the given file
        :param filename: path to a file
        :return: MD5 hash
        """
        if not os.path.exists(filename):
            raise FileNotFoundError("Firmware path doesn't exist.")

        hash = hashlib.md5()
        with open(filename, "rb") as f:
            buff = f.read()
            hash.update(buff)
        return hash.hexdigest()

    def __prepare_firmware_for_install(self, fw_file: FirmwareObject) -> None:
        PTLogger.debug('{} - Preparing firmware for installation'.format(self.device_info.device_name))
        path_to_fw_file = os.path.abspath(fw_file.path)

        self.fw_file_hash = self.__read_hash_from_file(path_to_fw_file)

        _, fw_filename = os.path.split(path_to_fw_file)
        self.fw_file_location = os.path.join(
            self.FW_SAFE_LOCATION, self.device_info.device_name, fw_filename
        )

        if self.fw_file_location != path_to_fw_file:
            os.makedirs(os.path.dirname(self.fw_file_location), exist_ok=True)
            shutil.copyfile(path_to_fw_file, self.fw_file_location)
            PTLogger.debug('{} - File copied to {}'.format(self.device_info.device_name, self.fw_file_location))
