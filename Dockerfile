# CodeCheck Docker Image
# Multi-stage build for minimal runtime image size.
#
# Build:
#   docker build -t codecheck .
#
# Run:
#   docker run -v $(pwd):/workspace -v ~/.codecheck:/root/.codecheck codecheck review /workspace
#
# Or with docker-compose:
#   docker-compose run --rm codecheck review /workspace

# ---- Builder stage ----
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN pip install --no-cache-dir hatchling

# Copy source and build
COPY pyproject.toml README.md ./
COPY src/ src/
COPY .codecheck/ .codecheck/

# Build the wheel
RUN pip wheel --no-cache-dir --wheel-dir=/wheels .

# ---- Runtime stage ----
FROM python:3.12-slim AS runtime

# Install system dependencies (git is required for git diff/log tools)
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# Install the wheel
COPY --from=builder /wheels/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# Install optional dev dependencies for lint/test support
RUN pip install --no-cache-dir ruff pytest

# Create a non-root user for better security
RUN useradd --create-home --shell /bin/bash codecheck && \
    mkdir -p /home/codecheck/.codecheck && \
    chown -R codecheck:codecheck /home/codecheck/.codecheck

USER codecheck
WORKDIR /workspace

ENTRYPOINT ["codecheck"]
CMD ["--help"]