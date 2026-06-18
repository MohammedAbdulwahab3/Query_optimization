FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY generator.py writers.py main.py ./

# Generates synthetic CDRs and dual-writes to ClickHouse + Memgraph, then exits.
CMD ["python", "main.py"]
