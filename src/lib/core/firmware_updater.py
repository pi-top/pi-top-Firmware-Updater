from hashlib import md5
from os import makedirs, path
from shutil import copyfile
from time import sleep

from pitopcommon.firmware_device import DeviceInfo, FirmwareDevice
from pitopcommon.logger import PTLogger

from .packet_manager import PacketManager, PacketType
from .firmware_file_object import FirmwareFileObject


class PTInvalidFirmwareFile(Exception):
    pass


class PTUpdatePending(Exception):
    pass


class FirmwareUpdater(object):
    fw_file_location = ""
    fw_file_hash = ""
    FW_SAFE_LOCATION = "/tmp/pt-firmware-updater/bin/"

    def __init__(self, fw_device: FirmwareDevice) -> None:
        self.device = fw_device
        self._packet = PacketManager()
        self.__processed_firmware_files = list()
        self.set_current_device_info()

    def set_current_device_info(self):
        self.device_info = FirmwareFileObject.from_device(self.device)

    def has_staged_updates(self) -> bool:
        return path.isfile(self.fw_file_location) and \
            self.__read_hash_from_file(self.fw_file_location) == self.fw_file_hash

    def stage_file(self, fw_file: FirmwareFileObject, force: bool = False) -> None:
        PTLogger.debug('{} - Verifying file {}'.format(self.device_info.device_name, fw_file.path))

        if self.fw_downloaded_successfully():
            raise PTUpdatePending("There's a binary uploaded to {} waiting to be installed".format(self.device_info.device_name))

        if force is True:
            PTLogger.warning("Skipping firmware file verification (using --force argument)")
        elif not self.__firmware_file_is_valid(fw_file):
            raise PTInvalidFirmwareFile('{} is not a valid candidate firmware file'.format(fw_file.path))

        self.__prepare_firmware_for_install(fw_file)
        PTLogger.info("{} - {} was staged to be updated (version {}).".format(self.device_info.device_name, fw_file.path, fw_file.firmware_version))

    def install_updates(self) -> bool:
        fw_version_before_install = self.device_info.firmware_version

        PTLogger.info(f"Current device version is {fw_version_before_install}")
        self.__send_staged_firmware_to_device()

        PTLogger.info("{} - Successfully sent firmware to device.".format(self.device_info.device_name))

        success = True

        if self.device_info.device_name == "pt4_hub" \
                or self.device_info.device_name == "pt4_expansion_plate" \
                or self.device.get_fw_version_update_schema() == 0:
            requires_restart = True
            return success, requires_restart

        self.device.reset()

        time_wait_mcu = 2

        PTLogger.info(
            "{} - Sleeping for {} secs before verifying update".format(self.device_info.device_name, time_wait_mcu))
        sleep(time_wait_mcu)

        self.set_current_device_info()
        success = self.device_info.firmware_version > fw_version_before_install

        if success:
            PTLogger.info("{} - Successfully restarted after update.".format(self.device_info.device_name))
        else:
            PTLogger.error("{} - Failed to update.".format(self.device_info.device_name))

        requires_restart = False
        return success, requires_restart

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
        check_fw_packet = None

        # this read sometimes fails after an update is completed
        time_sleep_on_error = 0.1
        for i in range(5):
            try:
                check_fw_packet = self.device.get_check_fw_okay()
                if check_fw_packet:
                    break
            except Exception:
                PTLogger.debug(f"Couldn't read FW OKAY register from device. Sleeping for {time_sleep_on_error} secs")
                sleep(time_sleep_on_error)

        if check_fw_packet is None:
            PTLogger.error("Couldn't read FW OKAY register from device")
            return False
        return self._packet.read_fw_download_verified_packet(check_fw_packet)

    def __candidate_fw_version_is_newer_than_current(self, fw_file: FirmwareFileObject):
        PTLogger.debug("Checking if candidate firmware version is newer than device")
        return FirmwareFileObject.is_newer(self.device_info, fw_file)

    def __firmware_file_is_valid(self, fw_file: FirmwareFileObject):
        verified = fw_file.verify(self.device_info.device_name, self.device_info.schematic_version)
        if not verified:
            return False

        newer = self.__candidate_fw_version_is_newer_than_current(fw_file)
        return newer

    def __read_hash_from_file(self, filename: str) -> str:
        """
        Computes the MD5 hash of the given file
        :param filename: path to a file
        :return: MD5 hash
        """
        if not path.exists(filename):
            raise FileNotFoundError("Firmware path doesn't exist.")

        hash = md5()
        with open(filename, "rb") as f:
            buff = f.read()
            hash.update(buff)
        return hash.hexdigest()

    def __prepare_firmware_for_install(self, fw_file: FirmwareFileObject) -> None:
        PTLogger.debug('{} - Preparing firmware for installation'.format(self.device_info.device_name))
        path_to_fw_file = path.abspath(fw_file.path)

        self.fw_file_hash = self.__read_hash_from_file(path_to_fw_file)

        _, fw_filename = path.split(path_to_fw_file)
        self.fw_file_location = path.join(
            self.FW_SAFE_LOCATION, self.device_info.device_name, fw_filename
        )

        if self.fw_file_location != path_to_fw_file:
            makedirs(path.dirname(self.fw_file_location), exist_ok=True)
            copyfile(path_to_fw_file, self.fw_file_location)
            PTLogger.debug('{} - File copied to {}'.format(self.device_info.device_name, self.fw_file_location))
