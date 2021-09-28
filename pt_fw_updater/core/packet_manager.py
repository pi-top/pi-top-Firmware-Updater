import binascii
import os
from enum import Enum

from .frame_creator import FrameCreator, get_crc16


class PacketType(Enum):
    StartingPacket = 1
    FwPackets = 2
    FwDownloadVerifiedPacket = 3


class PacketManager(object):
    frame_length = 256

    def __init__(self):
        self.bin_file = None

    def set_fw_file_to_install(self, bin_file):
        self.bin_file = bin_file

    def create_packets(self, packet_type):
        if packet_type == PacketType.StartingPacket:
            return self._create_starting_packet()
        if packet_type == PacketType.FwPackets:
            return self._create_fw_packets()

    def read_fw_download_verified_packet(self, packet):
        hex_of_packet = binascii.hexlify(packet.to_bytes(8, byteorder="big")).decode(
            "utf-8"
        )
        packet_crc_val = PacketManager._validate_and_return_crc_of_received_packet(
            hex_of_packet
        )
        PacketManager._check_first_byte_of_received_packet(hex_of_packet)
        hex_of_packet = hex_of_packet[10:]
        data_section = int(hex_of_packet.replace(packet_crc_val, ""))
        return data_section == 1

    def _create_starting_packet(self):
        if self.bin_file is None:
            raise Exception("No binary file specified")

        fw_size = PacketManager._int_to_hex_string(os.path.getsize(self.bin_file), 4)
        frame_size = PacketManager._int_to_hex_string(self.frame_length, 2)
        total_frames = PacketManager._int_to_hex_string(len(self._get_frames_list()), 2)
        last_frame = PacketManager._int_to_hex_string(
            len(self._get_frames_list()[-1]), 2
        )
        fw_checksum = self._get_firmware_checksum()
        reserved = PacketManager._int_to_hex_string(0, 2)
        return FrameCreator.create_initialising_frame(
            fw_size, frame_size, total_frames, last_frame, fw_checksum, reserved
        )

    def _create_fw_packets(self):
        frames_packet_list = []
        for frameNumber, frameData in enumerate(self._get_frames_list()):
            frameNumber += 1
            new_frame = FrameCreator.create_fw_frame(frameNumber, frameData)
            frames_packet_list.insert(len(frames_packet_list), new_frame)
        return frames_packet_list

    @staticmethod
    def _check_first_byte_of_received_packet(hex_of_packet):
        if "8a" not in hex_of_packet[:2]:
            raise ValueError(
                "First byte (8A) not found in received packet: {}".format(hex_of_packet)
            )

    @staticmethod
    def _validate_and_return_crc_of_received_packet(hex_of_packet):
        received_crc_val = hex_of_packet[-4:]
        calculated_crc_val = get_crc16(hex_of_packet[:-4])
        if received_crc_val != calculated_crc_val:
            raise ValueError(
                "received CRC value = "
                + received_crc_val
                + " and calculated CRC value = "
                + calculated_crc_val
                + " are not the same"
            )
        return received_crc_val

    def _get_firmware_checksum(self):
        if self.bin_file is None:
            raise Exception("No binary file specified")

        with open(self.bin_file, "rb") as f:
            file_data = f.read()
        checksum_val = b"%02X" % (sum(file_data) & 0xFFFFFFFF)
        return checksum_val.decode("UTF-8").zfill(8)

    def _get_frames_list(self):
        if self.bin_file is None:
            raise Exception("No binary file specified")

        with open(self.bin_file, "rb") as f:
            file_data = f.read()
        file_size = len(file_data)
        frames_list = [
            file_data[i : i + self.frame_length]  # noqa
            for i in range(0, file_size, self.frame_length)
        ]
        return frames_list

    @staticmethod
    def _int_to_hex_string(value, byte_length):
        byte_format = "{:0" + str(byte_length * 2) + "x}"
        return byte_format.format(value)
