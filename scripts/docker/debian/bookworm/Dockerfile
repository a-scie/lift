FROM python:3.14-bookworm

ARG UID
ARG GID

RUN pip install --root-user-action ignore uv && \
    addgroup --gid ${GID} build && \
    adduser --disabled-password --gecos '' --gid ${GID} --uid ${UID} build

COPY post-install.sh /post-install.sh
RUN /post-install.sh && rm /post-install.sh
