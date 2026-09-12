FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data/tmp /app/data/repositories

EXPOSE 8000

# Runs pending Alembic migrations, then starts the server. In a real
# production deploy this migration step is usually a separate CI/CD job
# rather than baked into the container start, but for a self-contained
# `docker compose up` demo this keeps it a single working command.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
