FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
RUN useradd --create-home --shell /usr/sbin/nologin --uid 10001 eip

# The API imports these first-party modules at startup or on its Azure-backed
# query path. Keep the image limited to the API runtime closure rather than
# copying tests, infrastructure, and design artifacts into the release image.
COPY --chown=eip:eip app /app/app
COPY --chown=eip:eip feedback /app/feedback
COPY --chown=eip:eip finops /app/finops
COPY --chown=eip:eip integrations /app/integrations
COPY --chown=eip:eip portal /app/portal
COPY --chown=eip:eip security /app/security
COPY --chown=eip:eip telemetry /app/telemetry

EXPOSE 8000
USER eip
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
