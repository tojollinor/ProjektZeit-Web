FROM python:3.12-alpine

RUN apk add --no-cache tzdata ca-certificates
RUN addgroup -S projektzeit && adduser -S projektzeit -G projektzeit
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
# Alle Python-Module der Anwendung kopieren. So werden neue Runtime-Module
# nicht versehentlich aus dem Image ausgespart.
COPY *.py /app/
COPY static /app/static
RUN mkdir -p /app/data && chown -R projektzeit:projektzeit /app
USER projektzeit
ENV HOST=0.0.0.0 PORT=8080 DATA_DIR=/app/data PYTHONDONTWRITEBYTECODE=1 TZ=Europe/Berlin
EXPOSE 8080
VOLUME ["/app/data"]
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 CMD wget -qO- http://127.0.0.1:8080/health || exit 1
CMD ["python", "-u", "-c", "import app, customer_runtime, feature_runtime, contact_runtime, ux_runtime, provider_cache_runtime, api_runtime, zammad_cache_runtime, provider_nav_runtime, worktime_runtime, customer_extra_runtime, next_batch_runtime, frontend_update_runtime; customer_runtime.install(app); feature_runtime.install(app); contact_runtime.install(app); ux_runtime.install(app); provider_cache_runtime.install(app); api_runtime.install(app); zammad_cache_runtime.install(app); provider_nav_runtime.install(app); worktime_runtime.install(app); customer_extra_runtime.install(app); next_batch_runtime.install(app); frontend_update_runtime.install(app); app.init_db(); print('ProjektZeit Web läuft auf http://%s:%d' % (app.HOST, app.PORT)); app.ThreadingHTTPServer((app.HOST, app.PORT), app.App).serve_forever()"]
