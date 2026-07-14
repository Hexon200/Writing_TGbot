FROM python:3.12-slim

WORKDIR /app

# Install build dependencies if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependencies and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Ensure data directory exists
RUN mkdir -p data

# Convert line endings of start.sh to Unix format and make it executable
RUN sed -i 's/\r$//' start.sh && chmod +x start.sh

# Expose port (Railway will override this with its own $PORT environment variable)
EXPOSE 8080

# Launch the unified startup script
CMD ["./start.sh"]
