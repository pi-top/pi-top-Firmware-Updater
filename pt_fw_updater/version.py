from importlib.metadata import version

__version__ = "N/A"
try:
    __version__ = version("pt_fw_updater")
except Exception:
    pass
