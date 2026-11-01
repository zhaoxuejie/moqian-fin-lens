FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

ARG PIP_INDEX_URL=https://pypi.org/simple

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --index-url "${PIP_INDEX_URL}" .

RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
