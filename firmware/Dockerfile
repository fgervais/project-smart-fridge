FROM python:3.9.5-slim-buster AS base

# FROM base AS build
# RUN apt-get update && apt-get -y install --no-install-recommends \
# 	build-essential \
# 	libusb-1.0 \
# 	libudev-dev
# RUN pip wheel \
# 	hidapi==0.9.0.post2 \
# 	sysv_ipc==1.0.1

FROM base AS dev
# RUN apt-get update && apt-get -y install --no-install-recommends \
# 	git \
# 	libusb-1.0
# COPY --from=build /*.whl /
# RUN pip install *.whl
# RUN pip install \
# 	Adafruit-Blinka==6.10.2 \
# 	git+https://github.com/fgervais/Adafruit_CircuitPython_MLX90640.git@broken-pixels \
# 	adafruit-circuitpython-mlx90640
# 	# websockets
WORKDIR /app
CMD ["python", "main.py"]

FROM dev
COPY . /app/
