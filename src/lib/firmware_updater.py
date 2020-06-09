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
    def __init__(self, path_to_file=None):
        self.path = path_to_file

        self.error = True  # Until we have parsed
        self.error_string = "Uninitialised"

        self.device_name = None
        self.firmware_version = None
        self.schematic_version = None
        self.is_release = None
        self.timestamp = None

        if not os.path.isfile(path_to_file):
            self.error_string = "No file found"
            return

        if not path_to_file.endswith(".bin"):
            self.error_string = "Not a .bin file"
            return

        _, fw_filename = os.path.split(path_to_file)

        # e.g. 'pt4_expansion_plate-v21.1-sch2-release.bin'
        filename_fields = fw_filename.replace(".bin", "").split('-')

        if len(filename_fields) < 4:
            self.error_string = "Less than 4 dash-separated fields in filename"
            return

        # e.g. 'pt4_expansion_plate'
        device_name = filename_fields[0]
        if device_name not in FirmwareDeviceID._member_names_:
            self.error_string = "Invalid device name string: {}".format(device_name)
            return

        # e.g. 'v21.1'
        version_str = filename_fields[1].replace("v", "")
        if not re.search(r"^\d+.\d+$", version_str):
            self.error_string = "Invalid firmware version string: {}".format(version_str.replace("v", ""))
            return

        # e.g. 'sch2'
        schematic_version_str = filename_fields[2].replace("sch", "")
        if not str.isdigit(schematic_version_str):
            self.error_string = "Invalid schematic version string: {}".format(schematic_version_str.replace("sch", ""))
            return

        # e.g. 'preview'
        release_type_str = filename_fields[3]
        if release_type_str != "release" and release_type_str != "preview":
            self.error_string = "Invalid release type string: {}".format(release_type_str)
            return

        # e.g. '1591708039'
        timestamp = None
        if len(filename_fields) >= 5:
            timestamp = filename_fields[4]
            if not str.isdigit(timestamp):
                self.error_string = "Invalid timestamp string: {}".format(timestamp)
                return

        # Only set parameters at the end, so that they can't be used by accident
        self.device_name = device_name
        self.firmware_version = StrictVersion(version_str)
        self.schematic_version = int(schematic_version_str)
        self.is_release = (release_type_str == "release")
        self.timestamp = timestamp

        # Clear error state
        self.error_string = ""
        self.error = False

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


