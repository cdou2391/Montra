# syntax=docker/dockerfile:1

# ------------------------------------------------------------------- builder
# Compilers and headers live here and are never copied forward: the runtime
# needs the built wheels, not the toolchain that produced them.
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# A virtualenv rather than the system site-packages, so one directory carries
# everything the application needs and can be copied whole.
RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir --upgrade pip setuptools

# Two layers on purpose: production installs the runtime set, and the dev stage
# adds the test tooling on top without a second resolution of the first.
RUN pip install --no-cache-dir -r requirements.txt

# ----------------------------------------------------------------------- dev
# Test tooling, the source bind-mounted over /app, and pip left in place — a
# development image is a place to run pytest and pip-audit from.
FROM builder AS dev
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements-dev.txt
WORKDIR /app
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# -------------------------------------------------------------------- runner
# libpq only — the client library psycopg links against, without the headers
# and compilers used to build it.
FROM python:3.12-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/venv/bin:$PATH"

# upgrade, not just install: the published base lags Debian's security
# updates by however long it has been since it was last rebuilt, and a scanner
# reports what is installed rather than whose fault it is.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    # pip is not needed to run the application, and every advisory the scan
    # reported against this image was inside pip's own vendored tree.
    && rm -rf /usr/local/lib/python3.12/site-packages/pip \
              /usr/local/lib/python3.12/site-packages/pip-* \
              /usr/local/bin/pip /usr/local/bin/pip3 \
    && useradd --create-home --uid 10001 montra

COPY --from=builder --chown=montra:montra /venv /venv
# The venv brings its own pip, which the system-level removal above does not
# reach. Nothing installs at runtime, so it goes too.
RUN rm -rf /venv/lib/python3.12/site-packages/pip \
           /venv/lib/python3.12/site-packages/pip-* \
           /venv/bin/pip /venv/bin/pip3 /venv/bin/pip3.12

WORKDIR /app
COPY --chown=montra:montra . .

USER montra
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
