# Multi-stage build for CodeCheck
# Stage 1: Build and install dependencies
FROM python:3.12-slim AS builder

WORKDIR /app
COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

# Stage 2: Runtime
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/codecheck /usr/local/bin/codecheck

# Create .codecheck directory for persistent config and credentials
RUN mkdir -p /root/.codecheck

VOLUME ["/workspace", "/root/.codecheck"]

ENTRYPOINT ["codecheck"]
CMD ["--help"]