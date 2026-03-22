FROM python:3.12-slim

# Install uv
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies into a virtual environment
RUN uv sync --frozen --no-dev

# Copy source code
COPY src/ ./src/

# Expose Prometheus metrics port
EXPOSE 9090

CMD ["uv", "run", "python", "-m", "src.main"]
