FROM python:3.14-alpine

ARG UID
ARG GID

RUN pip install --root-user-action ignore uv && \
    addgroup --gid $GID build && \
    adduser -D -g '' -G build -u $UID build && \
    apk add \
        bash \
        curl \
        gcc \
        git \
        linux-headers \
        musl-dev \
        python3-dev
