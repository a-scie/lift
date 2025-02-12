ARG BASE_IMAGE=invalid
FROM ${BASE_IMAGE}

RUN python -mvenv /uv.venv && \
    /uv.venv/bin/python -mpip install uv && \
    ln -s /uv.venv/bin/uv /usr/bin/uv

ENV UV_FIND_LINKS=/wheels
ENV UV_INDEX_STRATEGY=unsafe-first-match
RUN mkdir "${UV_FIND_LINKS}"

ARG SRC_WHEEL_DIR
COPY "${SRC_WHEEL_DIR}/*.whl" "${UV_FIND_LINKS}/"
