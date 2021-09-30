import adafruit_ds18x20
import adafruit_mlx90640
import adafruit_tmp117
import logging
import os

from ds2482.ds2482 import DS2482
from ds2482.onewire import OneWireBus


MAX_NUMBER_OF_TMP117 = 4


logger = logging.getLogger(__name__)
if "DEBUG" in os.environ:
    logger.setLevel(logging.DEBUG)


def enumerate(buses, compressor_tmp117_addr, condenser_tmp117_addr):
    i2c_bus_internal = None

    # Find which i2c bus has the camera
    for bus in buses:
        try:
            mlx = adafruit_mlx90640.MLX90640(bus)
            logger.info(
                f"MLX addr detected on I2C {[hex(i) for i in mlx.serial_number]}"
            )
            mlx.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_2_HZ
            i2c_bus_internal = bus
            buses.remove(bus)
        except Exception:
            logger.debug("This isn't the internal bus")

    # Find the compressor bus
    for bus in buses:
        try:
            compressor_tmp117 = adafruit_tmp117.TMP117(bus, compressor_tmp117_addr)
            buses.remove(bus)
        except Exception:
            logger.debug("This isn't the comressor bus")

    # Find the side bus
    for bus in buses:
        try:
            condenser_tmp117 = adafruit_tmp117.TMP117(bus, condenser_tmp117_addr)
            buses.remove(bus)
        except Exception:
            logger.debug("This isn't the side bus")

    inside_tmp117 = [None] * MAX_NUMBER_OF_TMP117
    for i in range(MAX_NUMBER_OF_TMP117):
        try:
            inside_tmp117[i] = adafruit_tmp117.TMP117(i2c_bus_internal, 0x48 + i)
        except Exception as e:
            logger.info(e)

    if not any(inside_tmp117):
        logger.info("No sensor detected")

    try:
        ds2482 = DS2482(i2c_bus_internal, active_pullup=True)
        ow_bus = OneWireBus(ds2482)

        devices = ow_bus.scan()
        for device in devices:
            logger.info(
                "ROM = {} \tFamily = 0x{:02x}".format(
                    [hex(i) for i in device.rom], device.family_code
                )
            )

        ds18b20 = adafruit_ds18x20.DS18X20(ow_bus, devices[0])
    except Exception:
        ds18b20 = None

    return mlx, compressor_tmp117, condenser_tmp117, inside_tmp117, ds18b20
