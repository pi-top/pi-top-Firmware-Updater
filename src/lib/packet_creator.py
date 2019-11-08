from .packet_type import PacketType
from .frame_creator import FrameCreator, get_crc16

import binascii
import os


class PacketCreator(object):
    frame_length = 256

    def __init__(self, bin_file):
        self.bin_file = bin_file
        self.frames_list = self._get_frames_list(bin_file)

    def create_packets(self, packet_type):
        if packet_type == PacketType.StartingPacket:
            return self._create_starting_packet()
        if packet_type == PacketType.FwPackets:
            return self._create_fw_packets()

    def read_packet(self, packet_type, packet):
        if packet_type == PacketType.FwDownloadVerifiedPacket:
            return self._read_fw_download_verified_packet(packet)
        if packet_type == PacketType.FwVersionPacket:
            return self._read_fw_version_packet(packet)

    def _create_starting_packet(self):
        fw_size = PacketCreator.int_to_hex_string(
            os.path.getsize(self.bin_file), 4)
        frame_size = PacketCreator.int_to_hex_string(self.frame_length, 2)
        total_frames = PacketCreator.int_to_hex_string(len(self.frames_list), 2)
        last_frame = PacketCreator.int_to_hex_string(
            len(self.frames_list[-1]), 2)
        fw_checksum = self._get_firmware_checksum()
        reserved = PacketCreator.int_to_hex_string(0, 2)
        return FrameCreator.create_initialising_frame(
            fw_size, frame_size, total_frames, last_frame, fw_checksum, reserved
        )

    def _create_fw_packets(self):
        frames_packet_list = []
        for frameNumber, frameData in enumerate(self.frames_list):
            frameNumber += 1
            new_frame = FrameCreator.create_fw_frame(frameNumber, frameData)
            frames_packet_list.insert(len(frames_packet_list), new_frame)
        return frames_packet_list

    def _read_fw_download_verified_packet(self, packet):  # TODO
        hex_of_packet = binascii.hexlify(bytes(packet)).decode("utf-8")
        packet_crc_val = PacketCreator._validate_and_return_crc_of_received_packet(
            hex_of_packet)
        PacketCreator._check_received_packet_size(
            packet, PacketType.FwDownloadVerifiedPacket)
        PacketCreator._check_first_byte_of_received_packet(hex_of_packet)
        hex_of_packet = hex_of_packet[10:]
        data_section = int(hex_of_packet.replace(packet_crc_val, ""))
        return data_section == 1

    def _read_fw_version_packet(self, packet):  # TODO
        hex_of_packet = binascii.hexlify(bytes(packet)).decode("utf-8")
        packet_crc_val = PacketCreator._validate_and_return_crc_of_received_packet(
            hex_of_packet)
        PacketCreator._check_received_packet_size(
            packet, PacketType.FwVersionPacket)
        PacketCreator._check_first_byte_of_received_packet(hex_of_packet)
        hex_of_packet = hex_of_packet[10:]
        data_section = hex_of_packet.replace(packet_crc_val, "")
        firmware_name = bytes.fromhex(
            data_section[2:]).decode("utf-8").strip("\x00")
        firmware_version = data_section[:2]
        return firmware_name, firmware_version

    @staticmethod
    def _check_first_byte_of_received_packet(hex_of_packet):
        if "8a" not in hex_of_packet[:2]:
            raise ValueError("first byte not found in received packet")

    @staticmethod
    def _check_received_packet_size(packet, packet_type):
        if packet_type == PacketType.FwDownloadVerifiedPacket:
            if len(packet) != 8:
                raise ValueError(
                    "FwDownloadVerifiedPacket size is incorrect" +
                    str(len(packet))
                )
        if packet_type == PacketType.FwVersionPacket:
            if len(packet) != 23:
                raise ValueError(
                    "FwVersionPacket size is incorrect" + str(len(packet)))

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
        with open(self.bin_file, "rb") as f:
            file_data = f.read()
        checksum_val = b"%02X" % (sum(file_data) & 0xFFFFFFFF)
        return checksum_val.decode("UTF-8").zfill(8)

    def _get_frames_list(self, bin_file):
        with open(bin_file, "rb") as f:
            file_data = f.read()
        file_size = len(file_data)
        frames_list = [
            file_data[i: i + self.frame_length]
            for i in range(0, file_size, self.frame_length)
        ]
        return frames_list

    @staticmethod
    def int_to_hex_string(value, byte_length):
        byte_format = "{:0" + str(byte_length * 2) + "x}"
        return byte_format.format(value)
