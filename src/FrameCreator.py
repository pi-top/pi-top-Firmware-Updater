import binascii
from PyCRC.CRC16Kermit import CRC16Kermit


class FrameCreator(object):

    def createInitialisingFrame(self, fwSize, frameSize, totalFrames, lastFrame, fwChecksum, reserved):
        frameLength = str(format(7 + int(frameSize), '02x').zfill(4))
        prefix = "8A" + frameLength + "01A1"
        dataSection = fwSize + frameSize + totalFrames + lastFrame + fwChecksum + reserved
        crc = self.getCRC16(prefix + dataSection)
        return list(bytearray.fromhex(prefix + dataSection + crc))

    def createFwFrame(self, frameNumber, frameData):
        frameLength = str(format(9 + len(frameData), '02x').zfill(4))
        prefix = "8A" + frameLength + "01A2"
        hexStringFrameNumber = format(frameNumber, '04x')
        dataSection = hexStringFrameNumber + frameData.hex()
        crc = self.getCRC16(prefix + dataSection).zfill(4)
        return list(bytearray.fromhex(prefix + dataSection + crc))

    def getCRC16(self, frameData):
        crcValue = CRC16Kermit().calculate(binascii.unhexlify(frameData))
        return crcValue.to_bytes(2, byteorder="little").hex()