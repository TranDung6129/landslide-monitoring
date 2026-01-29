#!/usr/bin/env python3

import json
import time
import random
import os 
import paho.mqtt.client as mqtt # type: ignore
from datetime import datetime
from typing import Dict, Any

class RainSensor:
    def __init__(self, config_path: str = "sensors_config.json"):
        """Khởi tạo cảm biến mưa"""
        
        # --- PHẦN 1: ĐỌC CẤU HÌNH HẠ TẦNG TỪ DOCKER (ENV) ---
        # Đây là những thứ bạn đã xóa khỏi JSON, giờ lấy từ Docker
        self.mqtt_broker = os.getenv('MQTT_BROKER', 'localhost')
        self.mqtt_port = int(os.getenv('MQTT_PORT', 1883))
        self.cluster_id = os.getenv('CLUSTER_ID', 'cluster_01')
        self.sensor_type = os.getenv('SENSOR_TYPE', 'rain') 
        
        # Tự động tạo ID và Topic dựa trên thông tin môi trường
        # Ví dụ: rain_01_cluster_01 (đảm bảo duy nhất)
        self.sensor_id = f"{self.sensor_type}_01_{self.cluster_id}"
        # Topic chuẩn: sensors/cluster_01/rain
        self.topic = f"sensors/{self.cluster_id}/{self.sensor_type}"

        # --- PHẦN 2: ĐỌC CẤU HÌNH LOGIC TỪ JSON ---
        self.config = {}
        try:
            with open(config_path, 'r') as f:
                full_config = json.load(f)
                # QUAN TRỌNG: Dùng self.sensor_type ('rain') để lấy đúng cục config trong JSON
                self.sensor_config = full_config.get(self.sensor_type, {})
        except Exception as e:
            print(f"[{self.sensor_id}] Lỗi đọc config: {e}. Dùng mặc định.")
            self.sensor_config = {}

        # Lấy tham số vận hành (Nếu thiếu trong JSON thì dùng mặc định code)
        self.frequency = self.sensor_config.get('frequency', 1.0)
        self.unit = self.sensor_config.get('unit', 'mm')
        
        # Cấu hình mô phỏng (Đi sâu vào key 'simulation')
        sim_config = self.sensor_config.get('simulation', {})
        self.base_rainfall_rate = sim_config.get('base_rainfall_rate', 0.0)
        self.rainfall_variation = sim_config.get('rainfall_variation', 5.0)
        self.accumulation_period = sim_config.get('accumulation_period', 60)
        
        # Trạng thái nội tại
        self.accumulated_rainfall = 0.0
        self.last_update_time = time.time()
        
        # --- PHẦN 3: KẾT NỐI MQTT ---
        # Client ID prefix lấy mặc định hoặc từ env, cộng với sensor_id
        client_prefix = os.getenv('CLIENT_PREFIX', 'sim')
        # Sử dụng callback API version 2 để tránh deprecation warning
        self.client = mqtt.Client(
            client_id=f"{client_prefix}_{self.sensor_id}",
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2
        )
        self.client.on_connect = self.on_connect
        self.client.on_publish = self.on_publish
        
    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        """Callback khi kết nối MQTT (API version 2)"""
        if reason_code == 0:
            print(f"[{self.sensor_id}] Connected to MQTT broker at {self.mqtt_broker}")
            print(f"[{self.sensor_id}] Target Topic: {self.topic}")
        else:
            print(f"[{self.sensor_id}] Failed to connect, return code {reason_code}")
    
    def on_publish(self, client, userdata, mid):
        pass
    
    def connect(self):
        """Kết nối đến MQTT broker với retry logic"""
        max_retries = 30  # Thử tối đa 30 lần
        retry_delay = 2   # Bắt đầu với 2 giây
        
        for attempt in range(max_retries):
            try:
                # Kết nối dùng biến lấy từ Docker
                self.client.connect(self.mqtt_broker, self.mqtt_port, 60)
                self.client.loop_start()
                # Đợi một chút để xác nhận kết nối thành công
                time.sleep(1)
                if self.client.is_connected():
                    return
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"[{self.sensor_id}] Error connecting to MQTT (attempt {attempt + 1}/{max_retries}): {e}")
                    print(f"[{self.sensor_id}] Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 1.5, 30)  # Exponential backoff, max 30s
                else:
                    print(f"[{self.sensor_id}] Failed to connect to MQTT after {max_retries} attempts: {e}")
                    raise
    
    def generate_rainfall_intensity(self) -> float:
        """Tạo cường độ mưa (mm/h)"""
        intensity = self.base_rainfall_rate + random.uniform(
            -self.rainfall_variation,
            self.rainfall_variation
        )
        return max(0.0, intensity)
    
    def update_accumulated_rainfall(self, intensity: float, time_delta: float):
        rainfall_increment = (intensity / 3600.0) * time_delta
        self.accumulated_rainfall += rainfall_increment
    
    def create_data_packet(self, intensity: float, accumulated: float) -> Dict[str, Any]:
        """Tạo gói dữ liệu JSON"""
        # Timestamp rất quan trọng cho Spark xử lý cửa sổ thời gian
        timestamp = datetime.now().isoformat()
        
        return {
            "timestamp": timestamp,
            "cluster_id": self.cluster_id,   # Lấy từ Docker
            "sensor_id": self.sensor_id,     # Tự sinh
            "sensor_type": self.sensor_type, # Lấy từ Docker
            "value": {
                "intensity": round(intensity, 2),
                "accumulated": round(accumulated, 2)
            },
            "unit": {
                "intensity": "mm/h",
                "accumulated": self.unit
            }
        }
    
    def publish_data(self, data: Dict[str, Any]):
        payload = json.dumps(data, ensure_ascii=False)
        self.client.publish(self.topic, payload, qos=1)
        # In log ra màn hình để debug
        print(f"[{self.sensor_id}] Sent: {payload}")
    
    def run(self):
        self.connect()
        # Tính thời gian ngủ
        sleep_interval = 1.0 / self.frequency if self.frequency > 0 else 1.0
        
        try:
            while True:
                current_time = time.time()
                time_delta = current_time - self.last_update_time
                
                # Logic sinh dữ liệu
                intensity = self.generate_rainfall_intensity()
                self.update_accumulated_rainfall(intensity, time_delta)
                
                # Đóng gói và gửi
                data = self.create_data_packet(intensity, self.accumulated_rainfall)
                self.publish_data(data)
                
                self.last_update_time = current_time
                time.sleep(sleep_interval)
                
        except KeyboardInterrupt:
            print(f"\n[{self.sensor_id}] Stopping sensor...")
            self.client.loop_stop()
            self.client.disconnect()

if __name__ == "__main__":
    sensor = RainSensor()
    sensor.run()