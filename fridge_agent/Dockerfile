FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 FRIDGE_MODE=server FRIDGE_DATA_DIR=/var/lib/hankki PORT=8000
WORKDIR /srv/fridge_agent
COPY --chown=10001:10001 backend /srv/backend
COPY --chown=10001:10001 fridge_agent /srv/fridge_agent
RUN --mount=type=secret,id=ca_bundle if [ -f /run/secrets/ca_bundle ]; then export PIP_CERT=/run/secrets/ca_bundle; fi; \
    pip install --no-cache-dir -r requirements.txt && \
    useradd --system --uid 10001 hankki && mkdir -p /var/lib/hankki && chown hankki /var/lib/hankki
USER hankki
EXPOSE 8000
CMD ["sh","-c","exec python -m uvicorn app:app --host 0.0.0.0 --port \"$PORT\" --no-access-log"]
