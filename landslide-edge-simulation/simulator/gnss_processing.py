#!/usr/bin/env python3

import json
import time
import random
import math
import os  
import paho.mqtt.client as mqtt # type:ignore  
from datetime import datetime
from typing import Dict, Any, Tuple

class GNSSSensor:
    def __init__(self, config_path: str = "sensors_config.json"):
        """Khởi tạo cảm biến GNSS"""
        
        # --- PHẦN 1: ĐỌC CẤU HÌNH HẠ TẦNG TỪ DOCKER (ENV) ---
        self.mqtt_broker = os.getenv('MQTT_BROKER', 'localhost')
        self.mqtt_port = int(os.getenv('MQTT_PORT', 1883))
        self.cluster_id = os.getenv('CLUSTER_ID', 'cluster_01')
        self.sensor_type = os.getenv('SENSOR_TYPE', 'gnss') # Mặc định là gnss
        
        # Tự động tạo ID và Topic
        self.sensor_id = f"{self.sensor_type}_01_{self.cluster_id}"
        self.topic = f"sensors/{self.cluster_id}/{self.sensor_type}"

        # --- PHẦN 2: ĐỌC CẤU HÌNH LOGIC TỪ JSON ---
        self.config = {}
        try:
            with open(config_path, 'r') as f:
                full_config = json.load(f)
                self.sensor_config = full_config.get(self.sensor_type, {})
        except Exception as e:
            print(f"[{self.sensor_id}] Lỗi đọc config: {e}. Dùng mặc định.")
            self.sensor_config = {}
        
        # Lấy tham số vận hành
        self.frequency = self.sensor_config.get('frequency', 1.0)
        self.unit = self.sensor_config.get('unit', 'degrees')
        
        # Cấu hình mô phỏng
        sim_config = self.sensor_config.get('simulation', {})
        self.base_latitude = sim_config.get('base_latitude', 21.0285)  # Mặc định Hà Nội
        self.base_longitude = sim_config.get('base_longitude', 105.8542)
        self.position_noise = sim_config.get('position_noise', 0.00001)
        
        # Trạng thái cảm biến
        self.current_latitude = self.base_latitude
        self.current_longitude = self.base_longitude
        
        # --- PHẦN 3: KẾT NỐI MQTT ---
        client_prefix = os.getenv('CLIENT_PREFIX', 'sim')
        self.client = mqtt.Client(client_id=f"{client_prefix}_{self.sensor_id}")
        self.client.on_connect = self.on_connect
        self.client.on_publish = self.on_publish
        
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"[{self.sensor_id}] Connected to MQTT broker at {self.mqtt_broker}")
            print(f"[{self.sensor_id}] Target Topic: {self.topic}")
        else:
            print(f"[{self.sensor_id}] Failed to connect, return code {rc}")
    
    def on_publish(self, client, userdata, mid):
        pass
    
    def connect(self):
        try:
            self.client.connect(self.mqtt_broker, self.mqtt_port, 60)
            self.client.loop_start()
        except Exception as e:
            print(f"[{self.sensor_id}] Error connecting to MQTT: {e}")
            raise
    
    def generate_position(self) -> Tuple[float, float]:
        """Tạo vị trí GPS (latitude, longitude)"""
        # Mô phỏng vị trí với biến thiên ngẫu nhiên (Drift nhỏ)
        lat_noise = random.uniform(-self.position_noise, self.position_noise)
        lon_noise = random.uniform(-self.position_noise, self.position_noise)
        
        # Cập nhật vị trí hiện tại (Random Walk)
        # self.current_latitude += lat_noise * 0.1 # Nếu muốn mô phỏng trôi dạt từ từ
        
        # Hoặc chỉ dao động quanh điểm gốc (Noise only)
        sim_lat = self.base_latitude + lat_noise
        sim_lon = self.base_longitude + lon_noise
        
        return sim_lat, sim_lon
    
    def wgs84_to_vn2000(self, lat: float, lon: float) -> Tuple[float, float, float]:
        """
        Chuyển đổi từ WGS84 (lat/lon) sang VN-2000 (x, y, z) - MÔ PHỎNG
        """
        # Tham số ellipsoid WGS84
        a = 6378137.0  # Bán trục lớn (m)
        e2 = 0.00669437999014  # Độ lệch tâm bình phương
        
        lat_rad = math.radians(lat)
        lon_rad = math.radians(lon)
        lon0_rad = math.radians(105.0) # Kinh tuyến trục 105°00'
        
        # Tính bán kính cong vòng thẳng đứng đầu (Radius of curvature in the prime vertical)
        N = a / math.sqrt(1 - e2 * math.sin(lat_rad)**2)
        
        # Công thức mô phỏng đơn giản hóa để ra tọa độ phẳng (Projection Approximation)
        # Lưu ý: Đây CHƯA PHẢI công thức chuẩn xác của Bộ TNMT (rất phức tạp)
        # Nhưng đủ để tạo ra dữ liệu X, Y có ý nghĩa mét tương đối
        
        # Delta Longitude
        dLon = lon_rad - lon0_rad
        
        # Tọa độ X (Bắc - Nam), Y (Đông - Tây) trên mặt phẳng chiếu
        # Xấp xỉ đơn giản:
        x_vn2000 = (lat_rad * a) # Khoảng cách từ xích đạo
        y_vn2000 = (dLon * a * math.cos(lat_rad)) + 500000 # Cộng 500km để tránh số âm (False Easting)
        
        # Z là độ cao (giả sử độ cao ellip ~ độ cao trắc địa cho đơn giản)
        z_vn2000 = random.uniform(10.0, 10.5) # Giả lập độ cao
        
        return x_vn2000, y_vn2000, z_vn2000
    
    def create_data_packet(self, lat: float, lon: float) -> Dict[str, Any]:
        """Tạo gói dữ liệu JSON"""
        timestamp = datetime.now().isoformat()
        x, y, z = self.wgs84_to_vn2000(lat, lon)
        
        return {
            "timestamp": timestamp,
            "cluster_id": self.cluster_id,   # Docker Env
            "sensor_id": self.sensor_id,     # Generated
            "sensor_type": self.sensor_type, # Docker Env
            "value": {
                "latitude": round(lat, 8),
                "longitude": round(lon, 8),
                "vn2000": {
                    "x": round(x, 3), # Tọa độ mét (Bắc)
                    "y": round(y, 3), # Tọa độ mét (Đông)
                    "z": round(z, 3)  # Độ cao
                }
            },
            "unit": {
                "latitude": self.unit,
                "longitude": self.unit,
                "vn2000": "m"
            }
        }
    
    def publish_data(self, data: Dict[str, Any]):
        payload = json.dumps(data, ensure_ascii=False)
        self.client.publish(self.topic, payload, qos=1)
        
        # Chỉ in log đơn giản
        pos = data['value']
        print(f"[{self.sensor_id}] Sent: Lat={pos['latitude']}, Lon={pos['longitude']}")
    
    def run(self):
        """Chạy cảm biến liên tục"""
        self.connect()
        sleep_interval = 1.0 / self.frequency if self.frequency > 0 else 1.0
        
        try:
            while True:
                # Tạo dữ liệu GNSS
                lat, lon = self.generate_position()
                
                # Tạo và gửi gói dữ liệu
                data = self.create_data_packet(lat, lon)
                self.publish_data(data)
                
                time.sleep(sleep_interval)
                
        except KeyboardInterrupt:
            print(f"\n[{self.sensor_id}] Stopping sensor...")
            self.client.loop_stop()
            self.client.disconnect()

if __name__ == "__main__":
    sensor = GNSSSensor()
    sensor.run()