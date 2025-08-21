FROM debian:trixie

ARG UID
ARG GID

RUN apt update && \
    apt install -y curl gcc python3-dev python3.13-venv python-is-python3 && \
    groupadd --gid ${GID} build && \
    useradd --create-home --gid ${GID} --uid ${UID} build

RUN python -mvenv /venv && \
    /venv/bin/pip install --root-user-action ignore uv && \
    ln -s /venv/bin/uv /usr/bin/uv
