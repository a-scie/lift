ARG BASE_IMAGE=scratch
FROM ${BASE_IMAGE}

VOLUME /code
WORKDIR /code

COPY --from=ephemeral pyproject.toml .
COPY --from=ephemeral uv.lock .
RUN chown -R build:build /code

USER build

# Work around SIGSEGVs and other errors under some qemu targets.
ENV UV_CONCURRENT_BUILDS=1
# Silence warning about needing to copy since we know /code/.venv lives on a bind mount.
ENV UV_LINK_MODE=copy

RUN uv sync --frozen --no-install-project && rm pyproject.toml uv.lock

ENTRYPOINT ["uv", "run", "--frozen", "dev-cmd"]