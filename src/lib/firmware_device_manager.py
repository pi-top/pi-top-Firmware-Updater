import multiprocessing
from sys import path
from enum import Enum, auto

from ptcommon.logger import PTLogger
from ptcommon.common_ids import FirmwareDeviceID
from ptcommon.firmware_device import FirmwareDevice
from ptcommon.firmware_device import PTInvalidFirmwareDeviceException
path.append("/usr/lib/pt-firmware-updater/")
from firmware_updater import FirmwareUpdater
from file_supervisor import FileSupervisor, FirmwareFileEventManager
from notification_manager import NotificationManager, UpdateStatusEnum


class DeviceInfoKeys(Enum):
    CONNECTED = auto()
    FW_DEVICE = auto()
    FW_UPDATER = auto()
    NOTIFIED = auto()
    UPDATE_AVAILABLE = auto()
    PATH_TO_BINARY = auto()


class FirmwareDeviceManager:
    __devices_status = {}
    file_monitor = None
    queue = None
    FIRMWARE_FILE_PATH = '/usr/lib/pt-firmware-updater/bin/'

    def __init__(self, devices: [FirmwareDeviceID]) -> None:
        self.devices_id_list = devices
        for dev in devices:
            self.__devices_status[dev] = {}
        self.scan_for_connected_devices()
        self.notification_manager = NotificationManager()

    def scan_for_connected_devices(self):
        PTLogger.debug('Scanning for connected firmware devices')

        for dev in self.devices_id_list:
            try:
                fw_device = FirmwareDevice(dev)
                connected = True
                PTLogger.debug('{} is connected'.format(dev))
                self.__devices_status[dev][DeviceInfoKeys.FW_DEVICE] = fw_device
            except (ConnectionError, AttributeError, PTInvalidFirmwareDeviceException) as e:
                PTLogger.warning('{} - {}'.format(dev.name, e))
                connected = False
                self.__devices_status[dev] = {}
            except Exception as e:
                PTLogger.error('{} - {}'.format(dev.name, e))
                connected = False
                self.__devices_status[dev] = {}
            finally:
                self.__devices_status[dev][DeviceInfoKeys.CONNECTED] = connected

    def connected_devices(self) -> [FirmwareDeviceID]:
        return [device_id for device_id in self.__devices_status if self.is_connected(device_id)]

    def is_connected(self, device_id: FirmwareDeviceID) -> bool:
        return self.__devices_status[device_id][DeviceInfoKeys.CONNECTED] if device_id in self.__devices_status else False

    def force_update_if_available(self) -> None:
        PTLogger.info("Forcing update if available")
        for device_id in self.devices_id_list:
            if self.has_update(device_id):
                self.update(device_id)
            self.set_notification_status(device_id, True)

    def has_update(self, device_id: FirmwareDeviceID) -> bool:
        has_updates = False
        if not self.is_connected(device_id):
            PTLogger.info("{} - Not connected. Skipping update check.".format(device_id))
            return has_updates

        try:
            fw_dev = self.__devices_status[device_id][DeviceInfoKeys.FW_DEVICE]
            fw_updater = FirmwareUpdater(fw_dev)
            fw_updater.search_updates()

            has_updates = fw_updater.has_staged_updates()
            path = fw_updater.fw_file_location
        except (ConnectionError, AttributeError, PTInvalidFirmwareDeviceException) as e:
            PTLogger.warning('{} - {}'.format(device_id.name, e))
            has_updates = False
            fw_updater = None
            path = None
        except Exception as e:
            PTLogger.error('{} - {}'.format(device_id.name, e))
            has_updates = False
            fw_updater = None
            path = None
        finally:
            self.set_notification_status(device_id, has_updates)
            self.__devices_status[device_id][DeviceInfoKeys.UPDATE_AVAILABLE] = has_updates
            self.__devices_status[device_id][DeviceInfoKeys.FW_UPDATER] = fw_updater
            self.__devices_status[device_id][DeviceInfoKeys.PATH_TO_BINARY] = path
        return has_updates

    def update(self, device_id: FirmwareDeviceID) -> bool:
        success = False

        if not self.is_connected(device_id):
            PTLogger.info("{} is not connected".format(device_id))
            return success
        if not self.__devices_status[device_id][DeviceInfoKeys.UPDATE_AVAILABLE]:
            PTLogger.info("{} - There's no update available".format(device_id))
            return success

        try:
            fw_updater = self.__devices_status[device_id][DeviceInfoKeys.FW_UPDATER]
            PTLogger.info("{} - Updating firmware".format(device_id))

            if fw_updater.install_updates():
                success = True
                PTLogger.info("{} - Updated firmware successfully to device".format(device_id))
            self.set_notification_status(device_id, True)
            self.notification_manager.notify_user(UpdateStatusEnum.SUCCESS if success else UpdateStatusEnum.FAILURE, device_id)
        except (ConnectionError, AttributeError, PTInvalidFirmwareDeviceException) as e:
            PTLogger.warning('{} - {}'.format(device_id.name, e))
        except Exception as e:
            PTLogger.error('{} - {}'.format(device_id.name, e))

        return success

    def set_notification_status(self, device_id: FirmwareDeviceID, status: bool) -> None:
        self.__devices_status[device_id][DeviceInfoKeys.NOTIFIED] = status

    def already_notified_this_session(self, device_id: FirmwareDeviceID):
        return self.__devices_status[device_id][DeviceInfoKeys.NOTIFIED]

    def notify_user_about_update(self, device_id):
        path_to_binary = self.__devices_status[device_id][DeviceInfoKeys.PATH_TO_BINARY]
        self.notification_manager.notify_user(UpdateStatusEnum.PROMPT, device_id, path_to_binary)
        self.set_notification_status(device_id, True)

    def start_file_supervisor(self) -> None:
        self.queue = multiprocessing.Queue()
        event_manager = FirmwareFileEventManager(self.queue)
        binary_directories = [self.FIRMWARE_FILE_PATH + dev.name for dev in self.devices_id_list]

        self.file_monitor = FileSupervisor(binary_directories, event_manager)
        self.file_monitor.run(threaded=True)

    def update_notification_states_for_new_firmware_files(self) -> None:
        if not self.queue:
            return
        while not self.queue.empty():
            device_id = self.queue.get()
            PTLogger.info("{} - Found new firmware file!".format(device_id))
            self.set_notification_status(device_id, False)
