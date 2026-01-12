import json
import time
import paho.mqtt.client as mqtt
from kafka import KafkaProducer

# Cấu hình
MQTT_BROKER = "mosquitto"
MQTT_TOPIC = "sensors/#" 
KAFKA_BROKER = "kafka:29092"
KAFKA_TOPIC = "landslide_data"

# Kết nối Kafka (Thử lại cho đến khi thành công)
producer = None
while producer is None:
    try:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BROKER,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        print(">>> Bridge: Da ket noi Kafka thanh cong!")
    except Exception as e:
        print(f">>> Bridge: Cho Kafka khoi dong... ({e})")
        time.sleep(5)

# Xử lý khi có tin nhắn từ MQTT
def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        # Thêm topic gốc vào dữ liệu để biết nguồn
        payload['mqtt_topic'] = msg.topic
        producer.send(KAFKA_TOPIC, payload)
        print(f" -> Da chuyen ti: {msg.topic}")
    except Exception as e:
        print(f"Loi xu ly: {e}")

# Kết nối MQTT
client = mqtt.Client()
client.on_message = on_message
while True:
    try:
        client.connect(MQTT_BROKER, 1883, 60)
        client.subscribe(MQTT_TOPIC)
        print(f">>> Bridge: Da ket noi MQTT va dang nghe {MQTT_TOPIC}")
        client.loop_forever()
    except Exception as e:
        print(f"Loi MQTT: {e}. Thu lai sau 5s...")
        time.sleep(5)
