from enum import Enum, auto
from subprocess import getoutput

from ptcommon.logger import PTLogger
from ptcommon.notifications import send_notification, NotificationActionManager
from ptcommon.firmware_device import FirmwareDevice
from ptcommon.common_ids import FirmwareDeviceID
from ptcommon.common_names import FirmwareDeviceName


class UpdateStatusEnum(Enum):
    PROMPT = auto()
    SUCCESS = auto()
    FAILURE = auto()


class NotificationManager(object):
    NOTIFICATION_TITLE = "Firmware Device Update"

    MESSAGE_DATA = {
        UpdateStatusEnum.SUCCESS: {
            "icon": "vcs-normal",
            "timeout": 0,
            "actions": [
                {
                    "device": [FirmwareDeviceID.pt4_hub],
                    "text": "Reboot Now",
                    "command": "env SUDO_ASKPASS=/usr/lib/pt-firmware-updater/pwdptfu.sh sudo -A reboot"
                }
            ]
        },
        UpdateStatusEnum.FAILURE: {
            "icon": "messagebox_critical",
            "timeout": 0,
            "actions": []
        },
        UpdateStatusEnum.PROMPT: {
            "icon": "messagebox_info",
            "timeout": 0,
            "actions": [
                {
                    "device": [FirmwareDeviceID.pt4_hub, FirmwareDeviceID.pt4_foundation_plate, FirmwareDeviceID.pt4_expansion_plate],
                    "text": "Upgrade Now",
                    "command": "env SUDO_ASKPASS=/usr/lib/pt-firmware-updater/pwdptfu.sh sudo -A /usr/bin/pt-firmware-updater"
                },
            ]
        }
    }

    self.__notification_memory = {
        UpdateStatusEnum.SUCCESS: {},
        UpdateStatusEnum.FAILURE: {},
        UpdateStatusEnum.PROMPT: {},
    }

    def notify_user(self, update_enum: UpdateStatusEnum, device_id: FirmwareDeviceID, path_to_fw: str = "") -> None:
        if update_enum not in UpdateStatusEnum:
            PTLogger.debug("{} is not a UpdateStatusEnum".format(update_enum))
            return

        PTLogger.info("notify_user() w/device: {}, enum: {}".format(device_id.value, update_enum))

        if update_enum == UpdateStatusEnum.PROMPT:
            self.__notification_memory[update_enum][device_id] = ""

        notification_id = send_notification(
            title=self.NOTIFICATION_TITLE,
            text=self.__get_notification_message(update_enum, device_id),
            icon_name=self.MESSAGE_DATA[update_enum]["icon"],
            timeout=self.MESSAGE_DATA[update_enum]["timeout"],
            actions_manager=self.__get_action_manager(update_enum, device_id, path_to_fw),
            notification_id=self.__get_notification_id(update_enum, device_id)
        )

        self.__notification_memory[update_enum][device_id] = notification_id

    def __get_notification_message(self, update_enum: UpdateStatusEnum, device_id: FirmwareDeviceID) -> str:
        device_friendly_name = FirmwareDeviceName[device_id.name].value

        if update_enum is UpdateStatusEnum.SUCCESS:
            if device_id == FirmwareDeviceID.pt4_hub:
                return "Reboot your {} to apply changes".format(device_friendly_name)
            elif device_id in (FirmwareDeviceID.pt4_expansion_plate, FirmwareDeviceID.pt4_foundation_plate):
                return "Disconnect and reconnect your\n{} to apply changes".format(device_friendly_name)
        elif update_enum is UpdateStatusEnum.PROMPT:
            return "There's a firmware update available\nfor your {}.".format(device_friendly_name)
        elif update_enum is UpdateStatusEnum.FAILURE:
            return "There were errors while updating\nyour {}.".format(device_friendly_name)

    def __get_action_manager(self, update_enum: UpdateStatusEnum, device_id: FirmwareDeviceID, path_to_fw: str = "") -> NotificationActionManager:
        action_manager = None
        if len(self.MESSAGE_DATA[update_enum]['actions']) == 0:
            return action_manager

        action_manager = NotificationActionManager()
        for action in self.MESSAGE_DATA[update_enum]['actions']:
            if action["device"] != device_id:
                continue

            command = action["command"]
            command += " -d {}".format(device_id.name)
            if path_to_fw:
                command += " --path {}".format(path_to_fw)

            action_manager.add_action(
                call_to_action_text=action["text"],
                command_str=command)
        return action_manager

    def __get_notification_id(self, update_enum: UpdateStatusEnum, device_id: FirmwareDeviceID) -> str:
        if device_id not in self.__notification_memory[update_enum]:
            return ""
        return self.__notification_memory[update_enum][device_id]
