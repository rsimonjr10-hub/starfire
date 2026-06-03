FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY . .

# Make startup script executable
RUN chmod +x scripts/start.sh

# Create non-root user
RUN useradd -m -u 1001 starfire && chown -R starfire:starfire /app
USER starfire

# Railway injects PORT — default 8000
EXPOSE 8000

CMD ["sh", "scripts/start.sh"]
