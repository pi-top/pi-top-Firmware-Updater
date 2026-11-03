import logging
from hashlib import md5
from os import makedirs, path
from shutil import copyfile
from time import sleep
from typing import Callable, Optional, Tuple

from pitop.common.firmware_device import DeviceInfo, FirmwareDevice

from .firmware_file_object import FirmwareFileObject
from .packet_manager import PacketManager, PacketType

logger = logging.getLogger(__name__)


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
        self.set_current_device_info()

    def set_current_device_info(self):
        self.device_info = FirmwareFileObject.from_device(self.device)

    def has_staged_updates(self) -> bool:
        return (
            path.isfile(self.fw_file_location)
            and self.__read_hash_from_file(self.fw_file_location) == self.fw_file_hash
        )

    def stage_file(self, fw_file: FirmwareFileObject, force: bool = False) -> None:
        logger.debug(f"{self.device_info.device_name} - Verifying file {fw_file.path}")

        if self.fw_downloaded_successfully():
            raise PTUpdatePending(
                f"There's a binary uploaded to {self.device_info.device_name} waiting to be installed"
            )

        if force is True:
            logger.warning(
                "Skipping firmware file verification (using --force argument)"
            )
        elif not self.__firmware_file_is_valid(fw_file):
            raise PTInvalidFirmwareFile(
                f"{fw_file.path} is not a valid candidate firmware file"
            )

        self._copy_file_to_staging_folder(fw_file)
        logger.info(
            f"{self.device_info.device_name} - {fw_file.path} was staged to be updated (version {fw_file.firmware_version})."
        )

    def install_updates(
        self, on_progress: Optional[Callable] = None
    ) -> Tuple[bool, bool]:
        fw_version_before_install = self.device_info.firmware_version

        logger.info(f"Current device version is {fw_version_before_install}")

        def report(progress):
            if on_progress:
                on_progress(progress)

        def report_stagging_progress(progress):
            # Sending the firmware to the device takes 90% of the whole process
            report(progress * 0.9)

        self._send_firmware_to_device(on_progress=report_stagging_progress)

        logger.info(
            f"{self.device_info.device_name} - Successfully sent firmware to device."
        )

        success = True

        if (
            self.device_info.device_name == "pt4_hub"
            or self.device_info.device_name == "pt4_expansion_plate"
            or self.device.get_fw_version_update_schema() == 0
        ):
            requires_restart = True
        else:
            self.device.reset()
            time_wait_mcu = 2

            logger.info(
                f"{self.device_info.device_name} - Sleeping for {time_wait_mcu} secs before verifying update"
            )
            sleep(time_wait_mcu)

            self.set_current_device_info()
            success = self.device_info.firmware_version > fw_version_before_install

            if success:
                logger.info(
                    f"{self.device_info.device_name} - Successfully restarted after update."
                )
            else:
                logger.error(f"{self.device_info.device_name} - Failed to update.")

            requires_restart = False

        report(100)
        return success, requires_restart

    def _send_firmware_to_device(self, on_progress: Optional[Callable] = None) -> None:
        if not self.has_staged_updates():
            logger.error("There isn't a firmware staged to be installed on")
            return

        if self.fw_file_hash != self.__read_hash_from_file(self.fw_file_location):
            logger.error(
                f"{self.device_info.device_name} - Binary file didn't pass the sanity check."
            )
            return

        self._packet.set_fw_file_to_install(self.fw_file_location)

        starting_packet = self._packet.create_packets(PacketType.StartingPacket)
        self.device.send_packet(DeviceInfo.FW__UPGRADE_START, starting_packet)

        fw_packets = self._packet.create_packets(PacketType.FwPackets)
        logger.info(
            f"{self.device_info.device_name} - Sending packages to device, please wait."
        )

        for i in range(len(fw_packets)):
            packet = fw_packets[i]
            self.device.send_packet(DeviceInfo.FW__UPGRADE_PACKET, packet)

            if on_progress:
                on_progress(100 * (i + 1) / len(fw_packets))

        logger.info(f"{self.device_info.device_name} - Finished.")

    def fw_downloaded_successfully(self) -> bool:
        logger.debug(
            "Checking if device has previously loaded firmware ready to be installed"
        )
        check_fw_packet = None

        # this read sometimes fails after an update is completed
        time_sleep_on_error = 0.1
        for i in range(5):
            try:
                check_fw_packet = self.device.get_check_fw_okay()
                if check_fw_packet:
                    break
            except Exception:
                logger.debug(
                    f"Couldn't read FW OKAY register from device. Sleeping for {time_sleep_on_error} secs"
                )
                sleep(time_sleep_on_error)

        if check_fw_packet is None:
            logger.error("Couldn't read FW OKAY register from device")
            return False
        return self._packet.read_fw_download_verified_packet(check_fw_packet)

    def __candidate_fw_version_is_newer_than_current(self, fw_file: FirmwareFileObject):
        logger.debug("Checking if candidate firmware version is newer than device")
        return FirmwareFileObject.is_newer(self.device_info, fw_file)

    def __firmware_file_is_valid(self, fw_file: FirmwareFileObject):
        verified = fw_file.verify(
            self.device_info.device_name, self.device_info.schematic_version
        )
        if not verified:
            return False

        newer = self.__candidate_fw_version_is_newer_than_current(fw_file)
        return newer

    def __read_hash_from_file(self, filename: str) -> str:
        """Computes the MD5 hash of the given file.

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

    def _copy_file_to_staging_folder(self, fw_file: FirmwareFileObject) -> None:
        logger.debug(
            f"{self.device_info.device_name} - Preparing firmware for installation"
        )
        path_to_fw_file = path.abspath(fw_file.path)

        self.fw_file_hash = self.__read_hash_from_file(path_to_fw_file)

        _, fw_filename = path.split(path_to_fw_file)
        self.fw_file_location = path.join(
            self.FW_SAFE_LOCATION, self.device_info.device_name, fw_filename
        )

        if self.fw_file_location != path_to_fw_file:
            makedirs(path.dirname(self.fw_file_location), exist_ok=True)
            copyfile(path_to_fw_file, self.fw_file_location)
            logger.debug(
                f"{self.device_info.device_name} - File copied to {self.fw_file_location}"
            )
