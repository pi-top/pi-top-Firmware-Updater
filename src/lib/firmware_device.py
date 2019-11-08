from packet_manager import PacketManager, PacketType

from ptcommon.i2c_device import I2CDevice

from enum import Enum
from time import sleep
import binascii


# Taken from hubv3 class
# TODO: move to common library, as this is common to all firmware-upgradable devices
class DeviceInfo:
    FW__UPGRADE_START = 0x01
    FW__UPGRADE_PACKET = 0x02
    FW__CHECK_FW_OKAY = 0x03
    FW__GET_FW_VERSION = 0x04

    ID__MCU_SOFT_VERS_MAJOR = 0xE0
    ID__MCU_SOFT_VERS_MINOR = 0xE1
    ID__SCH_REV_MAJOR = 0xE2
    ID__SCH_REV_MINOR = 0xE3
    ID__BRD_REV = 0xE4
    ID__PART_NAME = 0xE5
    ID__PART_NUMBER = 0xE6


class FirmwareDevice(object):
    def __init__(self, i2c_address, send_packet_interval):
        self._i2c_device = I2CDevice("/dev/i2c-1", i2c_address)
        self._i2c_device.set_delays(send_packet_interval, send_packet_interval)
        self._i2c_device.connect()

        self._packet = PacketManager()

    def set_fw_file_to_install(self, bin_file):
        self._packet.set_fw_file_to_install(bin_file)

    def get_fw_version(self):
        major_ver = self._get_mcu_software_version_major()
        minor_ver = self._get_mcu_software_version_minor()

        return str(major_ver) + "." + str(minor_ver)

    def update_firmware(self):
        starting_packet = self._packet.create_packets(PacketType.StartingPacket)
        self._send_packet(DeviceInfo.FW__UPGRADE_START, starting_packet)
        fw_packets = self._packet.create_packets(PacketType.FwPackets)
        for i in range(len(fw_packets)):
            packet = fw_packets[i]
            self._send_packet(DeviceInfo.FW__UPGRADE_PACKET, packet)
            if i == len(fw_packets) - 1:
                print("COMPLETE")
            else:
                print(f"{i/len(fw_packets)*100:.1f}%", end="\r")

    def fw_downloaded_successfully(self):
        check_fw_packet = self._i2c_device.read_n_unsigned_bytes(DeviceInfo.FW__CHECK_FW_OKAY, 8)

        return self._packet.read_fw_download_verified_packet(check_fw_packet)

    def _get_mcu_software_version_major(self):
        return self._i2c_device.read_unsigned_byte(DeviceInfo.ID__MCU_SOFT_VERS_MAJOR)

    def _get_mcu_software_version_minor(self):
        return self._i2c_device.read_unsigned_byte(DeviceInfo.ID__MCU_SOFT_VERS_MINOR)

    def get_part_number(self):
        return self._i2c_device.read_unsigned_word(DeviceInfo.ID__PART_NUMBER)

    def get_sch_hardware_version_major(self):
        return self._i2c_device.read_unsigned_byte(DeviceInfo.ID__SCH_REV_MAJOR)

    def _send_packet(self, hardware_reg, packet):
        self._i2c_device.write_n_bytes(hardware_reg, packet)
