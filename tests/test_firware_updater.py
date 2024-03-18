from os import path, remove
from pathlib import Path
from sys import modules
from unittest import TestCase
from unittest.mock import ANY, Mock, patch

mock_command_runner = modules["pitop.common.command_runner"] = Mock()
mock_logger = modules["pitop.common.logger"] = Mock()
mock_i2c = modules["pitop.common.i2c_device"] = Mock()

import core.notification_manager
import pt_firmware_updater as pt_firmware_updater
from pitop.common.common_ids import FirmwareDeviceID
from pitop.common.firmware_device import FirmwareDevice

from .core.firmware_file_object import FirmwareFileObject
from .core.firmware_updater import PTInvalidFirmwareFile
from .utils import dotdict


class FirmwareUpdaterFunctionsTestCase(TestCase):
    def test_main_fails_with_invalid_files(self):
        for _path in ("/tmp", "/tmp/not_existant_file"):
            parsed_args = dotdict({"path": _path})
            with self.assertRaises(ValueError):
                pt_firmware_updater.main(parsed_args)

    def test_get_device_data_returns_tuple_with_correct_values(self):
        for device_str in ("pt4_hub", "pt4_foundation_plate", "pt4_expansion_plate"):
            device_enum, device_addr = pt_firmware_updater.get_device_data(device_str)
            self.assertTrue(isinstance(device_enum, FirmwareDeviceID))
            self.assertTrue((isinstance(device_addr, int)))

    def test_get_device_data_raises_error_on_incorrect_device(self):
        for device_str in ("hub", "qwe", 123):
            with self.assertRaises(AttributeError):
                pt_firmware_updater.get_device_data(device_str)

    def test_create_fw_device_raises_on_invalid_device_id(self):
        for device_id in ("hub", "qwe", 123):
            with self.assertRaises(AttributeError):
                pt_firmware_updater.create_firmware_device(device_id)

    def test_create_fw_device_succeeds_if_connected(self):
        device_to_mock = FirmwareDeviceID.pt4_hub
        FirmwareDevice.get_part_name = Mock()
        FirmwareDevice.get_part_name.return_value = FirmwareDevice.device_info.get(
            device_to_mock
        ).get("part_name")

        fw_device = pt_firmware_updater.create_firmware_device(device_to_mock)
        self.assertTrue(isinstance(fw_device, FirmwareDevice))

    def test_create_fw_updater_calls_create_fw_device(self):
        device_to_mock = FirmwareDeviceID.pt4_hub
        FirmwareDevice.get_part_name = Mock()
        FirmwareDevice.get_part_name.return_value = FirmwareDevice.device_info.get(
            device_to_mock
        ).get("part_name")

        pt_firmware_updater.FirmwareUpdater.set_current_device_info = Mock()

        with patch.object(
            pt_firmware_updater,
            "create_firmware_device",
            wraps=pt_firmware_updater.create_firmware_device,
        ) as wrapped_call:
            pt_firmware_updater.create_fw_updater_object(device_to_mock)
            wrapped_call.assert_called_with(device_to_mock)

    def test_create_fw_updater_raises_on_invalid_device_id(self):
        for device_id in ("hub", "qwe", 123):
            with self.assertRaises(AttributeError):
                pt_firmware_updater.create_fw_updater_object(device_id)

    def test_create_fw_updater_succeeds_if_connected(self):
        device_to_mock = FirmwareDeviceID.pt4_hub
        FirmwareDevice.get_part_name = Mock(
            side_effect=[
                FirmwareDevice.device_info.get(device_to_mock).get("part_name")
            ]
        )
        pt_firmware_updater.FirmwareUpdater.set_current_device_info = Mock()

        fw_updater = pt_firmware_updater.create_fw_updater_object(device_to_mock)
        self.assertTrue(isinstance(fw_updater, pt_firmware_updater.FirmwareUpdater))


