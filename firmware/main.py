import adafruit_mlx90640
import adafruit_tmp117
import board
import busio
import io
import logging
import matplotlib.pyplot as plt
import numpy as np
import paho.mqtt.client as mqtt
import signal
import time
import traceback

from pprint import pprint


MAX_NUMBER_OF_TMP117 = 4


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
    format='[%(asctime)s] %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)
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
        print(e)

if not any(tmp117):
    print("No sensor detected")

client = mqtt.Client()
client.connect("mosquitto")
client.loop_start()

plt.style.use("dark_background")


while True:
    while True:
        try:
            mlx.getFrame(frame)
            break
        except:
            traceback.print_exc()
            time.sleep(1)

    frame_array = np.array(frame)
    frame_array = np.reshape(frame_array, (-1, 32))

    im = plt.imshow(frame_array)
    plt.colorbar(im)
    image = io.BytesIO()
    plt.savefig(image, format = "png")

    logger.debug("Waiting for publish")
    try:
        mqtt_mi.wait_for_publish()
    except NameError as e:
        pass
    except:
        logger.exception("Error waiting for publish")
        traceback.print_exc()
    logger.debug("Publishing")
    mqtt_mi = client.publish("inside/thermal1", bytearray(image.getvalue()))
    plt.close()


    for i in range(MAX_NUMBER_OF_TMP117):
        if not tmp117[i]:
            break

        temp = tmp117[i].temperature
        client.publish(f"inside/tmp117/{i}", temp)

        logger.debug(f"Temperature{i}: {temp}°C")
