FROM python:3.12-alpine

RUN apk add --no-cache tzdata ca-certificates
RUN addgroup -S projektzeit && adduser -S projektzeit -G projektzeit
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py workday.py integrations.py database.py starface_oauth.py migrate_sqlite.py provider_lists.py starface_calls.py customer_data.py customer_runtime.py /app/
COPY static /app/static
RUN mkdir -p /app/data && chown -R projektzeit:projektzeit /app
USER projektzeit
ENV HOST=0.0.0.0 PORT=8080 DATA_DIR=/app/data PYTHONDONTWRITEBYTECODE=1 TZ=Europe/Berlin
EXPOSE 8080
VOLUME ["/app/data"]
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 CMD wget -qO- http://127.0.0.1:8080/health || exit 1
CMD ["python", "-u", "-c", "import app, customer_runtime; customer_runtime.serve(app)"]