class FirmwareUpdaterFlowsTestCase(TestCase):
    def setUp(self):
        self.device_to_mock = FirmwareDeviceID.pt4_hub
        self.path_to_fw_device = "/tmp/pt4_hub-v5.1-sch8-release.bin"
        self.path_to_fw_to_upgrade = "/tmp/pt4_hub-v5.2-sch8-release.bin"

        for f in (self.path_to_fw_device, self.path_to_fw_to_upgrade):
            Path(f).touch()

        # Mock internals
        FirmwareDevice.get_part_name = Mock(
            side_effect=[
                FirmwareDevice.device_info.get(self.device_to_mock).get("part_name")
            ]
        )
        pt_firmware_updater.FirmwareUpdater.set_current_device_info = Mock()
        pt_firmware_updater.FirmwareUpdater.install_updates = Mock(
            return_value=(True, False)
        )
        pt_firmware_updater.FirmwareUpdater.device_info = FirmwareFileObject.from_file(
            self.path_to_fw_device
        )
        pt_firmware_updater.FirmwareUpdater.fw_downloaded_successfully = Mock(
            return_value=False
        )
        self.send_notification_mock = core.notification_manager.send_notification = (
            Mock(return_value="1")
        )

    def tearDown(self):
        for f in (self.path_to_fw_device, self.path_to_fw_to_upgrade):
            if path.isfile(f):
                remove(f)

    def test_downgrade_succeeds_with_force_parameter(self):
        parsed_args = dotdict(
            {
                "path": self.path_to_fw_device,
                "device": self.device_to_mock.name,
                "notify_user": False,
                "force": True,
            }
        )
        try:
            pt_firmware_updater.main(parsed_args)
        except Exception as e:
            self.fail(f"Unexpected exception: {e}")

    def test_fails_when_trying_to_downgrade_without_force_parameter(self):
        parsed_args = dotdict(
            {
                "path": self.path_to_fw_device,
                "device": self.device_to_mock.name,
                "notify_user": False,
                "force": False,
            }
        )

        with self.assertRaises(PTInvalidFirmwareFile):
            pt_firmware_updater.main(parsed_args)

    def test_notifies_user_if_notify_param_is_provided(self):
        parsed_args = dotdict(
            {
                "path": self.path_to_fw_to_upgrade,
                "device": self.device_to_mock.name,
                "notify_user": True,
                "force": False,
            }
        )

        pt_firmware_updater.main(parsed_args)
        self.send_notification_mock.assert_called_with(
            title="Firmware Device Update",
            text="There's a firmware update available\nfor your pi-top [4].",
            icon_name="messagebox_info",
            timeout=0,
            notification_id=-1,
            capture_notification_id=True,
            actions_manager=ANY,
        )

    def test_doesnt_update_if_user_rejects_notification(self):
        parsed_args = dotdict(
            {
                "path": self.path_to_fw_to_upgrade,
                "device": self.device_to_mock.name,
                "notify_user": True,
                "force": False,
            }
        )

        with patch.object(
            pt_firmware_updater, "apply_update", wraps=pt_firmware_updater.apply_update
        ) as wrapped_apply_update:
            pt_firmware_updater.main(parsed_args)
            wrapped_apply_update.assert_not_called()

    def test_updates_if_user_accepts_notification(self):
        core.notification_manager.send_notification = Mock(return_value="0\nOK")

        parsed_args = dotdict(
            {
                "path": self.path_to_fw_to_upgrade,
                "device": self.device_to_mock.name,
                "notify_user": True,
                "force": False,
            }
        )

        with patch.object(
            pt_firmware_updater, "apply_update", wraps=pt_firmware_updater.apply_update
        ) as wrapped_apply_update:
            pt_firmware_updater.main(parsed_args)
            wrapped_apply_update.assert_called_once()

    def test_notifies_user_if_update_failed(self):
        self.send_notification_mock = core.notification_manager.send_notification = (
            Mock(return_value="0\nOK")
        )
        pt_firmware_updater.apply_update = Mock(return_value=[False, False])

        parsed_args = dotdict(
            {
                "path": self.path_to_fw_to_upgrade,
                "device": self.device_to_mock.name,
                "notify_user": True,
                "force": False,
            }
        )

        pt_firmware_updater.main(parsed_args)
        text_fields = [
            "A problem was encountered while attempting",
            "to update your pi-top [4].",
            "Please reboot and try again.",
            "If you are repeatedly experiencing",
            "this issue, please contact pi-top support.",
        ]
        self.send_notification_mock.assert_called_with(
            title="Firmware Device Update",
            text="\n".join(text_fields),
            icon_name="messagebox_critical",
            timeout=0,
            notification_id=-1,
            capture_notification_id=False,
            actions_manager=ANY,
        )

    def test_notifies_user_if_update_succeeds(self):
        self.send_notification_mock = core.notification_manager.send_notification = (
            Mock(return_value="0\nOK")
        )
        pt_firmware_updater.apply_update = Mock(return_value=[True, False])

        parsed_args = dotdict(
            {
                "path": self.path_to_fw_to_upgrade,
                "device": self.device_to_mock.name,
                "notify_user": True,
                "force": False,
            }
        )
        pt_firmware_updater.main(parsed_args)
        self.send_notification_mock.assert_called_with(
            title="Firmware Device Update",
            text="Your pi-top [4] has been updated and is ready to use.",
            icon_name="vcs-normal",
            timeout=0,
            notification_id=-1,
            capture_notification_id=False,
            actions_manager=ANY,
        )

    def test_notifies_user_about_required_reboot(self):
        self.send_notification_mock = core.notification_manager.send_notification = (
            Mock(return_value="0\nOK")
        )
        pt_firmware_updater.apply_update = Mock(return_value=[True, True])

        parsed_args = dotdict(
            {
                "path": self.path_to_fw_to_upgrade,
                "device": self.device_to_mock.name,
                "notify_user": True,
                "force": False,
            }
        )
        pt_firmware_updater.main(parsed_args)
        self.send_notification_mock.assert_called_with(
            title="Firmware Device Update",
            text="Reboot your pi-top [4] to apply changes.",
            icon_name="vcs-normal",
            timeout=0,
            notification_id=-1,
            capture_notification_id=False,
            actions_manager=ANY,
        )
