ARG BASE_IMAGE=scratch
FROM ${BASE_IMAGE}

VOLUME /code
WORKDIR /code

COPY --from=ephemeral pyproject.toml .
COPY --from=ephemeral uv.lock .
RUN chown -R build:build /code

USER build
ENV UV_LINK_MODE=copy
RUN uv sync --frozen --no-install-project && rm pyproject.toml uv.lock

ENTRYPOINT ["uv", "run", "dev-cmd"]