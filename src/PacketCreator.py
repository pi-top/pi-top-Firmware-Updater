from PacketType import PacketType
from FrameCreator import FrameCreator
import binascii
import os


class PacketCreator(object):
    frameLength = 256

    def __init__(self, binFile):
        self.binFile = binFile
        self.framesList = self._getFramesList(binFile)
        self.Frame = FrameCreator()

    def createPacket(self, packetType):
        if packetType == PacketType.StartingPacket:
            return self._createStartingPacket()
        if packetType == PacketType.FwPackets:
            return self._createFwPackets()

    def readPacket(self, packetType, packet):
        if packetType == PacketType.FwDownloadVerifiedPacket:
            return self._readFwDownloadVerifiedPacket(packet)
        if packetType == PacketType.FwVersionPacket:
            return self._readFwVersionPacket(packet)

    def _createStartingPacket(self):
        fwSize = self.intToHexString(os.path.getsize(self.binFile), 4)
        frameSize = self.intToHexString(self.frameLength, 2)
        totalFrames = self.intToHexString(len(self.framesList), 2)
        lastFrame = self.intToHexString(len(self.framesList[-1]), 2)
        fwChecksum = self._getFirmwareChecksum()
        reserved = self.intToHexString(0, 2)
        return self.Frame.createInitialisingFrame(
            fwSize, frameSize, totalFrames, lastFrame, fwChecksum, reserved
        )

    def _createFwPackets(self):
        framesPacketList = []
        for frameNumber, frameData in enumerate(self.framesList):
            frameNumber += 1
            newFrame = self.Frame.createFwFrame(frameNumber, frameData)
            framesPacketList.insert(len(framesPacketList), newFrame)
        return framesPacketList

    def _readFwDownloadVerifiedPacket(self, packet):  # TODO
        hexOfPacket = binascii.hexlify(bytes(packet)).decode("utf-8")
        packetCRCValue = self._validateAndReturnCRCOfRecivedPacket(hexOfPacket)
        self._checkReceivedPacketSize(
            packet, PacketType.FwDownloadVerifiedPacket)
        self._checkFirstByteOfReceivedPacket(hexOfPacket)
        hexOfPacket = hexOfPacket[10:]
        dataSection = int(hexOfPacket.replace(packetCRCValue, ""))
        if dataSection == 1:
            return True
        return False

    def _readFwVersionPacket(self, packet):  # TODO
        hexOfPacket = binascii.hexlify(bytes(packet)).decode("utf-8")
        packetCRCValue = self._validateAndReturnCRCOfRecivedPacket(hexOfPacket)
        self._checkReceivedPacketSize(packet, PacketType.FwVersionPacket)
        self._checkFirstByteOfReceivedPacket(hexOfPacket)
        hexOfPacket = hexOfPacket[10:]
        dataSection = hexOfPacket.replace(packetCRCValue, "")
        firmwareName = bytes.fromhex(
            dataSection[2:]).decode("utf-8").strip("\x00")
        firmwareVersion = dataSection[:2]
        return firmwareName, firmwareVersion

    def _checkFirstByteOfReceivedPacket(self, hexOfPacket):
        if "8a" not in hexOfPacket[:2]:
            raise ValueError("first byte not found in received packet")

    def _checkReceivedPacketSize(self, packet, packetType):
        if packetType == PacketType.FwDownloadVerifiedPacket:
            if len(packet) != 8:
                raise ValueError(
                    "FwDownloadVerifiedPacket size is incorrect" +
                    str(len(packet))
                )
        if packetType == PacketType.FwVersionPacket:
            if len(packet) != 23:
                raise ValueError(
                    "FwVersionPacket size is incorrect" + str(len(packet)))

    def _validateAndReturnCRCOfRecivedPacket(self, hexOfPacket):
        receivedCRCValue = hexOfPacket[-4:]
        calculatedCRCValue = self.Frame.getCRC16(hexOfPacket[:-4])
        if receivedCRCValue != calculatedCRCValue:
            raise ValueError(
                "received CRC value = "
                + receivedCRCValue
                + " and calculated CRC value = "
                + calculatedCRCValue
                + " are not the same"
            )
        return receivedCRCValue

    def _getFirmwareChecksum(self):
        with open(self.binFile, "rb") as f:
            fileData = f.read()
        checksumValue = b"%02X" % (sum(fileData) & 0xFFFFFFFF)
        return checksumValue.decode("UTF-8").zfill(8)

    def _getFramesList(self, binFile):
        with open(binFile, "rb") as f:
            fileData = f.read()
        fileSize = len(fileData)
        framesList = [
            fileData[i: i + self.frameLength]
            for i in range(0, fileSize, self.frameLength)
        ]
        return framesList

    def intToHexString(self, value, byteLength):
        byteFormat = "{:0" + str(byteLength * 2) + "x}"
        return byteFormat.format(value)
