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


class FirmwareUpdater(object):
    fw_dst_path = ""
    fw_hash = ""
    FW_SAFE_LOCATION = "/tmp/pt-firmware-updater/bin/"
    FW_INITIAL_LOCATION = "/usr/lib/pt-firmware-updater/bin/"

    def __init__(self, fw_device: FirmwareDevice) -> None:
        self.device = fw_device
        self._packet = PacketManager()

    def update_available(self) -> bool:
        """
        Checks if there are updates available for the given device
        :return: tuple with device object and path to firmware update if
        there's a update available. None otherwise.
        """
        PTLogger.info('{} - Checking update availability.'.format(self.device.str_name))

        if self.fw_downloaded_successfully():
            PTLogger.info(
                "{} - There's a binary uploaded to the device waiting to be installed. Skipping."
                .format(self.device.str_name))
            return False

        board = self.device.get_sch_hardware_version_major()
        fw_path = os.path.join(self.FW_INITIAL_LOCATION, self.device.str_name, "b" + str(board))
        PTLogger.debug("{} - Looking for binaries in: {}".format(self.device.str_name, fw_path))

        fw_to_install = self.__get_latest_fw_version_to_install(fw_path)
        if not fw_to_install:
            return False

        current_fw_version = self.device.get_fw_version()
        PTLogger.info(
            "{} - Current Firmware Version: {}"
            .format(self.device.str_name, current_fw_version))
        PTLogger.info(
            "{} - Possible update found. Candidate Firmware Version: {}"
                .format(self.device.str_name, fw_to_install))

        if StrictVersion(current_fw_version) >= StrictVersion(fw_to_install):
            PTLogger.info(
                "{} - Firmware installed is newer than the candidate. Exiting."
                    .format(self.device.str_name))
            return False

        fw_file_path = os.path.join(fw_path, fw_to_install + ".bin")
        self.fw_hash = self.__read_hash_from_file(fw_file_path)
        self.fw_dst_path = os.path.join(self.FW_SAFE_LOCATION, fw_to_install + '.bin')

        # Copy binary to a safe location before installing
        os.makedirs(os.path.dirname(self.fw_dst_path), exist_ok=True)
        shutil.copyfile(fw_file_path, self.fw_dst_path)

        PTLogger.info(
            "{} - Firmware update found: {}"
            .format(self.device.str_name, self.fw_dst_path))
        return True

    def install_updates(self) -> bool:
        """
        Sends the firmware file to the device
        :param device: device object
        :return: Nothing. Exceptions on failure.
        """
        self.__update_firmware()
        time_wait_mcu = 0.1
        PTLogger.info(
            '{} - Sleeping for {}s before verifying update'
                .format(self.device.str_name, time_wait_mcu))
        sleep(time_wait_mcu)  # Wait for MCU before verifying

        if self.fw_downloaded_successfully():
            PTLogger.info(
                "{} - Successfully applied update."
                .format(self.device.str_name))
            return True
        PTLogger.error("{} - Failed to update.".format(self.device.str_name))
        return False

    def fw_downloaded_successfully(self) -> bool:
        check_fw_packet = self.device.get_check_fw_okay()
        return self._packet.read_fw_download_verified_packet(check_fw_packet)

    def __update_firmware(self) -> None:
        if not os.path.isfile(self.fw_dst_path):
            PTLogger.error(str(self.fw_dst_path) + "doesn't exist.")
            return

        if self.fw_hash != self.__read_hash_from_file(self.fw_dst_path):
            PTLogger.error(
                "{} - Binary file didn't pass the sanity check. Exiting."
                    .format(self.device.str_name))
            return

        self._packet.set_fw_file_to_install(self.fw_dst_path)

        starting_packet = self._packet.create_packets(PacketType.StartingPacket)
        self.device.send_packet(DeviceInfo.FW__UPGRADE_START, starting_packet)

        fw_packets = self._packet.create_packets(PacketType.FwPackets)
        PTLogger.info('{} - Sending packages to device, please wait.'.format(self.device.str_name))
        for i in range(len(fw_packets)):
            packet = fw_packets[i]
            self.device.send_packet(DeviceInfo.FW__UPGRADE_PACKET, packet)

            if i == len(fw_packets) - 1:
                PTLogger.info("{} - Finished.".format(self.device.str_name))

    def __get_latest_fw_version_to_install(self, fw_path: str) -> str:
        """
        Looks for the latest firmware version in a specified folder
        :param fw_path: path to the folder where the latest update
        will be searched
        :return: string with the name of the binary corresponding to the latest
        available version of the firmware.
        """
        if not os.path.exists(fw_path):
            PTLogger.error(
                "{} - Firmware path doesn't exist. Exiting."
                    .format(self.device.str_name))
            return False

        candidate_latest_fw_version = "0.0"
        with os.scandir(fw_path) as i:
            for entry in i:
                if not entry.is_file() or not entry.name.endswith(".bin"):
                    continue

                fw_version_under_inspection = entry.name.replace(".bin", "")
                success = False
                try:
                    StrictVersion(fw_version_under_inspection)
                    success = True
                except ValueError:
                    PTLogger.info(
                        "{} - Skipping invalid firmware file: {}"
                        .format(self.device.str_name, entry.name))
                    continue

                if not success:
                    continue

                if StrictVersion(fw_version_under_inspection) >=\
                        StrictVersion(candidate_latest_fw_version):
                    candidate_latest_fw_version = fw_version_under_inspection

        if candidate_latest_fw_version == 0:
            PTLogger.info(
                "{} - No firmware found in folder. Exiting."
                .format(self.device.str_name))
            return ""

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
