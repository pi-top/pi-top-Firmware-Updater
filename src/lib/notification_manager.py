from enum import Enum
from subprocess import getoutput

from ptcommon.logger import PTLogger
from ptcommon.notifications import send_notification


class UpdateStatusEnum(Enum):
    WARNING = 0
    SUCCESS = 1
    FAILURE = 2


class NotificationManager(object):
    NOTIFICATION_TITLE = "Firmware Device Update"

    MESSAGE_DATA = {
        UpdateStatusEnum.SUCCESS: {
            "icon": "vcs-normal",
            "timeout": 10000,
        },
        UpdateStatusEnum.FAILURE: {
            "icon": "messagebox_critical",
            "timeout": 10000
        },
        UpdateStatusEnum.WARNING: {
            "icon": "messagebox_info",
            "timeout": 15000
        }
    }

    def notify_user(self, update_enum: UpdateStatusEnum, device: str) -> None:
        if update_enum not in UpdateStatusEnum:
            PTLogger.debug("{} is not a UpdateStatusEnum".format(update_enum))
            return

        PTLogger.info("notify_send - device: {}, enum: {}".format(device, update_enum))

        send_notification(
            title=self.NOTIFICATION_TITLE,
            text=self.__get_notification_message(update_enum, device),
            icon_name=self.MESSAGE_DATA[update_enum]["icon"],
            timeout=self.MESSAGE_DATA[update_enum]["timeout"]
        )

    def __get_notification_message(self, update_enum: UpdateStatusEnum, device: str) -> str:
        if update_enum is UpdateStatusEnum.SUCCESS:
            if device == "pt4_hub":
                return "Reboot your pi-top to apply changes"
            elif device in ("pt4_expansion_plate", "pt4_foundation_plate"):
                return "Disconnect and reconnect your plate to apply changes"
            return "Successfully updated {}".format(device)
        elif update_enum is UpdateStatusEnum.WARNING:
            return "Installing firmware update to {}.\nPlease, don't disconnect.".format(device)
        elif update_enum is UpdateStatusEnum.FAILURE:
            return "There were errors while updating {}.".format(device)
