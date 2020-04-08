/*
	pt-i2cdetect.c - a modified version of i2cdetect

    i2cdetect.c - a user-space program to scan for I2C devices
    Copyright (C) 1999-2004  Frodo Looijaard <frodol@dds.nl>, and
                             Mark D. Studebaker <mdsxyz123@yahoo.com>
    Copyright (C) 2004-2012  Jean Delvare <khali@linux-fr.org>

    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 2 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program; if not, write to the Free Software
    Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
    MA 02110-1301 USA.
*/

#include <sys/ioctl.h>
#include <errno.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <linux/i2c.h>
#include <linux/i2c-dev.h>
#include <i2c/smbus.h>
#include "i2cbusses.h"
#include "../version.h"

#define MODE_QUICK	1
#define MODE_READ	2

static void help(void)
{
	fprintf(stderr, "Usage: pt-i2cdetect I2C_ADDRESS\n");
}

static int scan_i2c_bus(int file, int address)
{
	int cmd, res;

	if ((address >= 0x30 && address <= 0x37)
	 || (address >= 0x50 && address <= 0x5F))
	 	cmd = MODE_READ;
	else
		cmd = MODE_QUICK;

	/* Set slave address */
	if (ioctl(file, I2C_SLAVE, address) < 0) {
		if (errno == EBUSY) {
			return -1;
		} else {
			fprintf(stderr, "Error: Could not set "
				"address to 0x%02x: %s\n", address,
				strerror(errno));
			return -1;
		}
	}

	/* Probe this address */
	switch (cmd) {
	default: /* MODE_QUICK */
		/* This is known to corrupt the Atmel AT24RF08
		   EEPROM */
		res = i2c_smbus_write_quick(file,
		      I2C_SMBUS_WRITE);
		break;
	case MODE_READ:
		/* This is known to lock SMBus on various
		   write-only chips (mainly clock chips) */
		res = i2c_smbus_read_byte(file);
		break;
	}

	if (res < 0)
		return -1;
	else
		return 0;
}

int main(int argc, char *argv[])
{
	char *end;
	int i2cbus, file, address, res;
	char filename[20];
	int first = 0x03, last = 0x77;

	i2cbus = lookup_i2c_bus("1");
	if (i2cbus < 0) {
		help();
		exit(2);
	}

	if (argc == 2) {
		int tmp;

		tmp = strtol(argv[1], &end, 0);
		if (*end) {
			fprintf(stderr, "Error: I2C_ADDRESS argment not a "
				"number!\n");
			help();
			exit(3);
		}
		if (tmp < first || tmp > last) {
			fprintf(stderr, "Error: I2C_ADDRESS argument out of range "
				"(0x%02x-0x%02x)!\n", first, last);
			help();
			exit(4);
		}
		address = tmp;
	} else {
		help();
		exit(5);
	}

	file = open_i2c_dev(i2cbus, filename, sizeof(filename), 0);
	if (file < 0) {
		exit(6);
	}

	res = scan_i2c_bus(file, address);

	close(file);

	exit(res?1:0);
}
