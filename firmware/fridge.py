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


class S31Relay:
    def __init__(self, mqtt_client):
        self.mqtt_client = mqtt_client

    def turn_on(self):
        self.mqtt_client.publish("fridge-relay/switch/sonoff_s31_relay/command", "ON")

    def turn_off(self):
        self.mqtt_client.publish("fridge-relay/switch/sonoff_s31_relay/command", "OFF")

    def keepalive(self):
        self.mqtt_client.publish("fridge-relay/keepalive", True)


class Thermostat:
    def __init__(self, relay, sensor, min_t=-5, max_t=2):
        self.relay = relay
        self.sensor = sensor
        self.min_t = min_t
        self.max_t = max_t

        if sensor.temperature > max_t:
            self.on()
        else:
            self.off()

    def on(self):
        self.relay.turn_on()
        self.is_on = True

    def off(self):
        self.relay.turn_off()
        self.is_on = False

    def run(self):
        temperature = self.sensor.temperature
        logger.debug(
            f"Thermostat ({'ON' if self.is_on else 'OFF'}) ({self.min_t} < {temperature} < {self.max_t})"
        )
        if self.is_on and temperature < self.min_t:
            self.off()
        elif not self.is_on and temperature > self.max_t:
            self.on()


class Fridge:
    def __init__(
        self,
        ir_camera,
        discrete_temperature_sensors,
        compressor_sensor,
        condenser_sensor,
        thermostat=None,
    ):
        self.ir_camera = ir_camera
        self.discrete_temperature_sensors = discrete_temperature_sensors
        self.compressor_sensor = compressor_sensor
        self.condenser_sensor = condenser_sensor
        self.thermostat = thermostat

    @property
    def ir_frame(self):
        frame = [0] * 768

        logger.debug("Getting frame")
        self._retry(lambda: self.ir_camera.getFrame(frame), "Could not read mlx frame")

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

            temp = self._retry(
                lambda: sensor.temperature, f"Error reading TMP117 ({i})"
            )
            logger.debug(f"Temperature{i}: {temp}°C")
            readings.append(round(temp, 2))

        return readings

    @property
    def compressor_temperature(self):
        temp = self._retry(
            lambda: self.compressor_sensor.temperature,
            f"Error reading compressor TMP117",
        )
        logger.debug(f"Temperature (compressor): {temp}°C")

        return round(temp, 2)

    @property
    def condenser_temperature(self):
        temp = self._retry(
            lambda: self.condenser_sensor.temperature, f"Error reading condenser TMP117"
        )
        logger.debug(f"Temperature (condenser): {temp}°C")

        return round(temp, 2)

    @property
    def power_usage(self):
        raise NotImplementedError()

    def _reset_mcp2221(self, device):
        logger.info("Resetting MCP2221A")
        mcp2221_handle = device.i2c_device.i2c._i2c._mcp2221
        mcp2221_handle._hid.close()
        mcp2221_handle._hid.open_path(mcp2221_handle._bus_id)

    def _retry(self, func, error_message="Could not execute function"):
        MAX_RETRY = 3

        for retry in range(MAX_RETRY):
            try:
                ret = func()
                break
            except Exception as e:
                logger.exception(error_message)
                if retry == (MAX_RETRY - 1):
                    raise e
                time.sleep(1)

        return ret

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
