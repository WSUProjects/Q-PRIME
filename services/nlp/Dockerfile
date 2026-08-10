FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

ENV PYTHONUNBUFFERED=1

EXPOSE 5500

CMD ["gunicorn", "--bind", "0.0.0.0:5500", "--workers", "1", "--threads", "8", "--timeout", "120", "app:app"]
