import adafruit_mlx90640
import adafruit_tmp117
import asyncio
import board
import busio
import forensic
import hid
import kasa
import logging
import matplotlib.pyplot as plt
import os
import paho.mqtt.client as mqtt
import signal
import time

from pprint import pprint

from fridge import Fridge, Thermostat


MAX_NUMBER_OF_TMP117 = 4
KASA_RELAY_DEVICE_ID = "50:C7:BF:6B:D4:E9"

MCP2221_VID = 0x04D8
MCP2221_PID = 0x00DD

COMPRESSOR_TMP117_ADDR = 0x48
EVAPORATOR_TMP117_ADDR = 0x49


# Used by docker-compose down
def sigterm_handler(signal, frame):
    logger.info("Reacting to SIGTERM")
    teardown()
    exit(0)


def teardown():
    try:
        fridge.thermostat.off()
    except:
        pass

    try:
        client.loop_stop()
    except:
        logger.exception("Could not stop MQTT client loop")

    try:
        client.disconnect()
    except:
        logger.exception("Could not disconnect MQTT client")


logging.basicConfig(
    format="[%(asctime)s] %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

if "DEBUG" in os.environ:
    logger.setLevel(logging.DEBUG)

signal.signal(signal.SIGTERM, sigterm_handler)

i2c_buses = []
i2c_bus_internal = None
addresses = [mcp["path"] for mcp in hid.enumerate(MCP2221_VID, MCP2221_PID)]
for address in addresses:
    logger.debug(f"New I2C bus: {address}")
    i2c_bus = busio.I2C(bus_id=address, frequency=400000)
    i2c_buses.append(i2c_bus)

# Find which i2c bus has the camera
for bus in i2c_buses:
    try:
        mlx = adafruit_mlx90640.MLX90640(bus)
        logger.info(f"MLX addr detected on I2C {[hex(i) for i in mlx.serial_number]}")
        mlx.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_2_HZ
        i2c_bus_internal = bus
        i2c_buses.remove(bus)
    except:
        logger.debug("This isn't the internal bus")

# Find the compressor bus
for bus in i2c_buses:
    try:
        compressor_tmp117 = adafruit_tmp117.TMP117(bus, COMPRESSOR_TMP117_ADDR)
        i2c_buses.remove(bus)
    except:
        logger.debug("This isn't the comressor bus")

# Find the side bus
for bus in i2c_buses:
    try:
        side_tmp117 = adafruit_tmp117.TMP117(bus, EVAPORATOR_TMP117_ADDR)
        i2c_buses.remove(bus)
    except:
        logger.debug("This isn't the side bus")

tmp117 = [None] * MAX_NUMBER_OF_TMP117
for i in range(MAX_NUMBER_OF_TMP117):
    try:
        tmp117[i] = adafruit_tmp117.TMP117(i2c_bus_internal, 0x48 + i)
    except Exception as e:
        logger.info(e)

if not any(tmp117):
    logger.info("No sensor detected")

client = mqtt.Client()
client.connect("home.local")
client.loop_start()

plt.style.use("dark_background")

forensic.register_debug_hook()

kasa_relay = None
devices = asyncio.run(kasa.Discover.discover())
for addr, dev in devices.items():
    if dev.device_id == KASA_RELAY_DEVICE_ID:
        kasa_relay = dev

if not kasa_relay is None:
    logger.info(f"Found relay: {kasa_relay}")

thermostat = Thermostat(kasa_relay, tmp117[1])
fridge = Fridge(thermostat, mlx, tmp117, kasa_relay)

while True:
    logger.debug("Waiting for publish")
    try:
        mqtt_mi.wait_for_publish()
    except NameError as e:
        pass
    except:
        logger.exception("Error waiting for publish")

    logger.debug("Frame publish")
    mqtt_mi = client.publish("inside/thermal1", fridge.ir_image)

    for i, temp in enumerate(fridge.discrete_temperature_readings):
        client.publish(f"inside/tmp117/{i}", temp)

    logger.debug("Kasa publish")
    client.publish(f"outside/relay/power", fridge.power_usage)

    try:
        temp = compressor_tmp117.temperature
        logger.debug(f"Temperature (compressor): {temp}°C")
        client.publish(f"outside/compressor/temperature", round(temp, 2))
    except:
        logger.exception(f"Error reading compressor TMP117 ({i})")

    try:
        temp = side_tmp117.temperature
        logger.debug(f"Temperature (side): {temp}°C")
        client.publish(f"outside/side/temperature", round(temp, 2))
    except:
        logger.exception(f"Error reading side TMP117 ({i})")

    if fridge.thermostat:
        fridge.thermostat.run()

    logger.debug("Going to sleep")
    time.sleep(2)
