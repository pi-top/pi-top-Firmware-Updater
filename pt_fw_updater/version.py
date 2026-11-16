from importlib.metadata import version

__version__ = "N/A"
try:
    __version__ = version("pt-firmware-updater")
except Exception:
    pass
