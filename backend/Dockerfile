# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
# Optional: behind a TLS-intercepting proxy, pass its CA as a build secret named "extra_ca"
# (see README, "Building behind a corporate proxy"). Nothing is stored in the image.
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export PIP_CERT=/run/secrets/extra_ca; fi; \
    pip install -r requirements.txt

COPY app ./app
RUN useradd --create-home --uid 10001 seg && mkdir -p /app/data && chown -R seg /app/data
USER seg

ENV DATABASE_URL=sqlite:////app/data/energy_guardian.db \
    MODEL_DIR=/app/data/models
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status == 200 else 1)"
CMD ["uvicorn", "app.asgi:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
