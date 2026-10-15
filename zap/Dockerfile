FROM ghcr.io/zaproxy/zaproxy:stable

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3-pip \
    && (pip3 install --no-cache-dir --break-system-packages google-cloud-storage==2.19.0 \
        || pip3 install --no-cache-dir google-cloud-storage==2.19.0) \
    && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh upload.py /zap/
RUN chmod 755 /zap/entrypoint.sh \
    && chmod 644 /zap/upload.py \
    && chown zap:zap /zap/entrypoint.sh /zap/upload.py

ENV PYTHONUNBUFFERED=1

USER zap
WORKDIR /zap
ENTRYPOINT ["/zap/entrypoint.sh"]
