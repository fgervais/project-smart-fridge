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
import sys
import time
import traceback

from pprint import pprint

import i2c_helper

from fridge import Fridge, Thermostat


KASA_RELAY_DEVICE_ID = "50:C7:BF:6B:D4:E9"
WATCHDOG_TIMEOUT_SEC = 30

MCP2221_VID = 0x04D8
MCP2221_PID = 0x00DD

COMPRESSOR_TMP117_ADDR = 0x48
CONDENSER_TMP117_ADDR = 0x49


# Used by docker-compose down
def sigterm_handler(signal, frame):
    logger.info("Reacting to SIGTERM")
    teardown()
    sys.exit(0)


def hang(signal, frame):
    logger.error("User requested hang")
    logger.error("".join(traceback.format_stack(frame)))
    while True:
        time.sleep(1)


# This will not interrupt pure C code:
# https://docs.python.org/3/library/signal.html#execution-of-python-signal-handlers
def alarm_signal_handler(signal, frame):
    logger.error("Watchdog interrupt!")
    logger.error("".join(traceback.format_stack(frame)))
    sys.exit(1)


def kick_watchdog():
    logger.debug("Watchdog kick")
    signal.alarm(WATCHDOG_TIMEOUT_SEC)


def teardown():
    try:
        fridge.thermostat.off()
    except Exception:
        pass

    try:
        client.loop_stop()
    except Exception:
        logger.exception("Could not stop MQTT client loop")

    try:
        client.disconnect()
    except Exception:
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
signal.signal(signal.SIGUSR2, hang)
signal.signal(signal.SIGALRM, alarm_signal_handler)

i2c_buses = []
addresses = [mcp["path"] for mcp in hid.enumerate(MCP2221_VID, MCP2221_PID)]
for address in addresses:
    logger.debug(f"New I2C bus: {address}")
    i2c_bus = busio.I2C(bus_id=address, frequency=400000)
    i2c_buses.append(i2c_bus)

mlx, compressor_tmp117, condenser_tmp117, inside_tmp117 = i2c_helper.enumerate(
    i2c_buses, COMPRESSOR_TMP117_ADDR, CONDENSER_TMP117_ADDR
)

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

# thermostat = Thermostat(kasa_relay, inside_tmp117[1])
fridge = Fridge(mlx, inside_tmp117, compressor_tmp117, condenser_tmp117, kasa_relay)

kick_watchdog()


while True:
    logger.debug("Waiting for publish")
    try:
        mqtt_mi.wait_for_publish()
    except NameError as e:
        pass
    except Exception:
        logger.exception("Error waiting for publish")

    logger.debug("Frame publish")
    mqtt_mi = client.publish("inside/thermal1", fridge.ir_image)

    for i, temp in enumerate(fridge.discrete_temperature_readings):
        client.publish(f"inside/tmp117/{i}", temp)

    logger.debug("Kasa publish")
    client.publish(f"outside/relay/power", fridge.power_usage)

    client.publish(f"outside/compressor/temperature", fridge.compressor_temperature)
    client.publish(f"outside/side/temperature", fridge.condenser_temperature)

    if fridge.thermostat:
        fridge.thermostat.run()

    kick_watchdog()

    logger.debug("Going to sleep")
    time.sleep(2)
