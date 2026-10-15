FROM python:3.12-slim

WORKDIR /app

RUN useradd --create-home --uid 10001 appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY templates ./templates
COPY static ./static

USER appuser

ENV PORT=8080
EXPOSE 8080

CMD ["python", "main.py"]
