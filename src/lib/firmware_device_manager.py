import multiprocessing
from sys import path
from enum import Enum, auto
from subprocess import run

from ptcommon.logger import PTLogger
from ptcommon.common_ids import FirmwareDeviceID
from ptcommon.firmware_device import FirmwareDevice, PTInvalidFirmwareDeviceException
path.append("/usr/lib/pt-firmware-updater/")
from firmware_updater import FirmwareUpdater, PTInvalidFirmwareFile, PTUpdatePending
from file_supervisor import FileSupervisor, FirmwareFileEventManager
from notification_manager import NotificationManager, UpdateStatusEnum


class DeviceInfoKeys(Enum):
    FW_DEVICE = auto()
    FW_UPDATER = auto()
    NOTIFIED = auto()
    UPDATE_AVAILABLE = auto()
    PATH_TO_BINARY = auto()


class FirmwareDeviceManager:
    __devices_status = {}
    file_monitor = None
    queue = None
    FIRMWARE_FILE_PATH = '/lib/firmware/pi-top/'

    def __init__(self, devices: [FirmwareDeviceID]) -> None:
        self.devices_id_list = devices
        self.notification_manager = NotificationManager()

    def scan_for_connected_devices(self) -> None:
        PTLogger.debug('Scanning for connected firmware devices')

        def i2c_addr_found(addr):
            # TODO: add capturing of exit code to run_command, use that
            return run(["pt-i2cdetect", str(addr)], timeout=1).returncode == 0

        def add_device_if_newly_connected(device_id):
            PTLogger.debug('{} is connected'.format(device_id))
            if device_id not in self.__devices_status:
                PTLogger.info('{} is newly connected'.format(device_id))
                self.__devices_status[device_id] = {}
                self.__devices_status[device_id][DeviceInfoKeys.FW_DEVICE] = fw_device

        def remove_device_if_newly_disconnected(device_id):
            PTLogger.debug('{} is not connected'.format(device_id))
            if device_id in self.__devices_status:
                PTLogger.info('{} is newly disconnected'.format(device_id))
                del self.__devices_status[device_id]

        # Call 'pt-i2cdetect' for the I2C address of each possible device
        for device_id in self.devices_id_list:
            addr = FirmwareDevice.device_info[device_id]['i2c_addr']

            device_connected = False
            if i2c_addr_found(addr):
                try:
                    fw_device = FirmwareDevice(device_id)

                    device_connected = True
                except (ConnectionError, AttributeError) as e:
                    PTLogger.warning(
                        '{} - Exception when attempting to create firmware device: {}'.format(device_id.name, e))
                except PTInvalidFirmwareDeviceException as e:
                    # Probably just probing for the wrong device at the same address - nothing to worry about
                    PTLogger.debug('{} - Invalid firmware device exception: {}'.format(device_id.name, e))
                except Exception as e:
                    PTLogger.error('{} - Generic exception when attempting to create firmware device: {}'.format(device_id.name, e))
                finally:
                    if device_connected:
                        add_device_if_newly_connected(device_id)
                    else:
                        remove_device_if_newly_disconnected(device_id)
            else:
                remove_device_if_newly_disconnected(device_id)

    def connected_devices(self) -> [FirmwareDeviceID]:
        return [device_id for device_id in self.__devices_status if self.is_connected(device_id)]

    def is_connected(self, device_id: FirmwareDeviceID) -> bool:
        return device_id in self.__devices_status

    def force_update_if_available(self) -> None:
        PTLogger.debug("Forcing update if available")
        for device_id in self.__devices_status:
            if self.has_update(device_id):
                self.update(device_id)
            self.set_notification_status(device_id, True)

    def has_update(self, device_id: FirmwareDeviceID, path: str = "") -> bool:
        has_updates = False
        if not self.is_connected(device_id):
            PTLogger.info("{} - Not connected. Skipping update check.".format(device_id))
            return has_updates

        got_exception = False
        try:
            fw_dev = self.__devices_status[device_id][DeviceInfoKeys.FW_DEVICE]
            fw_updater = FirmwareUpdater(fw_dev)
            if path:
                fw_updater.verify_and_stage_file(path)
            else:
                fw_updater.search_updates()

            has_updates = fw_updater.has_staged_updates()
            path = fw_updater.fw_file_location
        except (ConnectionError, AttributeError, PTInvalidFirmwareDeviceException) as e:
            PTLogger.warning('{} - Exception while checking for update: {}'.format(device_id.name, e))
            got_exception = True
        except PTInvalidFirmwareFile as e:
            PTLogger.info(
                '{} - Skipping update check: no valid candidate firmware'.format(device_id.name))
            got_exception = True
        except PTUpdatePending as e:
            PTLogger.info(
                '{} - Skipping update check: {}'.format(device_id.name, e))
            got_exception = True
        except Exception as e:
            PTLogger.error(
                '{} - Generic exception while checking for update: {}'.format(device_id.name, e))
            got_exception = True
        finally:
            if got_exception:
                has_updates = False
                fw_updater = None
                path = None
            self.set_notification_status(device_id, has_updates)
            self.__devices_status[device_id][DeviceInfoKeys.UPDATE_AVAILABLE] = has_updates
            self.__devices_status[device_id][DeviceInfoKeys.FW_UPDATER] = fw_updater
            self.__devices_status[device_id][DeviceInfoKeys.PATH_TO_BINARY] = path
        return has_updates

    def update(self, device_id: FirmwareDeviceID) -> bool:
        success = False

        if not self.is_connected(device_id):
            PTLogger.warning("{} is not connected".format(device_id))
            return success
        if not self.__devices_status[device_id][DeviceInfoKeys.UPDATE_AVAILABLE]:
            PTLogger.warning("{} - There's no update available".format(device_id))
            return success

        try:
            self.notification_manager.notify_user(UpdateStatusEnum.ONGOING, device_id)
            fw_updater = self.__devices_status[device_id][DeviceInfoKeys.FW_UPDATER]
            PTLogger.info("{} - Updating firmware".format(device_id))

            if fw_updater.install_updates():
                success = True
                PTLogger.info("{} - Updated firmware successfully to device".format(device_id))
            self.set_notification_status(device_id, True)
        except (ConnectionError, AttributeError, PTInvalidFirmwareDeviceException) as e:
            PTLogger.warning(
                '{} - Exception while trying to update: {}'.format(device_id.name, e))
        except Exception as e:
            PTLogger.error(
                '{} - Generic exception while trying to update: {}'.format(device_id.name, e))
        finally:
            self.notification_manager.notify_user(
                UpdateStatusEnum.SUCCESS if success else UpdateStatusEnum.FAILURE,
                device_id)

        return success

    def set_notification_status(self, device_id: FirmwareDeviceID, status: bool) -> None:
        self.__devices_status[device_id][DeviceInfoKeys.NOTIFIED] = status

    def already_notified_this_session(self, device_id: FirmwareDeviceID):
        notified = self.__devices_status[device_id].get(DeviceInfoKeys.NOTIFIED)
        return notified == True

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
