FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY backend /app/backend
WORKDIR /app/backend
EXPOSE 8000
# Shell form (not the JSON-array form) so ${PORT} actually gets substituted --
# Railway/Render inject PORT at runtime and expect the app to bind to it;
# the array form CMD ["uvicorn", ..., "--port", "8000"] can't read env vars
# at all, it would just always bind to the literal string "8000".
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
