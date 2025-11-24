FROM debian:trixie

ARG UID
ARG GID

RUN apt update && \
    apt install -y curl gcc && \
    groupadd --gid ${GID} build && \
    useradd --create-home --gid ${GID} --uid ${UID} build

RUN curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/bin sh
