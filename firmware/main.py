import adafruit_mlx90640
import board
import busio
import io
import logging
import matplotlib.pyplot as plt
import numpy as np
import paho.mqtt.client as mqtt
import signal
import time

from pprint import pprint


# Used by docker-compose down
def sigterm_handler(signal, frame):
    logger.info("Reacting to SIGTERM")
    teardown()
    exit(0)


def teardown():
    pass


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

client = mqtt.Client()
client.connect("mosquitto")

while True:
    mlx.getFrame(frame)
    frame_array = np.array(frame)
    frame_array = np.reshape(frame_array, (-1, 32))

    im = plt.imshow(frame_array)
    plt.colorbar(im)
    image = io.BytesIO()
    plt.savefig(image, format = "png")

    client.publish("inside/thermal1", bytearray(image.getvalue()))
    client.loop(0.1)
    plt.close()