class FirmwareUpdater(object):
    fw_file_location = ""
    fw_file_hash = ""
    FW_SAFE_LOCATION = "/tmp/pt-firmware-updater/bin/"
    FW_INITIAL_LOCATION = "/lib/firmware/pi-top/"

    def __init__(self, fw_device: FirmwareDevice) -> None:
        self.device = fw_device
        self._packet = PacketManager()
        self.schematic_board_rev = self.device.get_sch_hardware_version_major()
        self.__processed_firmware_files = list()

    def has_staged_updates(self) -> bool:
        return os.path.isfile(self.fw_file_location) and \
            self.__read_hash_from_file(self.fw_file_location) == self.fw_file_hash

    def stage_file(self, fw_file: FirmwareObject) -> None:
        PTLogger.debug('{} - Verifying file {}'.format(self.device.str_name, fw_file.path))

        if self.fw_downloaded_successfully():
            raise PTUpdatePending("There's a binary uploaded to {} waiting to be installed".format(self.device.str_name))

        if not self.__firmware_file_is_valid(fw_file):
            raise PTInvalidFirmwareFile('{} is not a valid candidate firmware file'.format(fw_file.path))

        self.__prepare_firmware_for_install(fw_file)
        PTLogger.info("{} - {} is valid and was staged to be updated.".format(self.device.str_name, fw_file.path))

    def search_updates(self) -> None:
        path_to_fw_folder = os.path.join(self.FW_INITIAL_LOCATION, self.device.str_name)
        fw_file = self.__get_latest_fw_file_for_current_device(path_to_fw_folder)
        if fw_file.error:
            return

        self.stage_file(fw_file)
        PTLogger.info("{} - Firmware update found: {}".format(self.device.str_name, fw_file.path))

    def install_updates(self) -> bool:
        self.__send_staged_firmware_to_device()

        time_wait_mcu = 0.1

        PTLogger.debug(
            "{} - Sleeping for {} secs before verifying update".format(self.device.str_name, time_wait_mcu))
        sleep(time_wait_mcu)  # Wait for MCU before verifying

        if self.fw_downloaded_successfully():
            PTLogger.info("{} - Successfully applied update.".format(self.device.str_name))
            return True
        PTLogger.error("{} - Failed to update.".format(self.device.str_name))
        return False

    def __send_staged_firmware_to_device(self) -> None:
        if not self.has_staged_updates():
            PTLogger.error("There isn't a firmware staged to be installed on")
            return

        if self.fw_file_hash != self.__read_hash_from_file(self.fw_file_location):
            PTLogger.error(
                "{} - Binary file didn't pass the sanity check."
                    .format(self.device.str_name))
            return

        self._packet.set_fw_file_to_install(self.fw_file_location)

        starting_packet = self._packet.create_packets(PacketType.StartingPacket)
        self.device.send_packet(DeviceInfo.FW__UPGRADE_START, starting_packet)

        fw_packets = self._packet.create_packets(PacketType.FwPackets)
        PTLogger.info('{} - Sending packages to device, please wait.'.format(self.device.str_name))
        for i in range(len(fw_packets)):
            packet = fw_packets[i]
            self.device.send_packet(DeviceInfo.FW__UPGRADE_PACKET, packet)

            if i == len(fw_packets) - 1:
                PTLogger.info("{} - Finished.".format(self.device.str_name))

    def fw_downloaded_successfully(self) -> bool:
        PTLogger.debug("Checking if device has previously loaded firmware ready to be installed")
        check_fw_packet = self.device.get_check_fw_okay()
        return self._packet.read_fw_download_verified_packet(check_fw_packet)

    def __candidate_fw_version_is_newer_than_current(self, fw_file: FirmwareObject):
        PTLogger.debug("Getting firmware version information from device")
        current_fw_version = StrictVersion(self.device.get_fw_version())

        PTLogger.info("{} - Firmware Versions: Current = {}, Candidate = {}".format(self.device.str_name, current_fw_version, fw_file.firmware_version))

        if fw_file.firmware_version > current_fw_version:
            PTLogger.info(
                "{} - Candidate firmware version is newer.".format(self.device.str_name))
            return True
        elif fw_file.firmware_version < current_fw_version:
            PTLogger.info(
                "{} - Candidate firmware version is not newer. Skipping...".format(self.device.str_name))
            return False
        elif self.device.has_extended_build_info():
            PTLogger.info(
                (
                    "{} - Candidate firmware version matches current firmware version. "
                    "Checking build metadata to determine if candidate is a newer build."
                ).format(self.device.str_name)
            )

            current_fw_is_release_build = self.device.get_is_release_build()
            current_fw_build_timestamp = self.device.get_build_timestamp()

            if fw_file.is_release and not current_fw_is_release_build:
                PTLogger.info(
                    "{} - Candidate firmware version is release build, and current is not.".format(self.device.str_name))
                return True

            if fw_file.timestamp is not None and fw_file.timestamp > current_fw_build_timestamp:
                PTLogger.info(
                    "{} - Candidate firmware is newer build.".format(self.device.str_name))
                return True

        PTLogger.info(
            "{} - Candidate firmware is not newer. Skipping...".format(self.device.str_name))
        return False

    def __firmware_file_is_valid(self, fw_file: FirmwareObject):
        verified = fw_file.verify(self.device.str_name, self.schematic_board_rev)
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

        PTLogger.debug("{} - Looking for binaries in: {}".format(self.device.str_name, fw_path))

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

                fw_file = FirmwareObject(path_to_file=entry.path)
                if fw_file.verify(self.device.str_name, self.schematic_board_rev):

                    if candidate_latest_fw_file is None or \
                        fw_file.firmware_version >= \
                            candidate_latest_fw_file.firmware_version:
                        candidate_latest_fw_file = fw_file

        if candidate_latest_fw_file is None:
            if has_processed_new_fw_file:
                PTLogger.warning("{} - No firmware found in folder: {}.".format(self.device.str_name, fw_path))
            candidate_latest_fw_file = ""
        else:
            PTLogger.debug("{} - Latest firmware available is version {}".format(self.device.str_name, candidate_latest_fw_file.firmware_version))

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
        PTLogger.debug('{} - Preparing firmware for installation'.format(self.device.str_name))
        path_to_fw_file = os.path.abspath(fw_file.path)

        self.fw_file_hash = self.__read_hash_from_file(path_to_fw_file)

        _, fw_filename = os.path.split(path_to_fw_file)
        self.fw_file_location = os.path.join(self.FW_SAFE_LOCATION, self.device.str_name, fw_filename)

        if self.fw_file_location != path_to_fw_file:
            os.makedirs(os.path.dirname(self.fw_file_location), exist_ok=True)
            shutil.copyfile(path_to_fw_file, self.fw_file_location)
            PTLogger.debug('{} - File copied to {}'.format(self.device.str_name, self.fw_file_location))
