FROM python@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90 AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src HOST=0.0.0.0
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.lock
COPY src ./src
RUN mkdir /state && chown 10001:10001 /state
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/livez',timeout=3)"
CMD ["python", "-m", "market_fiyati_mcp", "--transport", "http"]

FROM runtime AS test
USER root
COPY requirements-dev.lock pyproject.toml ./
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements-dev.lock
COPY tests ./tests
USER 10001:10001
RUN --network=none python -m pytest -q -p no:cacheprovider

FROM runtime AS production
