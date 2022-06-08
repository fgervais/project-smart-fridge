# FROM python:3.9.5-slim AS base
FROM ubuntu:20.04 AS base

FROM base AS python_build
RUN apt-get update && apt-get -y install --no-install-recommends \
	build-essential \
	ca-certificates \
	git \
	zlib1g-dev
RUN git clone https://github.com/python/cpython.git
RUN cd cpython && \
	git checkout v3.9.5 && \
	./configure --prefix=$(pwd)/_install && make && make install

FROM base AS python
# /usr/local/bin/python
COPY --from=python_build /cpython/_install /usr/local/

# FROM base AS build
# RUN apt-get update && apt-get -y install --no-install-recommends \
# 	build-essential \
# 	git \
# 	libusb-1.0 \
# 	libudev-dev
# RUN pip install \
# 	poetry==1.2.0a2
# WORKDIR /app
# COPY pyproject.toml poetry.lock ./
# RUN POETRY_VIRTUALENVS_IN_PROJECT=true \
# 	poetry install

# FROM base AS dev
# RUN apt-get update && apt-get -y install --no-install-recommends \
# 	libnss-mdns \
# 	libusb-1.0
# WORKDIR /app
# COPY --from=build /app/.venv ./.venv/
# COPY
# ENV PYTHONUNBUFFERED=1
# ENV PATH=/app/.venv/bin:$PATH
# CMD ["python", "main.py"]

# FROM dev
# COPY . /app/
