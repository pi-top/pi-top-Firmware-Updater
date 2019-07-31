from enum import Enum


class PacketType(Enum):
    StartingPacket = 1
    FwPackets = 2
    FwDownloadVerifiedPacket = 3
    FwVersionPacket = 4
