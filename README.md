# Smart Beer Fridge

## The general idea

The goal of this project is to make a custom control for a [DCR032A2BDD](https://www.danby.com/products/compact-refrigerators/dcr032a2bdd/) Danby mini fridge
hoping to introduce a couple different modes to save power/reduce noise/reduce strain in
idle periods and precisely cool when we need it.

I'd also like to get that "sub-zero" tap experience at home from times to times.

This idea came from this quote from the manufacturer's FAQ:

> The temperature range of Danby’s refrigerators are between 32F-39.2F/0C – 4C.
> ...
> Our refrigerators are capable of maintaining a wider range than the specified temperature
> ...

## Step 1 - Install hardware

### Inside

I went with 1 `MLX90640` infrared thermal sensor and 4 `TMP117` roughly installed
like so:

![Inside Sensors](assets/img/inside-sensors.jpg)

### Outside

I installed one more `TMP117` a temperature sensors on the compressor.

I also added a tp-link `HS110` to get power consumption.

## Step 2 - Get the data out

I send all those sensor out to an Home Assistant instance through MQTT.

![Dashboard](assets/img/ha-overview.png)

## Step 3 - Get a sense of how things are working

We don't want to push things too far so fist we need to learn how the fridge is
working when it does the control itself.

I'm specifically interested how low/high the temperature gets at the evaporator,
how often the compressor starts, for how long, and how does it's temperature
behave.

Things of that nature so when I take control I have a sense of what the limits are.

## IR view

This is what the infrared sensor sees with a room temp can moved from left to
right jumping from one row to the next.

![MLX90640](assets/img/ir-view.jpg)
