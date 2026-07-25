FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=1905
EXPOSE 1905

CMD ["gunicorn", "-b", "0.0.0.0:1905", "app:app"]
