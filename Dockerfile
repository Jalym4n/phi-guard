# phi-guard Studio in a container.
#   docker build -t phi-guard-studio .
#   docker run --rm -p 127.0.0.1:8765:8765 phi-guard-studio
# Then open the address printed in the logs (it contains the session token).
# Publishing to 127.0.0.1 keeps Studio reachable from this computer only.

FROM node:22-bookworm-slim AS ui
WORKDIR /ui
COPY studio-ui/package.json studio-ui/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY studio-ui/ ./
RUN mkdir -p /src/phi_guard_studio && npx tsc -b && npx vite build --outDir /out --emptyOutDir

FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# Tesseract reads scanned PDFs and faxes (English and French).
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-fra \
 && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 10001 studio
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY --from=ui /out ./src/phi_guard_studio/static
RUN pip install ".[studio]" && rm -rf /root/.cache \
 && mkdir -p /home/studio/data && chown studio:studio /home/studio/data && chmod 700 /home/studio/data
USER studio
VOLUME ["/home/studio/data"]
EXPOSE 8765
# Inside the container Studio must listen on all interfaces so Docker can forward the port;
# --allow-network acknowledges that. Bind the published port to 127.0.0.1 on the host (see above).
CMD ["phi-guard-studio", "--host", "0.0.0.0", "--allow-network", "--port", "8765", "--no-browser", "--data-dir", "/home/studio/data"]
