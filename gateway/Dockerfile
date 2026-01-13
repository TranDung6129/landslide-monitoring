FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY mqtt_to_kafka.py .
CMD ["python", "-u", "mqtt_to_kafka.py"]

