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


class Thermostat:
    def __init__(self, kasa_relay, sensor, min_t=-5, max_t=2):
        self.kasa_relay = kasa_relay
        self.sensor = sensor
        self.min_t = min_t
        self.max_t = max_t

        if sensor.temperature > max_t:
            self.on()
        else:
            self.off()

    def on(self):
        asyncio.run(self.kasa_relay.turn_on())
        self.is_on = True

    def off(self):
        asyncio.run(self.kasa_relay.turn_off())
        self.is_on = False

    def run(self):
        if self.is_on and self.sensor.temperature < self.min_t:
            self.off()
        elif not self.is_on and self.sensor.temperature > self.max_t:
            self.on()


class Fridge:
    def __init__(
        self, ir_camera, discrete_temperature_sensors, kasa_relay, thermostat=None
    ):
        self.ir_camera = ir_camera
        self.discrete_temperature_sensors = discrete_temperature_sensors
        self.kasa_relay = kasa_relay
        self.thermostat = thermostat

    @property
    def ir_frame(self):
        frame = [0] * 768

        while True:
            try:
                logger.debug("Getting frame")
                self.ir_camera.getFrame(frame)
                break
            except Exception:
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
            except Exception:
                logger.exception(f"Error reading TMP117 ({i})")

        return readings

    @property
    def power_usage(self):
        if self.thermostat and not self.thermostat.is_on:
            return 0

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
