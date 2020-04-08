#!/bin/bash

# sudo apt install -y libi2c-dev

DIR="$(pwd)"
BUILD_DIR="${DIR}/build"
mkdir -p "${BUILD_DIR}"

build_cmd="cc -O2 -Wall -Wstrict-prototypes -Wshadow -Wpointer-arith -Wcast-qual -Wcast-align -Wwrite-strings -Wnested-externs -Winline -W -Wundef -Wmissing-prototypes -I${DIR}/include/i2c-tools/include -I${DIR}/include/i2c-tools/tools"

{
  # Build i2cbusses
  ${build_cmd} -c "${DIR}/include/i2c-tools/tools/i2cbusses.c" -o "${BUILD_DIR}/i2cbusses.o"
  # Build pt-i2cdetect
  ${build_cmd} -c "${DIR}/src/pt-i2cdetect.c" -o "${BUILD_DIR}/pt-i2cdetect.o"

  cc -o "${BUILD_DIR}/pt-i2cdetect" \
    "${BUILD_DIR}/pt-i2cdetect.o" \
    "${BUILD_DIR}/i2cbusses.o" \
    -Llib -li2c
} 2>/dev/null

rm "${BUILD_DIR}/"*.o
