=======================
pi-top Firmware Updater
=======================

A desktop notification-based automated pi-top firmware updating application.

--------------------
Build Status: Latest
--------------------

.. image:: https://img.shields.io/github/workflow/status/pi-top/pi-top-Firmware-Updater/Test%20and%20Build%20Packages%20on%20All%20Commits
   :alt: GitHub Workflow Status

.. image:: https://img.shields.io/github/v/tag/pi-top/pi-top-Firmware-Updater
    :alt: GitHub tag (latest by date)

.. image:: https://img.shields.io/github/v/release/pi-top/pi-top-Firmware-Updater
    :alt: GitHub release (latest by date)

.. https://img.shields.io/codecov/c/gh/pi-top/pi-top-Firmware-Updater?token=hfbgB9Got4
..   :alt: Codecov

-----
About
-----

This application aims to provide an easy-to-use interface for keeping pi-top hub firmware up-to-date.

`pt-firmware-updater` is included out-of-the-box with pi-topOS.

Ensure that you keep your system up-to-date to enjoy the latest features and bug fixes.

This application is installed as a Python 3 module that is managed by a systemd service, configured to automatically run on startup and restart during software updates.

------------
Installation
------------

`pt-firmware-updater` is installed out of the box with pi-topOS, which is available from
pi-top.com_. To install on Raspberry Pi OS or other operating systems, check out the `Using pi-top Hardware with Raspberry Pi OS`_ page on the pi-top knowledge base.

.. _pi-top.com: https://www.pi-top.com/products/os/

.. _Using pi-top Hardware with Raspberry Pi OS: https://pi-top.com/pi-top-rpi-os

---------
More Info
---------

Upgrade priorities (in order):

* Candidate major version is newer
* Candidate minor version is newer
* Candidate is release version; current is preview
* Candidate is newer preview version

*NOTE: differing major schematic versions mean that the firmware is* **NOT** *compatible and are treated as separate devices.*

~~~~~~~~~~~~~~~~~~~~
Directory convention
~~~~~~~~~~~~~~~~~~~~

`pt_fw_updater/bin/<device_name>`

~~~~~~~~~~~~~~~~~~~
Filename convention
~~~~~~~~~~~~~~~~~~~

> `<device_name>-v<maj_ver>.<min_ver>-sch<sch_maj_ver>-<type>[-<preview_build_timestamp>].bin`


* `*_ver` (required)
    * Major and minor firmware versions must be integers, and must start with '`v`'
    * Schematic major version must be an integer, and must start with '`sch`'

* `type` (required)
    * Type of release takes the form of `release` or `preview`

* `preview_build_timestamp` (optional)
    * Integer representation of unix timestamp in seconds
    * Used to determine if an upgrade is available between preview versions

Examples:

``
pt4_expansion_plate/pt4_expansion_plate-v21.1-sch2-release.bin
pt4_expansion_plate/pt4_expansion_plate-v21.2-sch2-preview-1591213651.bin
pt4_expansion_plate/pt4_expansion_plate-v21.2-sch3-preview-1591213651.bin
pt4_expansion_plate/pt4_expansion_plate-v21.2-sch2-release.bin
pt4_expansion_plate/pt4_expansion_plate-v21.2-sch3-release.bin
``
