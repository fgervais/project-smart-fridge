import asyncio
import board
import busio
import faulthandler
import forensic
import hid
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
import persistent_state

from fridge import Fridge, Thermostat, DefrostThermostat, S31Relay
from hass_mqtt_discovery.ha_mqtt_device import Device, Sensor


WATCHDOG_TIMEOUT_SEC = 60
LOOP_SLEEP_SEC = 10

MAX_APP_RESTART_COUNT = 5

MCP2221_VID = 0x04D8
MCP2221_PID = 0x00DD

COMPRESSOR_TMP117_ADDR = 0x48
CONDENSER_TMP117_ADDR = 0x49


# Used by docker-compose down
def sigterm_handler(signal, frame):
    logger.info("💥 Reacting to SIGTERM")
    teardown()
    sys.exit(0)


def hang(signal, frame):
    logger.error("User requested hang")
    logger.error("".join(traceback.format_stack(frame)))
    while True:
        time.sleep(1)


def kick_watchdog():
    logger.debug("🐶 Watchdog kick")
    faulthandler.dump_traceback_later(WATCHDOG_TIMEOUT_SEC, exit=True)


def teardown():
    # try:
    #     fridge.off()
    # except Exception:
    #     pass

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

kick_watchdog()

pstate = persistent_state.load()
pstate["restart_count"] += 1
persistent_state.inc_restart_count()
logger.info(f"Restart count = {pstate['restart_count']}")

if pstate["restart_count"] > 1:
    logger.info("We are recovering from a failure")

if pstate["restart_count"] == MAX_APP_RESTART_COUNT:
    persistent_state.reset_restart_count()
    logger.error("Max restart reached, stopping application")
    while True:
        time.sleep(1)

i2c_buses = []
addresses = [mcp["path"] for mcp in hid.enumerate(MCP2221_VID, MCP2221_PID)]
for address in addresses:
    logger.debug(f"New I2C bus: {address}")
    i2c_bus = busio.I2C(bus_id=address, frequency=400000)
    i2c_buses.append(i2c_bus)

mlx, compressor_tmp117, condenser_tmp117, inside_tmp117, ds18b20 = i2c_helper.enumerate(
    i2c_buses, COMPRESSOR_TMP117_ADDR, CONDENSER_TMP117_ADDR
)

client = mqtt.Client()
last_log_time = 0
while True:
    try:
        client.connect("home.local")
        break
    except Exception:
        if (time.monotonic() - last_log_time) > (10 * 60):
            logger.exception("Could not connect to MQTT server, retrying")
            last_log_time = time.monotonic()
        time.sleep(2)
client.loop_start()

fridge_device = Device.from_config("device.yaml")
if ds18b20:
    ds18b20_sensor = Sensor(
        client,
        "waterproof",
        parent_device=fridge_device,
        unit_of_measurement="°C",
        topic_parent_level="inside",
    )

plt.style.use("dark_background")

forensic.register_debug_hook()

relay = S31Relay(client)
# thermostat = Thermostat(relay, inside_tmp117[1], min_t=-4, max_t=4) # Min
# thermostat = Thermostat(relay, inside_tmp117[1]) # Middle
# thermostat = Thermostat(relay, inside_tmp117[1], min_t=-7, max_t=-1)  # Max

# thermostat = Thermostat(min_t=-12, max_t=-5)
thermostat = Thermostat(min_t=-14, max_t=-5)

# thermostat = DefrostThermostat()

fridge = Fridge(
    mlx, inside_tmp117, compressor_tmp117, condenser_tmp117, ds18b20, relay, thermostat
)

kick_watchdog()
logger.info("We are online!")

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

    client.publish(f"outside/compressor/temperature", fridge.compressor_temperature)
    client.publish(f"outside/side/temperature", fridge.condenser_temperature)

    if ds18b20:
        ds18b20_sensor.send(fridge.waterproof_temperature)

    relay.keepalive()
    fridge.run()

    if pstate["restart_count"] > 0:
        logger.debug("Resetting restart count to 0")
        pstate["restart_count"] = 0
        persistent_state.reset_restart_count()

    kick_watchdog()

    logger.debug("💤 Going to sleep")
    time.sleep(LOOP_SLEEP_SEC)

    logger.debug("─" * 40)
