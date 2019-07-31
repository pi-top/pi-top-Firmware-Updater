from enum import Enum
from packet_type import PacketType
from packet_creator import PacketCreator
from time import sleep
from ptcommon.i2c_device import I2CDevice
import binascii


class HardwareReg(Enum):
    fwStart = 0x01
    fwFlash = 0x02
    checkFwDownloaded = 0x03
    fwVersionMajor = 0xE8
    fwVersionMinor = 0xE9


class HubCommunicator(object):
    i2c_device = I2CDevice("/dev/i2c-1", 0x10)
    sendPacketInterval = 0.200

    def __init__(self, bin_file):
        self.i2c_device.connect()
        self.packet = PacketCreator(bin_file)

    def send_packet(self, hardware_reg, packet):
        self.i2c_device.write_n_bytes(hardware_reg.value, packet)
        sleep(self.sendPacketInterval)

    def receive_packet(self, hardware_reg, packet_type):  # TODO
        if packet_type == PacketType.FwVersionPacket:
            return self.i2c_device.read_n_unsigned_bytes(hardware_reg.value, 23)
        elif packet_type == PacketType.FwDownloadVerifiedPacket:
            return self.i2c_device.read_n_unsigned_bytes(hardware_reg.value, 8)
        else:
            raise ValueError("Incorrect packet type")

    def send_update(self):
        print("Sending update ", end="", flush=True)
        starting_packet = self.packet.create_packets(PacketType.StartingPacket)
        self.send_packet(HardwareReg.fwStart, starting_packet)
        fw_packets = self.packet.create_packets(PacketType.FwPackets)
        for packet in fw_packets:
            print(".", end="", flush=True)
            self.send_packet(HardwareReg.fwFlash, packet)
        print(" Done!")

    def check_fw_downloaded_on_slave(self):
        check_fw_packet = self.receive_packet(
            HardwareReg.checkFwDownloaded, PacketType.FwDownloadVerifiedPacket
        )
        return self.packet.read_packet(
            PacketType.FwDownloadVerifiedPacket, check_fw_packet
        )

    def get_fw_version(self):
        fw_version_major_packet = self.receive_packet(
            HardwareReg.fwVersionMajor, PacketType.FwVersionPacket
        )
        major_ver = self.packet.read_packet(
            PacketType.FwVersionPacket, fw_version_major_packet
        )

        fw_version_major_packet = self.receive_packet(
            HardwareReg.fwVersionMinor, PacketType.FwVersionPacket
        )
        minor_ver = self.packet.read_packet(
            PacketType.FwVersionPacket, fw_version_major_packet
        )
        return str(major_ver) + "." + str(minor_ver)

    def update_firmware(self):
        #print(self.get_fw_version())
        self.send_update()
        # print("Firmware bin downloaded ", self.check_fw_downloaded_on_slave())
