import binascii
from PyCRC.CRC16Kermit import CRC16Kermit


def get_crc16(frame_data):
    crc_val = CRC16Kermit().calculate(binascii.unhexlify(frame_data))
    return crc_val.to_bytes(2, byteorder="little").hex()


class FrameCreator(object):
    @staticmethod
    def create_initialising_frame(fw_size, frame_size, total_frames, last_frame, fw_checksum, reserved):
        frame_length = str(format(7 + int(frame_size), '02x').zfill(4))
        prefix = "8A" + frame_length + "01A1"
        data_section = fw_size + frame_size + \
            total_frames + last_frame + fw_checksum + reserved
        crc = get_crc16(prefix + data_section)
        return list(bytearray.fromhex(prefix + data_section + crc))

    @staticmethod
    def create_fw_frame(frame_number, frame_data):
        frame_length = str(format(9 + len(frame_data), '02x').zfill(4))
        prefix = "8A" + frame_length + "01A2"
        hex_string_frame_number = format(frame_number, '04x')
        data_section = hex_string_frame_number + frame_data.hex()
        crc = get_crc16(prefix + data_section).zfill(4)
        return list(bytearray.fromhex(prefix + data_section + crc))
