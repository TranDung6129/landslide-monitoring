#!/usr/bin/env python3

import json
import time
import random
import math
import os  # <--- THÊM: Để đọc biến môi trường
import paho.mqtt.client as mqtt
from datetime import datetime
from typing import Dict, Any, Tuple

class IMUSensor:
    def __init__(self, config_path: str = "sensors_config.json"):
        """Khởi tạo cảm biến IMU"""
        
        # --- PHẦN 1: ĐỌC CẤU HÌNH HẠ TẦNG TỪ DOCKER (ENV) ---
        self.mqtt_broker = os.getenv('MQTT_BROKER', 'localhost')
        self.mqtt_port = int(os.getenv('MQTT_PORT', 1883))
        self.cluster_id = os.getenv('CLUSTER_ID', 'cluster_01')
        self.sensor_type = os.getenv('SENSOR_TYPE', 'imu') # Mặc định là imu
        
        # Tự động tạo ID và Topic
        self.sensor_id = f"{self.sensor_type}_01_{self.cluster_id}"
        self.topic = f"sensors/{self.cluster_id}/{self.sensor_type}"

        # --- PHẦN 2: ĐỌC CẤU HÌNH LOGIC TỪ JSON ---
        self.config = {}
        try:
            with open(config_path, 'r') as f:
                full_config = json.load(f)
                # Dùng sensor_type ('imu') để lấy config
                self.sensor_config = full_config.get(self.sensor_type, {})
        except Exception as e:
            print(f"[{self.sensor_id}] Lỗi đọc config: {e}. Dùng mặc định.")
            self.sensor_config = {}
        
        # Lấy tham số vận hành
        self.frequency = self.sensor_config.get('frequency', 10.0)
        self.unit = self.sensor_config.get('unit', 'm/s²')
        
        # Cấu hình mô phỏng (Lấy từ block 'simulation')
        sim_config = self.sensor_config.get('simulation', {})
        
        # Xử lý base_acceleration (dạng dictionary {x,y,z})
        default_accel = {'x': 0.0, 'y': 0.0, 'z': -9.81}
        self.base_acceleration = sim_config.get('base_acceleration', default_accel)
        
        # Các tham số nhiễu
        self.acceleration_noise = sim_config.get('acceleration_noise', 0.1)
        self.angular_velocity_noise = sim_config.get('angular_velocity_noise', 0.01)
        self.tilt_noise = sim_config.get('tilt_noise', 0.5)
        
        # Trạng thái cảm biến (tích phân để tính vận tốc và dịch chuyển)
        self.velocity = [0.0, 0.0, 0.0]  # vx, vy, vz
        self.displacement = [0.0, 0.0, 0.0]  # dx, dy, dz
        self.last_update_time = time.time()
        
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
        pass
    
    def connect(self):
        """Kết nối đến MQTT broker"""
        try:
            # Dùng biến từ Docker
            self.client.connect(self.mqtt_broker, self.mqtt_port, 60)
            self.client.loop_start()
        except Exception as e:
            print(f"[{self.sensor_id}] Error connecting to MQTT: {e}")
            raise
    
    def generate_acceleration(self) -> Tuple[float, float, float]:
        """Tạo gia tốc theo 3 trục (m/s²)"""
        # Lấy giá trị cơ bản từ config (JSON)
        bx = self.base_acceleration.get('x', 0.0)
        by = self.base_acceleration.get('y', 0.0)
        bz = self.base_acceleration.get('z', -9.81)

        ax = bx + random.uniform(-self.acceleration_noise, self.acceleration_noise)
        ay = by + random.uniform(-self.acceleration_noise, self.acceleration_noise)
        az = bz + random.uniform(-self.acceleration_noise, self.acceleration_noise)
        
        return ax, ay, az
    
    def generate_angular_velocity(self) -> Tuple[float, float, float]:
        """Tạo vận tốc góc theo 3 trục (rad/s)"""
        gx = random.uniform(-self.angular_velocity_noise, self.angular_velocity_noise)
        gy = random.uniform(-self.angular_velocity_noise, self.angular_velocity_noise)
        gz = random.uniform(-self.angular_velocity_noise, self.angular_velocity_noise)
        return gx, gy, gz
    
    def calculate_tilt_angles(self, ax: float, ay: float, az: float) -> Tuple[float, float, float]:
        """Tính góc nghiêng từ gia tốc (degrees)"""
        # Roll (quanh trục X)
        roll = math.atan2(ay, az) * 180.0 / math.pi
        
        # Pitch (quanh trục Y)
        # Sử dụng math.sqrt để tránh lỗi miền giá trị
        pitch = math.atan2(-ax, math.sqrt(ay**2 + az**2)) * 180.0 / math.pi
        
        # Yaw giả lập (IMU 6 trục thường không tính được Yaw chính xác nếu không có từ kế)
        yaw = random.uniform(-self.tilt_noise, self.tilt_noise)
        
        return roll, pitch, yaw
    
    def integrate_motion(self, ax: float, ay: float, az: float, dt: float):
        """Tích phân gia tốc để tính vận tốc và dịch chuyển"""
        # Lưu ý: Đây là tích phân đơn giản, sẽ bị trôi (drift) theo thời gian
        # Trong thực tế cần Kalman Filter để bù trừ.
        
        # Trừ gia tốc trọng trường (giả sử trục Z hướng xuống)
        # Để đơn giản hóa cho mô phỏng, ta chỉ tích phân phần nhiễu động
        # (Nếu không trừ 9.81, vận tốc trục Z sẽ tăng vô hạn)
        az_dynamic = az - self.base_acceleration.get('z', -9.81)
        ax_dynamic = ax - self.base_acceleration.get('x', 0.0)
        ay_dynamic = ay - self.base_acceleration.get('y', 0.0)

        # Tích phân gia tốc -> vận tốc
        self.velocity[0] += ax_dynamic * dt
        self.velocity[1] += ay_dynamic * dt
        self.velocity[2] += az_dynamic * dt
        
        # Giảm chấn (Damping) để vận tốc không tăng vô hạn do nhiễu cộng dồn
        damping_factor = 0.95
        self.velocity[0] *= damping_factor
        self.velocity[1] *= damping_factor
        self.velocity[2] *= damping_factor

        # Tích phân vận tốc -> dịch chuyển
        self.displacement[0] += self.velocity[0] * dt
        self.displacement[1] += self.velocity[1] * dt
        self.displacement[2] += self.velocity[2] * dt
    
    def calculate_rms(self, values: list) -> float:
        """Tính giá trị RMS (Root Mean Square)"""
        return math.sqrt(sum(v**2 for v in values) / len(values))
    
    def create_data_packet(self, acceleration, angular_velocity, tilt, velocity, displacement) -> Dict[str, Any]:
        """Tạo gói dữ liệu JSON"""
        timestamp = datetime.now().isoformat()
        acc_rms = self.calculate_rms(acceleration)
        
        return {
            "timestamp": timestamp,
            "cluster_id": self.cluster_id,   # Docker Env
            "sensor_id": self.sensor_id,     # Generated
            "sensor_type": self.sensor_type, # Docker Env
            "value": {
                "acceleration": {
                    "x": round(acceleration[0], 4),
                    "y": round(acceleration[1], 4),
                    "z": round(acceleration[2], 4),
                    "rms": round(acc_rms, 4)
                },
                "angular_velocity": {
                    "x": round(angular_velocity[0], 4),
                    "y": round(angular_velocity[1], 4),
                    "z": round(angular_velocity[2], 4)
                },
                "tilt": {
                    "roll": round(tilt[0], 2),
                    "pitch": round(tilt[1], 2),
                    "yaw": round(tilt[2], 2)
                },
                "velocity": {
                    "x": round(velocity[0], 4),
                    "y": round(velocity[1], 4),
                    "z": round(velocity[2], 4)
                },
                "displacement": {
                    "x": round(displacement[0], 6),
                    "y": round(displacement[1], 6),
                    "z": round(displacement[2], 6)
                }
            },
            "unit": {
                "acceleration": self.unit,
                "angular_velocity": "rad/s",
                "tilt": "degrees",
                "velocity": "m/s",
                "displacement": "m"
            }
        }
    
    def publish_data(self, data: Dict[str, Any]):
        payload = json.dumps(data, ensure_ascii=False)
        # Sử dụng topic động từ Env
        self.client.publish(self.topic, payload, qos=1)
        # Chỉ in log RMS để đỡ rác màn hình
        acc_data = data['value']['acceleration']
        print(f"[{self.sensor_id}] Sent: RMS={acc_data['rms']} m/s²")
    
    def run(self):
        """Chạy cảm biến liên tục"""
        self.connect()
        # Tính thời gian ngủ từ frequency trong JSON
        sleep_interval = 1.0 / self.frequency if self.frequency > 0 else 0.1
        
        try:
            while True:
                current_time = time.time()
                dt = current_time - self.last_update_time
                if dt <= 0: dt = 0.001 # Tránh chia cho 0 hoặc dt âm
                
                # 1. Sinh dữ liệu
                acceleration = self.generate_acceleration()
                angular_velocity = self.generate_angular_velocity()
                tilt = self.calculate_tilt_angles(*acceleration)
                
                # 2. Tính toán vật lý
                self.integrate_motion(*acceleration, dt)
                
                # 3. Đóng gói & Gửi
                data = self.create_data_packet(
                    acceleration,
                    angular_velocity,
                    tilt,
                    self.velocity,
                    self.displacement
                )
                self.publish_data(data)
                
                self.last_update_time = current_time
                time.sleep(sleep_interval)
                
        except KeyboardInterrupt:
            print(f"\n[{self.sensor_id}] Stopping sensor...")
            self.client.loop_stop()
            self.client.disconnect()

if __name__ == "__main__":
    sensor = IMUSensor()
    sensor.run()