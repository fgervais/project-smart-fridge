import adafruit_mlx90640
import adafruit_tmp117
import asyncio
import board
import busio
import forensic
import io
import kasa
import logging
import matplotlib.pyplot as plt
import numpy as np
import os
import paho.mqtt.client as mqtt
import signal
import time
import traceback

from pprint import pprint


MAX_NUMBER_OF_TMP117 = 4
KASA_RELAY_DEVICE_ID = "50:C7:BF:6B:D4:E9"


# Used by docker-compose down
def sigterm_handler(signal, frame):
    logger.info("Reacting to SIGTERM")
    teardown()
    exit(0)


def teardown():
    try:
        client.loop_stop()
    except:
        logger.exception("Could not stop MQTT client loop")
        traceback.print_exc()

    try:
        client.disconnect()
    except:
        logger.exception("Could not disconnect MQTT client")
        traceback.print_exc()


logging.basicConfig(
    format="[%(asctime)s] %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

if "DEBUG" in os.environ:
    logger.setLevel(logging.DEBUG)

signal.signal(signal.SIGTERM, sigterm_handler)

i2c = busio.I2C(board.SCL, board.SDA, frequency=800000)

frame = [0] * 768
mlx = adafruit_mlx90640.MLX90640(i2c)
print("MLX addr detected on I2C", [hex(i) for i in mlx.serial_number])
mlx.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_2_HZ

tmp117 = [None] * MAX_NUMBER_OF_TMP117
for i in range(MAX_NUMBER_OF_TMP117):
    try:
        tmp117[i] = adafruit_tmp117.TMP117(i2c, 0x48 + i)
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
    # asyncio.run(dev.update())
    if dev.device_id == KASA_RELAY_DEVICE_ID:
        kasa_relay = dev

if not kasa_relay is None:
    logger.info(f"Found relay: {kasa_relay}")

while True:
    while True:
        try:
            mlx.getFrame(frame)
            break
        except:
            logger.exception("Could not read mlx frame")
            time.sleep(1)

    frame_array = np.array(frame)
    frame_array = np.reshape(frame_array, (-1, 32))
    frame_array = np.fliplr(frame_array)

    im = plt.imshow(frame_array)
    plt.colorbar(im)
    image = io.BytesIO()
    plt.savefig(image, format="png")

    logger.debug("Waiting for publish")
    try:
        mqtt_mi.wait_for_publish()
    except NameError as e:
        pass
    except:
        logger.exception("Error waiting for publish")
    logger.debug("Publishing")
    mqtt_mi = client.publish("inside/thermal1", bytearray(image.getvalue()))
    plt.close()

    for i in range(MAX_NUMBER_OF_TMP117):
        if not tmp117[i]:
            break

        try:
            temp = tmp117[i].temperature
        except:
            logger.exception(f"Error reading TMP117 ({i})")

        client.publish(f"inside/tmp117/{i}", round(temp, 2))

        logger.debug(f"Temperature{i}: {temp}°C")

    logger.debug("Kasa update")
    asyncio.run(kasa_relay.update())
    power = round(kasa_relay.emeter_realtime["power"], 2)
    logger.debug(f"Power: {power} W")
    # Power peaks at ~800W on startup
    power = min(power, 80.00)
    logger.debug("Kasa publish")
    client.publish(f"outside/relay/power", power)
