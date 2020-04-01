import os
import pyinotify
import multiprocessing
from ptcommon.firmware_device import FirmwareDevice
from ptcommon.common_ids import FirmwareDeviceID
from ptcommon.logger import PTLogger


class FileSupervisor(object):
    def __init__(self, path, event_manager: pyinotify.ProcessEvent) -> None:
        if isinstance(path, str):
            path = [path]
        for p in path:
            if not os.path.isdir(p):
                raise AttributeError('Path {} is not a directory'.format(p))

        self.event_manager = event_manager
        self.wm = pyinotify.WatchManager()
        self.wdd = self.wm.add_watch(path, pyinotify.IN_MOVED_TO, rec=True, auto_add=True)

    def run(self, threaded: bool = False) -> None:
        if threaded:
            self.notifier = pyinotify.ThreadedNotifier(self.wm, self.event_manager)
            self.notifier.start()
        else:
            self.notifier = pyinotify.Notifier(self.wm, self.event_manager)
            self.notifier.loop()


class FirmwareFileEventManager(pyinotify.ProcessEvent):
    def __init__(self, queue:  multiprocessing.queues.Queue):
        if not isinstance(queue, multiprocessing.queues.Queue):
            raise AttributeError('Queue is not a multiprocessing Queue')
        self.queue = queue
        super().__init__()

    def process_IN_CREATE(self, event):
        PTLogger.info("---- {} was created".format(event.pathname))
        self.__process_event(event)

    def process_IN_MOVED_TO(self, event):
        PTLogger.info("---- {} was moved".format(event.pathname))
        self.__process_event(event)

    def __process_event(self, event):
        path = event.path
        PTLogger.info('Processing event on file {}'.format(path))

        if os.path.isfile(event.path):
            path = os.path.dirname(path)
        path = os.path.normpath(os.path.join(path, '..'))

        fw_device_str_name = os.path.basename(path)
        fw_device = FirmwareDevice.str_name_to_device_id(fw_device_str_name)
        PTLogger.info('Device to update: {}'.format(fw_device_str_name))
        self.queue.put(fw_device)
