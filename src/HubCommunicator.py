from enum import Enum
from PacketType import PacketType
from PacketCreator import PacketCreator
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

    def __init__(self, binFile):
        self.i2c_device.connect()
        self.packet = PacketCreator(binFile)

    def sendPacket(self, hardwareReg, packet):  # TODO
        self.i2c_device.write_n_bytes(hardwareReg.value, packet)
        sleep(self.sendPacketInterval)

    def receivePacket(self, hardwareReg, packetType):  # TODO
        if packetType == PacketType.FwVersionPacket:
            return self.i2c_device.read_n_unsigned_bytes(hardwareReg.value, 23)
        elif packetType == PacketType.FwDownloadVerifiedPacket:
            return self.i2c_device.read_n_unsigned_bytes(hardwareReg.value, 8)
        else:
            raise ValueError("Incorrect packet type")

    def sendUpdate(self):
        startingPacket = self.packet.createPacket(PacketType.StartingPacket)
        self.sendPacket(HardwareReg.fwStart, startingPacket)
        fwPackets = self.packet.createPacket(PacketType.FwPackets)
        for packet in fwPackets:
            print(binascii.hexlify(bytearray(packet)))
            self.sendPacket(HardwareReg.fwFlash, packet)

    def checkFwDownloadedOnSlave(self):
        checkFwPacket = self.receivePacket(
            HardwareReg.checkFwDownloaded, PacketType.FwDownloadVerifiedPacket
        )
        return self.packet.readPacket(
            PacketType.FwDownloadVerifiedPacket, checkFwPacket
        )

    def getFwVersion(self):
        fwVersionMajorPacket = self.receivePacket(
            HardwareReg.fwVersionMajor, PacketType.FwVersionPacket
        )
        majorVer = self.packet.readPacket(
            PacketType.FwVersionPacket, fwVersionMajorPacket
        )

        fwVersionMinorPacket = self.receivePacket(
            HardwareReg.fwVersionMinor, PacketType.FwVersionPacket
        )
        minorVer = self.packet.readPacket(
            PacketType.FwVersionPacket, fwVersionMinorPacket
        )
        return str(majorVer) + "." + str(minorVer)

    def updateFirmware(self):
        print(self.getFwVersion())
        self.sendUpdate()
        # print("Firmware bin downloaded ", self.checkFwDownloadedOnSlave())
