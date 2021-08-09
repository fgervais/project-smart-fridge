import asyncio
import io
import logging
import matplotlib.pyplot as plt
import numpy as np
import os
import time


logger = logging.getLogger(__name__)
if "DEBUG" in os.environ:
    logger.setLevel(logging.DEBUG)


class Fridge:
    def __init__(self, ir_camera, discrete_temperature_sensors, kasa_relay):
        self.ir_camera = ir_camera
        self.discrete_temperature_sensors = discrete_temperature_sensors
        self.kasa_relay = kasa_relay

    @property
    def ir_frame(self):
        frame = [0] * 768

        while True:
            try:
                logger.debug("Getting frame")
                self.ir_camera.getFrame(frame)
                break
            except:
                logger.exception("Could not read mlx frame")
                time.sleep(1)

        return frame

    @property
    def ir_image(self):
        return self.ir_frame_to_image(self.ir_frame)

    @property
    def discrete_temperature_readings(self):
        readings = []

        for i, sensor in enumerate(self.discrete_temperature_sensors):
            if not sensor:
                break

            try:
                temp = sensor.temperature
                logger.debug(f"Temperature{i}: {temp}°C")
                readings.append(round(temp, 2))
            except:
                logger.exception(f"Error reading TMP117 ({i})")

        return readings

    @property
    def power_usage(self):
        logger.debug("Kasa update")
        asyncio.run(self.kasa_relay.update())
        power = self.kasa_relay.emeter_realtime["power"]
        logger.debug(f"Power: {power} W")
        power = round(power, 2)
        # Power peaks at ~800W on startup, limit to 80W
        power = min(power, 80.00)

        return power

    def ir_frame_to_image(self, frame):
        logger.debug("Converting frame to image")
        frame_array = np.array(frame)
        frame_array = np.reshape(frame_array, (-1, 32))
        frame_array = np.fliplr(frame_array)

        im = plt.imshow(frame_array)
        plt.colorbar(im)
        image = io.BytesIO()
        plt.savefig(image, format="png")
        plt.close()

        return bytearray(image.getvalue())
