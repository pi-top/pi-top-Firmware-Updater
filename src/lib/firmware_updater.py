import os
import shutil
import hashlib
from time import sleep
from distutils.version import StrictVersion

from ptcommon.firmware_device import DeviceInfo
from ptcommon.firmware_device import FirmwareDevice
from ptcommon.logger import PTLogger
from packet_manager import PacketManager
from packet_manager import PacketType


class PTInvalidFirmwareFile(Exception):
    pass


class PTUpdatePending(Exception):
    pass


class FirmwareUpdater(object):
    fw_file_location = ""
    fw_file_hash = ""
    FW_SAFE_LOCATION = "/tmp/pt-firmware-updater/bin/"
    FW_INITIAL_LOCATION = "/usr/lib/pt-firmware-updater/bin/"

    def __init__(self, fw_device: FirmwareDevice) -> None:
        self.device = fw_device
        self._packet = PacketManager()

    def has_staged_updates(self) -> bool:
        return os.path.isfile(self.fw_file_location) and \
            self.__read_hash_from_file(self.fw_file_location) == self.fw_file_hash

    def verify_and_stage_file(self, path_to_fw_file: str) -> None:
        PTLogger.debug('{} - Verifying file {}'.format(self.device.str_name, path_to_fw_file))

        if self.fw_downloaded_successfully():
            raise PTUpdatePending("There's a binary uploaded to {} waiting to be installed".format(self.device.str_name))

        if not self.__can_install_firmware_file(path_to_fw_file):
            raise PTInvalidFirmwareFile('{} is not a valid candidate firmware file'.format(path_to_fw_file))

        self.__prepare_firmware_for_install(path_to_fw_file)
        PTLogger.info("{} - {} is valid and was staged to be updated.".format(self.device.str_name, path_to_fw_file))

    def search_updates(self) -> None:
        PTLogger.debug('{} - Checking for updates in {}'.format(self.device.str_name, self.FW_INITIAL_LOCATION))

        board = self.device.get_sch_hardware_version_major()
        path_to_fw_folder = os.path.join(self.FW_INITIAL_LOCATION, self.device.str_name, "b" + str(board))
        PTLogger.debug("{} - Looking for binaries in: {}".format(self.device.str_name, path_to_fw_folder))

        fw_version = self.__get_latest_fw_version_from_path(path_to_fw_folder)
        if len(fw_version) == 0:
            return
        path_to_fw_file = os.path.join(path_to_fw_folder, fw_version + ".bin")

        self.verify_and_stage_file(path_to_fw_file)
        PTLogger.info("{} - Firmware update found: {}".format(self.device.str_name, path_to_fw_file))

    def install_updates(self) -> bool:
        self.__send_staged_firmware_to_device()

        time_wait_mcu = 0.1
        PTLogger.debug(
            "{} - Sleeping for {}s before verifying update".format(self.device.str_name, time_wait_mcu))
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
                "{} - Binary file didn't pass the sanity check. Exiting."
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
        check_fw_packet = self.device.get_check_fw_okay()
        return self._packet.read_fw_download_verified_packet(check_fw_packet)

    def __verify_firmware_file_format(self, path_to_file: str) -> bool:
        success = False
        if not os.path.isfile(path_to_file):
            PTLogger.warning("{} - {} is not a file".format(self.device.str_name, path_to_file))
            return success

        if not path_to_file.endswith(".bin"):
            PTLogger.warning(
                "{} - filename on {} is not properly formatted".format(self.device.str_name, path_to_file))
            return success

        try:
            _, fw_version = os.path.split(path_to_file)
            fw_version = fw_version.replace(".bin", "")
            StrictVersion(fw_version)
            PTLogger.debug("{} - {} has a valid version ({})".format(self.device.str_name, path_to_file, fw_version))
            success = True
        except ValueError:
            PTLogger.error("{} - Skipping invalid firmware file: {}".format(self.device.str_name, path_to_file))

        return success

    def __can_install_firmware_file(self, path_to_fw_file: str):
        def can_install_version(path_to_file: str):
            _, candidate_fw_version = os.path.split(path_to_file)
            candidate_fw_version = candidate_fw_version.replace(".bin", "")

            current_fw_version = self.device.get_fw_version()
            PTLogger.info(
                "{} - Current Firmware Version: {}".format(self.device.str_name, current_fw_version))
            PTLogger.info(
                "{} - Candidate Firmware Version: {}".format(self.device.str_name, candidate_fw_version))

            if StrictVersion(current_fw_version) >= StrictVersion(candidate_fw_version):
                PTLogger.info(
                    "{} - Firmware installed is newer than the candidate".format(self.device.str_name))
                return False
            return True

        if not self.__verify_firmware_file_format(path_to_fw_file):
            return False

        if not can_install_version(path_to_fw_file):
            return False

        return True

    def __get_latest_fw_version_from_path(self, fw_path: str) -> str:
        """
        Looks for the latest firmware version in a specified folder
        :param fw_path: path to the folder where the latest update
        will be searched
        :return: string with the name of the binary corresponding to the latest
        available version of the firmware.
        """
        if not os.path.exists(fw_path):
            raise FileNotFoundError("Firmware path {} doesn't exist. Exiting.".format(fw_path))

        candidate_latest_fw_version = "0.0"
        with os.scandir(fw_path) as i:
            for entry in i:
                if self.__verify_firmware_file_format(entry.path):
                    _, version = os.path.split(entry.path)
                    fw_version_under_inspection = version.replace(".bin", "")

                    if StrictVersion(fw_version_under_inspection) >= \
                            StrictVersion(candidate_latest_fw_version):
                        candidate_latest_fw_version = fw_version_under_inspection

        if candidate_latest_fw_version == "0.0":
            PTLogger.warning("{} - No firmware found in folder. Exiting.".format(self.device.str_name))
            candidate_latest_fw_version = ""
        else:
            PTLogger.debug("{} - Latest firmware available is version {}".format(self.device.str_name, candidate_latest_fw_version))

        return candidate_latest_fw_version

    def __read_hash_from_file(self, filename: str) -> str:
        """
        Computes the MD5 has of the given file
        :param filename: path to a file
        :return: MD5 hash
        """
        if not os.path.exists(filename):
            raise FileNotFoundError("Firmware path doesn't exist. Exiting.")

        hash = hashlib.md5()
        with open(filename, "rb") as f:
            buff = f.read()
            hash.update(buff)
        return hash.hexdigest()

    def __prepare_firmware_for_install(self, path_to_fw_file: str) -> None:
        PTLogger.debug('{} - Preparing firmware for installation'.format(self.device.str_name))
        path_to_fw_file = os.path.abspath(path_to_fw_file)
        if not os.path.exists(path_to_fw_file):
            raise FileNotFoundError("Path {} doesn't exist.".format(path_to_fw_file))

        self.fw_file_hash = self.__read_hash_from_file(path_to_fw_file)

        fw_folder, fw_filename = os.path.split(path_to_fw_file)
        self.fw_file_location = os.path.join(self.FW_SAFE_LOCATION, self.device.str_name, fw_filename)

        if self.fw_file_location != path_to_fw_file:
            os.makedirs(os.path.dirname(self.fw_file_location), exist_ok=True)
            shutil.copyfile(path_to_fw_file, self.fw_file_location)
            PTLogger.debug('{} - File copied to {}'.format(self.device.str_name, self.fw_file_location))
