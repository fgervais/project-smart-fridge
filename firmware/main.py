import adafruit_mlx90640
import board
import busio
import logging
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
    level=logging.DEBUG,
    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

signal.signal(signal.SIGTERM, sigterm_handler)

i2c = busio.I2C(board.SCL, board.SDA, frequency=800000)

frame = [0] * 768
mlx = adafruit_mlx90640.MLX90640(i2c)
print("MLX addr detected on I2C", [hex(i) for i in mlx.serial_number])

mlx.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_2_HZ

mlx.getFrame(frame)
# pprint(frame)

while True:
    time.sleep(3)
