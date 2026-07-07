# CodeCheck — AI-powered code review harness
FROM python:3.12-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install CodeCheck
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

# Runtime directory
WORKDIR /workspace
RUN mkdir -p /root/.codecheck

VOLUME ["/workspace", "/root/.codecheck"]

ENTRYPOINT ["codecheck"]
CMD ["--help"]