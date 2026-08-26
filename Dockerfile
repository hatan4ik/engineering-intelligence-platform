FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
RUN useradd --create-home --shell /usr/sbin/nologin --uid 10001 eip

# The API imports these first-party modules at startup, on its Azure-backed
# query path, or when an optional capability is enabled (see app/runtime_wiring.py).
# Keep the image limited to that runtime closure rather than copying tests,
# infrastructure, and design artifacts into the release image. The list must
# match app.import_closure.SHIPPED_PACKAGES; CI imports every shipped module.
COPY --chown=eip:eip app /app/app
COPY --chown=eip:eip feedback /app/feedback
COPY --chown=eip:eip finops /app/finops
COPY --chown=eip:eip integrations /app/integrations
COPY --chown=eip:eip ingestion /app/ingestion
COPY --chown=eip:eip intelligence /app/intelligence
COPY --chown=eip:eip portal /app/portal
COPY --chown=eip:eip product /app/product
COPY --chown=eip:eip security /app/security
COPY --chown=eip:eip telemetry /app/telemetry
# The same immutable image is used by the API and the separately deployed
# Temporal worker.  These modules contain the fail-closed worker boundary, not
# test fixtures or infrastructure definitions.
COPY --chown=eip:eip control_plane /app/control_plane
COPY --chown=eip:eip orchestration /app/orchestration
COPY --chown=eip:eip state /app/state
# The operational-intelligence routes (app/operations_api.py) resolve a blast
# radius from the topology store before proposing anything.
COPY --chown=eip:eip topology /app/topology

EXPOSE 8000
USER eip
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
