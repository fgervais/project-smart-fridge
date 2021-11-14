import asyncio
import io
import logging
import matplotlib.pyplot as plt
import numpy as np
import os
import time

from datetime import timedelta


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
    def __init__(self, min_t=-5, max_t=2):
        self.fridge = None
        self.min_t = min_t
        self.max_t = max_t

    def set_fridge(self, fridge):
        self.fridge = fridge

        if self.fridge.evaporator_temperature > self.max_t:
            self.fridge.on()
        else:
            self.fridge.off()

    def run(self):
        if not self.fridge:
            return

        temperature = self.fridge.evaporator_temperature
        logger.debug(
            f"Thermostat ({'ON' if self.fridge.is_on else 'OFF'}) ({self.min_t} < {temperature} < {self.max_t})"
        )
        if self.fridge.is_on and temperature < self.min_t:
            self.fridge.off()
        elif not self.fridge.is_on and temperature > self.max_t:
            self.fridge.on()


class Fridge:
    COOLDOWN_TIME_SECONDS = 10 * 60
    MAX_ON_SECONDS = 20 * 60

    def __init__(
        self,
        ir_camera,
        discrete_temperature_sensors,
        compressor_sensor,
        condenser_sensor,
        relay=None,
        thermostat=None,
    ):
        self.ir_camera = ir_camera
        self.discrete_temperature_sensors = discrete_temperature_sensors
        self.compressor_sensor = compressor_sensor
        self.condenser_sensor = condenser_sensor
        self.relay = relay
        self.thermostat = thermostat

        self.is_on = False
        self.last_on = None
        self.last_off = None
        self.in_cooldown = False
        if self.thermostat:
            self.thermostat.set_fridge(self)

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
    def evaporator_temperature(self):
        temp = self._retry(
            lambda: self.discrete_temperature_sensors[1].temperature,
            f"Error reading condenser TMP117",
        )
        logger.debug(f"Temperature (evaporator): {temp}°C")

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

    def on(self):
        if not self.relay:
            return

        if self.in_cooldown:
            return

        self.relay.turn_on()
        self.is_on = True
        self.last_off = time.time()

    def off(self):
        if not self.relay:
            return

        self.relay.turn_off()
        self.is_on = False
        self.last_on = time.time()

    def run(self):
        if self.relay:
            if self.is_on:
                seconds_since_last_off = time.time() - self.last_off
                logger.debug(
                    f"Cooldown in {timedelta(seconds=Fridge.MAX_ON_SECONDS - int(seconds_since_last_off))} seconds"
                )
                if seconds_since_last_off > Fridge.MAX_ON_SECONDS:
                    self.in_cooldown = True
                    self.off()
                    logger.info("Cooldown")
            elif (
                self.in_cooldown
                and (time.time() - self.last_on) > Fridge.COOLDOWN_TIME_SECONDS
            ):
                self.in_cooldown = False
                logger.info("!Cooldown")

        if self.thermostat:
            self.thermostat.run()
