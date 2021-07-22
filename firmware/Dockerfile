FROM python:3.9.5-slim AS base

FROM base AS build
RUN apt-get update && apt-get -y install --no-install-recommends \
	build-essential \
	libusb-1.0 \
	libudev-dev
RUN pip install \
	poetry==1.2.0a1
WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN POETRY_VIRTUALENVS_IN_PROJECT=true \
	poetry install

FROM base AS dev
RUN apt-get update && apt-get -y install --no-install-recommends \
	libnss-mdns \
	libusb-1.0
WORKDIR /app
COPY --from=build /app/.venv ./.venv/
ENV PYTHONUNBUFFERED=1
ENV PATH=/app/.venv/bin:$PATH
CMD ["python", "main.py"]

FROM dev
COPY . /app/
