#!/usr/bin/env python3

import json
import time
import random
import os  # <--- THÊM: Để đọc biến môi trường
import paho.mqtt.client as mqtt
from datetime import datetime
from typing import Dict, Any

class GroundwaterSensor:
    def __init__(self, config_path: str = "sensors_config.json"):
        """Khởi tạo cảm biến nước ngầm"""
        
        # --- PHẦN 1: ĐỌC CẤU HÌNH HẠ TẦNG TỪ DOCKER (ENV) ---
        self.mqtt_broker = os.getenv('MQTT_BROKER', 'localhost')
        self.mqtt_port = int(os.getenv('MQTT_PORT', 1883))
        self.cluster_id = os.getenv('CLUSTER_ID', 'cluster_01')
        self.sensor_type = os.getenv('SENSOR_TYPE', 'groundwater') # Mặc định là groundwater
        
        # Tự động tạo ID và Topic dựa trên thông tin môi trường
        self.sensor_id = f"{self.sensor_type}_01_{self.cluster_id}"
        self.topic = f"sensors/{self.cluster_id}/{self.sensor_type}"

        # --- PHẦN 2: ĐỌC CẤU HÌNH LOGIC TỪ JSON ---
        self.config = {}
        try:
            with open(config_path, 'r') as f:
                full_config = json.load(f)
                # Dùng sensor_type để lấy đúng cục config trong JSON
                self.sensor_config = full_config.get(self.sensor_type, {})
        except Exception as e:
            print(f"[{self.sensor_id}] Lỗi đọc config: {e}. Dùng mặc định.")
            self.sensor_config = {}
        
        # Lấy tham số vận hành
        self.frequency = self.sensor_config.get('frequency', 1.0)
        self.unit = self.sensor_config.get('unit', 'm')
        
        # Cấu hình mô phỏng (Lấy từ block 'simulation')
        sim_config = self.sensor_config.get('simulation', {})
        self.base_water_level = sim_config.get('base_water_level', 2.5)
        self.water_level_variation = sim_config.get('water_level_variation', 0.1)
        self.base_pore_pressure = sim_config.get('base_pore_pressure', 24.5)
        self.pore_pressure_variation = sim_config.get('pore_pressure_variation', 1.0)
        
        # Trạng thái cảm biến
        self.current_water_level = self.base_water_level
        self.current_pore_pressure = self.base_pore_pressure
        
        # --- PHẦN 3: KẾT NỐI MQTT ---
        client_prefix = os.getenv('CLIENT_PREFIX', 'sim')
        self.client = mqtt.Client(client_id=f"{client_prefix}_{self.sensor_id}")
        self.client.on_connect = self.on_connect
        self.client.on_publish = self.on_publish
        
    def on_connect(self, client, userdata, flags, rc):
        """Callback khi kết nối MQTT"""
        if rc == 0:
            print(f"[{self.sensor_id}] Connected to MQTT broker at {self.mqtt_broker}")
            print(f"[{self.sensor_id}] Target Topic: {self.topic}")
        else:
            print(f"[{self.sensor_id}] Failed to connect, return code {rc}")
    
    def on_publish(self, client, userdata, mid):
        """Callback khi publish thành công"""
        pass
    
    def connect(self):
        """Kết nối đến MQTT broker"""
        try:
            # Sử dụng biến từ Docker env
            self.client.connect(self.mqtt_broker, self.mqtt_port, 60)
            self.client.loop_start()
        except Exception as e:
            print(f"[{self.sensor_id}] Error connecting to MQTT: {e}")
            raise
    
    def generate_water_level(self) -> float:
        """Tạo mực nước ngầm (m)"""
        # Mô phỏng mực nước với biến thiên ngẫu nhiên
        variation = random.uniform(
            -self.water_level_variation,
            self.water_level_variation
        )
        self.current_water_level = self.base_water_level + variation
        return self.current_water_level
    
    def generate_pore_pressure(self, water_level: float) -> float:
        """Tạo áp lực nước lỗ rỗng (kPa)"""
        # Áp lực nước lỗ rỗng tỷ lệ với mực nước
        # P = ρgh, với ρ = 1000 kg/m³, g = 9.81 m/s²
        # Chuyển từ Pa sang kPa: P_kPa = (ρgh) / 1000
        theoretical_pressure = (1000 * 9.81 * water_level) / 1000
        
        # Thêm biến thiên ngẫu nhiên
        variation = random.uniform(
            -self.pore_pressure_variation,
            self.pore_pressure_variation
        )
        self.current_pore_pressure = theoretical_pressure + variation
        return self.current_pore_pressure
    
    def create_data_packet(self, water_level: float, pore_pressure: float) -> Dict[str, Any]:
        """Tạo gói dữ liệu JSON"""
        timestamp = datetime.now().isoformat()
        
        return {
            "timestamp": timestamp,
            "cluster_id": self.cluster_id,   # Lấy từ Docker
            "sensor_id": self.sensor_id,     # Tự sinh
            "sensor_type": self.sensor_type, # Lấy từ Docker
            "value": {
                "water_level": round(water_level, 3),
                "pore_pressure": round(pore_pressure, 2)
            },
            "unit": {
                "water_level": self.unit,
                "pore_pressure": "kPa"
            }
        }
    
    def publish_data(self, data: Dict[str, Any]):
        """Gửi dữ liệu lên MQTT"""
        payload = json.dumps(data, ensure_ascii=False)
        result = self.client.publish(self.topic, payload, qos=1)
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"[{self.sensor_id}] Published: Water={data['value']['water_level']}m, Pressure={data['value']['pore_pressure']}kPa")
        else:
            print(f"[{self.sensor_id}] Failed to publish: {result.rc}")
    
    def run(self):
        """Chạy cảm biến liên tục"""
        self.connect()
        # Tính thời gian ngủ an toàn
        sleep_interval = 1.0 / self.frequency if self.frequency > 0 else 1.0
        
        try:
            while True:
                # Tạo dữ liệu nước ngầm
                water_level = self.generate_water_level()
                pore_pressure = self.generate_pore_pressure(water_level)
                
                # Tạo và gửi gói dữ liệu
                data = self.create_data_packet(water_level, pore_pressure)
                self.publish_data(data)
                
                time.sleep(sleep_interval)
                
        except KeyboardInterrupt:
            print(f"\n[{self.sensor_id}] Stopping sensor...")
            self.client.loop_stop()
            self.client.disconnect()

if __name__ == "__main__":
    sensor = GroundwaterSensor()
    sensor.run()