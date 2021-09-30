from enum import Enum, auto
from typing import Dict

from pitop.common.common_ids import FirmwareDeviceID
from pitop.common.common_names import FirmwareDeviceName
from pitop.common.logger import PTLogger
from pitop.common.notifications import NotificationActionManager, send_notification


class UpdateStatusEnum(Enum):
    PROMPT = auto()
    ONGOING = auto()
    SUCCESS = auto()
    SUCCESS_REQUIRES_RESTART = auto()
    FAILURE = auto()


class ActionEnum(Enum):
    HUB_REBOOT = auto()
    REBOOT = auto()
    UPDATE_FW = auto()


class NotificationManager(object):
    NOTIFICATION_TITLE = "Firmware Device Update"
    __REBOOT_CMD = (
        "env SUDO_ASKPASS=/usr/lib/pt-firmware-updater/pwdptfu.sh sudo -A reboot"
    )
    __HUB_REBOOT_CMD = (
        "touch /tmp/.com.pi-top.pi-topd.pt-poweroff.reboot-on-shutdown && "
    )
    "env SUDO_ASKPASS=/usr/lib/pt-firmware-updater/pwdptfu.sh sudo -A shutdown -h now"
    __FW_UPDATE_CMD = "echo OK"

    MESSAGE_DATA = {
        UpdateStatusEnum.SUCCESS: {"icon": "vcs-normal", "timeout": 0, "actions": []},
        UpdateStatusEnum.SUCCESS_REQUIRES_RESTART: {
            "icon": "vcs-normal",
            "timeout": 0,
            "actions": [
                {
                    "devices": [FirmwareDeviceID.pt4_hub],
                    "text": "Reboot Now",
                    "command": ActionEnum.HUB_REBOOT,
                }
            ],
        },
        UpdateStatusEnum.FAILURE: {
            "icon": "messagebox_critical",
            "timeout": 0,
            "actions": [
                {
                    "devices": [
                        FirmwareDeviceID.pt4_hub,
                        FirmwareDeviceID.pt4_foundation_plate,
                        FirmwareDeviceID.pt4_expansion_plate,
                    ],
                    "text": "Reboot Now",
                    "command": ActionEnum.REBOOT,
                }
            ],
        },
        UpdateStatusEnum.PROMPT: {
            "icon": "messagebox_info",
            "timeout": 0,
            "actions": [
                {
                    "devices": [
                        FirmwareDeviceID.pt4_hub,
                        FirmwareDeviceID.pt4_foundation_plate,
                        FirmwareDeviceID.pt4_expansion_plate,
                    ],
                    "text": "Update Now",
                    "command": ActionEnum.UPDATE_FW,
                },
            ],
        },
        UpdateStatusEnum.ONGOING: {
            "icon": "messagebox_info",
            "timeout": 0,
            "actions": [],
        },
    }

    __notification_ids: Dict[FirmwareDeviceID, int] = dict()

    def notify_user(
        self, update_enum: UpdateStatusEnum, device_id: FirmwareDeviceID
    ) -> list:
        if update_enum not in UpdateStatusEnum:
            raise ValueError("{} is not a UpdateStatusEnum".format(update_enum))

        PTLogger.info(
            "Notifying user. Device: {}; enum: {}".format(device_id.name, update_enum)
        )

        notification_output = send_notification(
            title=self.NOTIFICATION_TITLE,
            text=self.__get_notification_message(update_enum, device_id),
            icon_name=self.MESSAGE_DATA[update_enum]["icon"],
            timeout=self.MESSAGE_DATA[update_enum]["timeout"],
            actions_manager=self.__get_action_manager(update_enum, device_id),
            notification_id=self.get_notification_id(device_id),
            capture_notification_id=update_enum
            not in (
                UpdateStatusEnum.FAILURE,
                UpdateStatusEnum.SUCCESS,
                UpdateStatusEnum.SUCCESS_REQUIRES_RESTART,
            ),
        )

        notification_output_list = []
        if notification_output:
            PTLogger.error(notification_output)
            notification_id, *notification_output_list = notification_output.split()
            self.set_notification_id(device_id, notification_id)
        return notification_output_list

    def __get_notification_message(
        self, update_enum: UpdateStatusEnum, device_id: FirmwareDeviceID
    ) -> str:
        device_friendly_name = FirmwareDeviceName[device_id.name].value

        if update_enum is UpdateStatusEnum.SUCCESS:
            return "Your {} has been updated and is ready to use.".format(
                device_friendly_name
            )
        elif update_enum is UpdateStatusEnum.SUCCESS_REQUIRES_RESTART:
            if device_id == FirmwareDeviceID.pt4_hub:
                return "Reboot your {} to apply changes.".format(device_friendly_name)
            else:
                return "Disconnect and reconnect your\n{} to apply changes.".format(
                    device_friendly_name
                )
        elif update_enum is UpdateStatusEnum.PROMPT:
            return "There's a firmware update available\nfor your {}.".format(
                device_friendly_name
            )
        elif update_enum is UpdateStatusEnum.FAILURE:
            msg = (
                "A problem was encountered while attempting\n"
                "to update your {}.\n"
                "Please reboot and try again.\n"
                "If you are repeatedly experiencing\n"
                "this issue, please contact pi-top support.".format(
                    device_friendly_name
                )
            )
            return msg
        elif update_enum is UpdateStatusEnum.ONGOING:
            return "Updating your {}.\nPlease wait for this to finish before\ncontinuing to use your device!".format(
                device_friendly_name
            )

    def __get_action_manager(
        self, update_enum: UpdateStatusEnum, device_id: FirmwareDeviceID
    ) -> NotificationActionManager:
        action_manager = None
        if len(self.MESSAGE_DATA[update_enum]["actions"]) == 0:  # type: ignore
            return action_manager

        action_manager = NotificationActionManager()
        for action in self.MESSAGE_DATA[update_enum]["actions"]:  # type: ignore
            action_enum = action.get("command")
            if action_enum is None:
                continue
            if device_id not in action["devices"]:
                continue

            if action_enum == ActionEnum.HUB_REBOOT:
                command = self.__HUB_REBOOT_CMD
            elif action_enum == ActionEnum.REBOOT:
                command = self.__REBOOT_CMD
            elif action_enum == ActionEnum.UPDATE_FW:
                command = self.__FW_UPDATE_CMD

            action_manager.add_action(
                call_to_action_text=action["text"], command_str=command
            )
        return action_manager

    def get_notification_id(self, device_id: FirmwareDeviceID) -> int:
        id = self.__notification_ids.get(device_id)
        return -1 if not id else id

    def set_notification_id(self, device_id: FirmwareDeviceID, id: str) -> None:
        try:
            self.__notification_ids[FirmwareDeviceID, device_id] = int(id)
        except ValueError:
            pass
