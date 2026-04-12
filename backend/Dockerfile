FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
  'fastapi>=0.116.0' \
  'uvicorn[standard]>=0.32.0' \
  'httpx>=0.27.0' \
  'pydantic>=2.9.0' \
  'pydantic-settings>=2.5.0'

COPY backend/app /app/app

EXPOSE 1315
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "1315"]
