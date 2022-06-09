# FROM python:3.9.5-slim AS base
FROM ubuntu:20.04 AS base

FROM base AS python_build
RUN apt-get update && apt-get -y install --no-install-recommends \
	build-essential \
	ca-certificates \
	libffi-dev \
	libssl-dev \
	zlib1g-dev
COPY cpython /cpython/
RUN cd /cpython && \
	./configure --prefix=/usr/local && make && make install

FROM base AS python
COPY --from=python_build /usr/local /usr/local/

FROM python AS poetry
RUN apt-get update && apt-get -y install --no-install-recommends \
	build-essential \
	ca-certificates \
	git \
	libusb-1.0 \
	libudev-dev
RUN pip3 install \
	poetry==1.1.13
WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN POETRY_VIRTUALENVS_IN_PROJECT=true \
	poetry install

FROM python AS dev
RUN apt-get update && apt-get -y install --no-install-recommends \
	libnss-mdns \
	libusb-1.0
WORKDIR /app
COPY --from=poetry /app/.venv ./.venv/
ENV PYTHONUNBUFFERED=1
ENV PATH=/app/.venv/bin:$PATH
CMD ["python", "main.py"]

FROM dev
COPY *.py ./
COPY ds2482 ./ds2482/
COPY hass_mqtt_discovery ./hass_mqtt_discovery/
