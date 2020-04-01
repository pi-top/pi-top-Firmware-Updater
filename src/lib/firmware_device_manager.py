import multiprocessing
from enum import Enum, auto

from ptcommon.logger import PTLogger
from ptcommon.common_ids import FirmwareDeviceID
from ptcommon.firmware_device import FirmwareDevice
from ptcommon.firmware_device import PTInvalidFirmwareDeviceException
path.append("/usr/lib/pt-firmware-updater/")
from firmware_updater import FirmwareUpdater
from file_supervisor import FileSupervisor, FirmwareFileEventManager


class DeviceInfoKeys(Enum):
    CONNECTED = auto()
    FW_DEVICE = auto()
    FW_UPDATER = auto()
    NOTIFIED = auto()
    UPDATE_AVAILABLE = auto()


class FirmwareDeviceManager:
    __device_info = {}
    file_monitor = None
    queue = None
    FIRMWARE_FILE_PATH = '/usr/lib/pt-firmware-updater/bin/'

    def __init__(self, devices):
        self.devices = devices
        for dev in devices:
            self.__device_info[dev] = {}
        self.scan()

    def scan(self, packet_interval=None):
        PTLogger.debug('Scanning for connected firmware devices')

        for dev in self.devices:
            try:
                fw_device = FirmwareDevice(dev, packet_interval)
                connected = True
                PTLogger.debug('{} is connected'.format(dev))
                self.__device_info[dev][DeviceInfoKeys.FW_DEVICE] = fw_device
            except (ConnectionError, AttributeError, PTInvalidFirmwareDeviceException) as e:
                PTLogger.warning('{} - {}'.format(dev.name, e))
                connected = False
                self.__device_info[dev] = {}
            except Exception as e:
                PTLogger.error('{} - {}'.format(dev.name, e))
                connected = False
                self.__device_info[dev] = {}
            finally:
                self.__device_info[dev][DeviceInfoKeys.CONNECTED] = connected

    def connected_devices(self):
        return [device_id for device_id in self.__device_info if self.is_connected(device_id)]

    def is_connected(self, device: FirmwareDeviceID) -> bool:
        return self.__device_info[device]['connected'] if device in self.__device_info else False

    def force_update_if_available(self):
        for device_id in self.devices:
            if self.has_update(device_id):
                self.update(device_id)
            self.set_notification_status(device_id, True)

    def has_update(self, device_id: FirmwareDeviceID) -> bool:
        has_updates = False
        if not self.is_connected(device_id):
            return has_updates

        try:
            fw_dev = self.__device_info[device_id][DeviceInfoKeys.FW_DEVICE]
            fw_updater = FirmwareUpdater(fw_dev)
            has_updates = fw_updater.update_available()
            PTLogger.info('{} - There are updates available.'.format(device_id))
            del fw_updater
        except (ConnectionError, AttributeError, PTInvalidFirmwareDeviceException) as e:
            PTLogger.warning('{} - {}'.format(device_id.name, e))
            has_updates = False
        except Exception as e:
            PTLogger.error('{} - {}'.format(device_id.name, e))
            has_updates = False
        finally:
            self.set_notification_status(device_id, has_updates)
            self.__device_info[device_id][DeviceInfoKeys.UPDATE_AVAILABLE] = has_updates
        return has_updates

    def update(self, device_id: FirmwareDeviceID) -> bool:
        success = False
        if not self.is_connected(device_id):
            PTLogger.info("{} is not connected".format(device_id))
            return success
        if not self.__device_info[device_id][DeviceInfoKeys.UPDATE_AVAILABLE]:
            PTLogger.info("{} - There's no update available".format(device_id))
            return success

        try:
            fw_device = self.__device_info[device_id][DeviceInfoKeys.FW_DEVICE]
            fw_updater = FirmwareUpdater(fw_device)
            PTLogger.info("{} - Updating firmware".format(device_id))
            if fw_updater.install_updates():
                success = True
                PTLogger.info("{} - Updated firmware successfully to device".format(device_id))
            self.set_notification_status(device_id, True)
            del fw_updater
        except (ConnectionError, AttributeError, PTInvalidFirmwareDeviceException) as e:
            PTLogger.warning('{} - {}'.format(device_id.name, e))
        except Exception as e:
            PTLogger.error('{} - {}'.format(device_id.name, e))

        return success

    def set_notification_status(self, device, status):
        self.__device_info[device][DeviceInfoKeys.NOTIFIED] = status

    def was_notified(self, device):
        return self.__device_info[device][DeviceInfoKeys.NOTIFIED]

    def start_file_supervisor(self):
        self.queue = multiprocessing.Queue()
        event_manager = FirmwareFileEventManager(shared_queue)
        binary_directories = [self.FIRMWARE_FILE_PATH + dev.name for dev in self.devices]

        self.file_monitor = FileSupervisor(binary_directories, event_manager)
        self.file_monitor.run(threaded=True)

    def new_files_in_folder(self) -> bool:
        found_new_files = False
        if not self.queue:
            return found_new_files

        while not self.queue.empty():
            found_new_files = True
            device_id = self.queue.get()
            PTLogger.info("{} - Found new firmware file!".format(device_id))
            self.set_notification_status(device_id, False)

        return found_new_files
