from .packet_type import PacketType
from .packet_creator import PacketCreator

from ptcommon.i2c_device import I2CDevice

from enum import Enum
from time import sleep
import binascii


# Taken from hubv3 class
# TODO: move to common library
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
    def __init__(self, i2c_address, bin_file, send_packet_interval):
        self.i2c_device = I2CDevice("/dev/i2c-1", i2c_address)
        self.i2c_device.set_delays(send_packet_interval, send_packet_interval)
        self.i2c_device.connect()

        self.packet = PacketCreator(bin_file)

    def get_fw_version(self):
        fw_version_major_packet = self._receive_packet(
            DeviceInfo.ID__MCU_SOFT_VERS_MAJOR, PacketType.FwVersionPacket
        )
        major_ver = self.packet.read_packet(
            PacketType.FwVersionPacket, fw_version_major_packet
        )

        fw_version_minor_packet = self._receive_packet(
            DeviceInfo.ID__MCU_SOFT_VERS_MINOR, PacketType.FwVersionPacket
        )
        minor_ver = self.packet.read_packet(
            PacketType.FwVersionPacket, fw_version_minor_packet
        )
        return str(major_ver) + "." + str(minor_ver)

    def get_part_number(self):
        return self._i2c_device.read_unsigned_word(DeviceInfo.ID__PART_NAME)

    def get_sch_hardware_version_major(self):
        return self._i2c_device.read_unsigned_byte(DeviceInfo.ID__SCH_REV_MAJOR)

    def update_firmware(self):
        # print(self.get_fw_version())
        self._perform_update()
        # print("Firmware bin downloaded ", self._check_fw_downloaded_on_slave())

    def _send_packet(self, hardware_reg, packet):
        self.i2c_device.write_n_bytes(hardware_reg, packet)

    def _receive_packet(self, hardware_reg, packet_type):
        if packet_type == PacketType.FwVersionPacket:
            return self.i2c_device.read_n_unsigned_bytes(hardware_reg, 23)
        elif packet_type == PacketType.FwDownloadVerifiedPacket:
            return self.i2c_device.read_n_unsigned_bytes(hardware_reg, 8)
        else:
            raise ValueError("Incorrect packet type")

    def _perform_update(self):
        starting_packet = self.packet.create_packets(PacketType.StartingPacket)
        self._send_packet(DeviceInfo.FW__UPGRADE_START, starting_packet)
        fw_packets = self.packet.create_packets(PacketType.FwPackets)
        for i in range(len(fw_packets)):
            packet = fw_packets[i]
            self._send_packet(DeviceInfo.FW__UPGRADE_PACKET, packet)
            if i == len(fw_packets) - 1:
                print("COMPLETE")
            else:
                print(f"{i/len(fw_packets)*100:.1f}%", end="\r")

    def _check_fw_downloaded_on_slave(self):
        check_fw_packet = self._receive_packet(
            DeviceInfo.FW__CHECK_FW_OKAY, PacketType.FwDownloadVerifiedPacket
        )
        return self.packet.read_packet(
            PacketType.FwDownloadVerifiedPacket, check_fw_packet
        )
