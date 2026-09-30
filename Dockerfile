# SoftLabel — Label-Designer als Web-App
# Build:  docker build -t softlabel .
# (Optional hinter interner Spiegel-Quelle:  --build-arg PIP_INDEX_URL=https://nexus.intern/simple)
FROM python:3.12-slim

# PUID/PGID an Passende Rechte auf gemounteten Volumes anpassen (Portainer/UID 10000 üblich)
ARG PUID=1000
ARG PGID=1000
ARG PIP_INDEX_URL=https://pypi.org/simple

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --gid ${PGID} app \
    && adduser --uid ${PUID} --gid ${PGID} --disabled-password --gecos "" app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SL_DATA_DIR=/data

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --index-url ${PIP_INDEX_URL} -r requirements.txt

COPY run.py ./
COPY app ./app

RUN mkdir -p /data && chown -R app:app /data /app

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"

CMD ["python", "run.py"]
