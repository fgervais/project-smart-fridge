import asyncio
import io
import logging
import matplotlib.pyplot as plt
import numpy as np
import os
import time

from datetime import timedelta
from threading import Timer


logger = logging.getLogger(__name__)
if "DEBUG" in os.environ:
    logger.setLevel(logging.DEBUG)


class S31Relay:
    STATE_CHANGE_TIMEOUT_S = 10

    def __init__(self, mqtt_client):
        self.mqtt_client = mqtt_client

        self.state = None
        self.state_requested = None
        self.state_requested_timestamp = None
        self.state_change_timestamp = 0

        self.mqtt_client.message_callback_add(
            "fridge-relay/switch/sonoff_s31_relay/state", self._state_change_callback
        )
        self.mqtt_client.subscribe("fridge-relay/switch/sonoff_s31_relay/state")

    @property
    def state_matches_requested(self):
        return self.state == self.state_requested

    @property
    def is_on(self):
        return self.state == "ON"

    @property
    def seconds_since_last_state_change(self):
        return time.time() - self.state_change_timestamp

    def _state_change_callback(self, client, userdata, message):
        logger.debug(
            f"📝 Received message {message.payload} on topic {message.topic} with QoS {message.qos}"
        )

        self.state = str(message.payload)
        self.state_change_timestamp = time.time()

        if self.state_matches_requested:
            logger.debug("✔️ Expected relay state change")
        else:
            logger.error("❌ Unrequested relay state change")

    def turn_on(self):
        self.set_state("ON")

    def turn_off(self):
        self.set_state("OFF")

    def set_state(self, state):
        if state != self.state:
            self.mqtt_client.publish(
                "fridge-relay/switch/sonoff_s31_relay/command", state
            )
            self.state_requested = state
            self.state_requested_timestamp = time.time()

            retry = 0
            while true:
                if self.state == self.state_requested:
                    logger.debug("✔️ Requested state is set")
                    break

                if retry == 10:
                    logger.error("❌ Relay did not change state")
                    raise RuntimeError("Relay did not change state")

                logger.debug("⏳ Relay is not yet at state")
                time.sleep(1)
        else:
            logger.debug(f"🤔 Relay is already at {state} ({self.state})")

    def set_to_expected_state(self):
        if not self.state_matches_requested:
            logger.info("Resetting relay to expected state")
            self.set_state(self.state_requested)
        else:
            logger.debug(
                "We we're asked to reset the relay state but it's already fine"
            )

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
    MIN_ON_SECONDS = 5 * 60
    MIN_OFF_SECONDS = 5 * 60
    MAX_COMPRESSOR_TEMP_C = 60
    # Temperature over which the compressor won't be turned on.
    MAX_COMPRESSOR_START_TEMP_C = MAX_COMPRESSOR_TEMP_C - 5

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

        self.in_cooldown = False
        if self.thermostat:
            self.thermostat.set_fridge(self)

        self.state_correction_timer = None
        self.trigger_relay_state_correction = False

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

    @property
    def is_on(self):
        return self.relay.is_on

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
            logger.debug("⏱️ We are in cooldown")
            return

        if self.compressor_temperature >= Fridge.MAX_COMPRESSOR_START_TEMP_C:
            logger.debug("🔥 Compressor is too hot to restart")
            return

        if not self.relay.is_on:
            if self.relay.seconds_since_last_state_change < Fridge.MIN_OFF_SECONDS:
                logger.debug(
                    f"Compressor only OFF for {timedelta(seconds=int(seconds_since_last_off))}"
                )
                return

        logger.debug("Relay ON")
        self.relay.turn_on()

    def off(self, emergency=False):
        if not self.relay:
            return

        if not emergency and self.relay.is_on:
            if self.relay.seconds_since_last_state_change < Fridge.MIN_ON_SECONDS:
                logger.debug(
                    f"🕐 Compressor only ON for {timedelta(seconds=int(seconds_on))}"
                )
                return

        logger.debug("Relay OFF")
        self.relay.turn_off()

    def run(self):
        if self.relay:
            if self.is_on:
                seconds_since_last_off = time.time() - self.last_off
                compressor_temperature = self.compressor_temperature
                logger.debug(
                    f"Allowed compressor ΔT: {round(Fridge.MAX_COMPRESSOR_TEMP_C - compressor_temperature, 2)}°C"
                )
                if compressor_temperature > Fridge.MAX_COMPRESSOR_TEMP_C:
                    self.in_cooldown = True
                    self.off(emergency=True)
                    logger.info("🔥 Cooldown")
            elif self.in_cooldown:
                time_in_cooldown = int(time.time() - self.last_on)
                logger.debug(
                    f"🕐 In cooldown since {timedelta(seconds=time_in_cooldown)}"
                )
                if time_in_cooldown > Fridge.COOLDOWN_TIME_SECONDS:
                    self.in_cooldown = False
                    logger.info("!Cooldown")

            self.trigger_relay_state_correction

        if self.thermostat:
            self.thermostat.run()
