# Hệ thống Giám sát và Cảnh báo Sớm Sạt lở Đất

Hệ thống IoT phân tán thời gian thực, thu thập dữ liệu từ các cảm biến môi trường (mưa, GNSS, IMU, nước ngầm), truyền tải qua MQTT/Kafka và xử lý dòng dữ liệu lớn (Stream Processing) bằng Apache Spark.

Dự án được container hóa hoàn toàn bằng Docker và tích hợp CI/CD tự động qua Github Actions.

---

## Mục lục

- [Kiến trúc Hệ thống](#kiến-trúc-hệ-thống)
- [Yêu cầu Hệ thống](#yêu-cầu-hệ-thống)
- [Hướng dẫn Triển khai](#hướng-dẫn-triển-khai)
  - [1. Triển khai Server](#1-triển-khai-server-trung-tâm)
  - [2. Triển khai Gateway](#2-triển-khai-gateway)
  - [3. Triển khai Edge Node](#3-triển-khai-edge-node)
- [Quy trình Phát triển](#quy-trình-phát-triển-và-cicd)
- [Cấu hình Nâng cao](#cấu-hình-nâng-cao)
- [Khắc phục Sự cố](#khắc-phục-sự-cố)

---

## Kiến trúc Hệ thống

Hệ thống được thiết kế theo mô hình microservices, chia thành 3 thành phần độc lập có thể triển khai trên các thiết bị vật lý khác nhau:

### Tổng quan Luồng dữ liệu

```
[Edge Nodes] --MQTT--> [Gateway] --Kafka--> [Server] --Spark--> [Analytics]
```

### Chi tiết các Thành phần

**1. Edge Node (Sensor Layer)**
- Vai trò: Thu thập dữ liệu từ cảm biến và gửi về Gateway
- Công nghệ: Python, MQTT Client
- Thiết bị khuyến nghị: Raspberry Pi, Jetson Nano, Arduino với MQTT
- Cảm biến hỗ trợ: Rain gauge, GNSS/GPS, IMU (accelerometer/gyroscope), Water level sensors

**2. Gateway (Data Aggregation Layer)**
- Vai trò: Trung chuyển và chuyển đổi giao thức (MQTT to Kafka)
- Thành phần:
  - Eclipse Mosquitto: MQTT Broker
  - MQTT-to-Kafka Bridge: Python service chuyển đổi giao thức
- Thiết bị khuyến nghị: Server on-premise, IoT Gateway device

**3. Server (Processing & Storage Layer)**
- Vai trò: Lưu trữ message queue, xử lý stream data, phát hiện bất thường
- Thành phần:
  - Apache Kafka + Zookeeper: Message broker & coordinator
  - Apache Spark: Distributed stream processing engine
- Thiết bị khuyến nghị: Cloud server (AWS EC2, DigitalOcean), Workstation

### Kiến trúc Mạng

```
Cluster A (Vị trí 1)          Cluster B (Vị trí 2)
┌─────────────────┐           ┌─────────────────┐
│  Edge Nodes     │           │  Edge Nodes     │
│  - Rain sensor  │           │  - Rain sensor  │
│  - GNSS sensor  │           │  - GNSS sensor  │
│  - IMU sensor   │           │  - IMU sensor   │
└────────┬────────┘           └────────┬────────┘
         │ MQTT                        │ MQTT
         ▼                             ▼
┌─────────────────┐           ┌─────────────────┐
│    Gateway      │           │    Gateway      │
│  - Mosquitto    │           │  - Mosquitto    │
│  - MQTT Bridge  │           │  - MQTT Bridge  │
└────────┬────────┘           └────────┬────────┘
         │ Kafka                       │ Kafka
         └─────────────┬───────────────┘
                       ▼
              ┌─────────────────┐
              │  Central Server │
              │  - Kafka        │
              │  - Spark        │
              └─────────────────┘
```

---

## Yêu cầu Hệ thống

### Phần mềm

- Docker Engine 20.10 trở lên
- Docker Compose V2 (hoặc docker-compose V1.29+)
- Git (để clone repository)

### Phần cứng khuyến nghị

**Server:**
- CPU: 4 cores trở lên
- RAM: 4GB trở lên (8GB khuyến nghị cho Spark)
- Disk: 20GB trở lên
- Network: Địa chỉ IP tĩnh hoặc domain name

**Gateway:**
- CPU: 2 cores
- RAM: 1GB
- Disk: 5GB
- Network: Kết nối ổn định tới Server

**Edge Node:**
- CPU: 1 core (Raspberry Pi 3 trở lên)
- RAM: 512MB
- Disk: 2GB
- Network: Kết nối ổn định tới Gateway (WiFi/Ethernet/4G)

### Cổng mạng (Ports)

Đảm bảo các cổng sau chưa bị chiếm dụng:

| Service | Port | Mô tả |
|---------|------|-------|
| Kafka | 9092 | External client connection |
| Kafka Internal | 29092 | Internal broker communication |
| MQTT | 1883 | MQTT client connection |
| MQTT WebSocket | 9001 | MQTT over WebSocket |
| Spark Master UI | 9090 | Web interface (mapped từ 8080) |
| Spark Master | 7077 | Cluster communication |
| Zookeeper | 2181 | Internal service |

---

## Hướng dẫn Triển khai

### Chuẩn bị

1. Clone repository:

```bash
git clone https://github.com/TranDung6129/landslide-monitoring.git
cd landslide-monitoring
```

2. Kiểm tra Docker đã cài đặt:

```bash
docker --version
docker compose version
```

### 1. Triển khai Server (Trung tâm)

Server là thành phần cần chạy đầu tiên vì Gateway và Edge sẽ kết nối tới đây.

**Bước 1: Di chuyển vào thư mục server**

```bash
cd server
```

**Bước 2: Kiểm tra file cấu hình**

File `docker-compose.yml` chứa cấu hình cho Kafka, Zookeeper và Spark. Mặc định không cần sửa gì.

**Bước 3: Khởi động các services**

```bash
export COMPOSE_PROJECT_NAME=landslide_server
docker-compose up -d
```

**Bước 4: Kiểm tra trạng thái**

```bash
# Xem logs
docker-compose logs -f

# Kiểm tra containers đang chạy
docker-compose ps
```

Bạn sẽ thấy 4 containers:
- `zookeeper`: Coordination service
- `kafka`: Message broker
- `spark-master`: Spark master node
- `spark-worker`: Spark worker node

**Bước 5: Submit Spark Job**

```bash
# Submit job xử lý stream data
docker exec -d spark-master /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0 \
  /app/spark_jobs/processor.py
```

**Bước 6: Xác minh**

- Truy cập Spark Master UI: `http://<server-ip>:9090`
- Kiểm tra job đang chạy trong tab "Running Applications"

**Lưu ý:** Ghi nhớ địa chỉ IP của server này (dùng `ip addr` hoặc `hostname -I`) để cấu hình cho Gateway.

---

### 2. Triển khai Gateway

Gateway có thể chạy trên cùng máy với Server hoặc máy riêng biệt.

**Bước 1: Di chuyển vào thư mục gateway**

```bash
cd gateway
```

**Bước 2: Cấu hình kết nối tới Server**

Sửa file `docker-compose.yml`:

```yaml
environment:
  - MQTT_BROKER=mosquitto
  - KAFKA_BROKER=${KAFKA_ADDR:-192.168.1.100:9092}  # Thay bằng IP Server
```

Hoặc set biến môi trường:

```bash
export KAFKA_ADDR=192.168.1.100:9092  # Thay bằng IP thật của Server
```

**Bước 3: Khởi động Gateway**

```bash
export COMPOSE_PROJECT_NAME=landslide_gateway
docker-compose up -d
```

**Bước 4: Kiểm tra logs**

```bash
docker-compose logs -f mqtt-bridge
```

Bạn sẽ thấy:
```
>>> Bridge: Da ket noi MQTT va dang nghe sensors/#
>>> Bridge: Da ket noi Kafka thanh cong!
```

**Troubleshooting:** Nếu thấy lỗi "Connection refused to Kafka", kiểm tra:
- Server Kafka đã chạy chưa (`docker ps` trên máy Server)
- Firewall có block port 9092 không
- IP trong `KAFKA_BROKER` có đúng không

---

### 3. Triển khai Edge Node

Edge Node mô phỏng các cảm biến gửi dữ liệu tới Gateway.

**Bước 1: Di chuyển vào thư mục edge**

```bash
cd edge
```

**Bước 2: Cấu hình kết nối tới Gateway**

Tạo file `.env` trong thư mục `edge/`:

```bash
MQTT_BROKER=192.168.1.50      # IP của Gateway
MQTT_PORT=1883
CLUSTER_ID=cluster_A           # Định danh cụm sensor
```

**Bước 3: Cấu hình thông số cảm biến**

Sửa file `sensor_config.json` để điều chỉnh thông số mô phỏng (tần suất gửi, ngưỡng giá trị, v.v.)

**Bước 4: Khởi động các sensor simulators**

```bash
export CLUSTER_ID=cluster_A
export MQTT_BROKER=192.168.1.50  # IP Gateway
export MQTT_PORT=1883

docker-compose up -d
```

**Bước 5: Xem dữ liệu đang gửi**

```bash
# Xem tất cả sensors
docker-compose logs -f

# Xem chỉ rain sensor
docker-compose logs -f rain

# Xem chỉ GNSS sensor
docker-compose logs -f gnss
```

**Kiểm tra dữ liệu đã tới Server chưa:**

Trên máy Server, kiểm tra Kafka topic:

```bash
docker exec -it kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic landslide_data \
  --from-beginning
```

---

## Quy trình Phát triển và CI/CD

### Mô hình GitOps

Dự án áp dụng quy trình tự động hóa hoàn toàn:

```
Developer Push Code --> CI Check --> Build Images --> Push to GHCR --> Auto Deploy
```

### Workflow Chi tiết

**1. Continuous Integration (CI)**

File: `.github/workflows/ci-check.yml`

Mỗi khi push code lên branch `main`, workflow này sẽ:
- Kiểm tra cú pháp Python (flake8, black)
- Validate cấu hình YAML
- Test cơ bản

**2. Continuous Deployment (CD)**

File: `.github/workflows/ci-cd-pipeline.yml`

Kích hoạt khi tạo git tag có pattern `v*` (ví dụ: `v1.0.0`, `v2.1.3`)

**Giai đoạn 1: Build & Push (chạy trên Github Cloud)**
- Build Docker images cho Gateway và Server
- Push images lên Github Container Registry (GHCR)
- Tag images với version number và `latest`

**Giai đoạn 2: Deploy (chạy trên Self-hosted Runner)**
- Chờ giai đoạn 1 hoàn thành (`needs: build-and-push`)
- Pull images mới từ GHCR
- Deploy lên server thật
- Restart Spark job với code mới

### Hướng dẫn Release Phiên bản Mới

**Bước 1: Commit thay đổi**

```bash
git add .
git commit -m "feat: add anomaly detection algorithm"
git push origin main
```

**Bước 2: Tạo tag**

```bash
# Tag với message
git tag -a v1.0.5 -m "Release version 1.0.5 - Add anomaly detection"

# Push tag lên remote
git push origin v1.0.5
```

**Bước 3: Theo dõi deployment**

- Truy cập: `https://github.com/<username>/landslide-monitoring/actions`
- Chọn workflow "CI/CD Pipeline"
- Xem tiến trình: Build --> Deploy (có mũi tên nối)

**Bước 4: Xác minh trên Server**

```bash
# Kiểm tra image version
docker images | grep landslide

# Kiểm tra Spark job mới
docker logs spark-master | tail -20
```

### Setup Self-hosted Runner

Để workflow CD hoạt động, cần cài Github Runner trên server production:

**1. Tải và cài đặt:**

```bash
mkdir -p ~/actions-runner && cd ~/actions-runner

# Download runner (thay bằng link từ Github repo settings)
curl -o actions-runner-linux-x64-2.311.0.tar.gz -L \
  https://github.com/actions/runner/releases/download/v2.311.0/actions-runner-linux-x64-2.311.0.tar.gz

tar xzf ./actions-runner-linux-x64-2.311.0.tar.gz
```

**2. Cấu hình:**

```bash
# Lấy token từ: Settings > Actions > Runners > New self-hosted runner
./config.sh --url https://github.com/<username>/<repo> --token <YOUR_TOKEN>
```

**3. Chạy như service:**

```bash
sudo ./svc.sh install
sudo ./svc.sh start
```

---

## Cấu hình Nâng cao

### 1. Tăng hiệu năng Kafka

Sửa `server/docker-compose.yml`:

```yaml
kafka:
  environment:
    KAFKA_HEAP_OPTS: "-Xmx1G -Xms1G"  # Tăng memory
    KAFKA_NUM_NETWORK_THREADS: 8
    KAFKA_NUM_IO_THREADS: 8
```

### 2. Tăng Worker cho Spark

Sửa `server/docker-compose.yml`:

```yaml
spark-worker:
  environment:
    - SPARK_WORKER_CORES=4          # Tăng số cores
    - SPARK_WORKER_MEMORY=2g        # Tăng memory
  deploy:
    replicas: 2                      # Chạy 2 workers
```

### 3. Persistent Storage cho Kafka

Thêm named volumes:

```yaml
volumes:
  kafka_data:

services:
  kafka:
    volumes:
      - kafka_data:/var/lib/kafka/data
```

### 4. Bảo mật MQTT

Cấu hình authentication trong `gateway/mosquitto/config/mosquitto.conf`:

```conf
allow_anonymous false
password_file /mosquitto/config/passwd

listener 1883
listener 8883
cafile /mosquitto/config/ca.crt
certfile /mosquitto/config/server.crt
keyfile /mosquitto/config/server.key
```

Tạo password file:

```bash
docker exec -it mosquitto mosquitto_passwd -c /mosquitto/config/passwd username
```

### 5. Multi-cluster Deployment

Để triển khai nhiều cụm edge nodes:

**Cluster A (Vị trí 1):**
```bash
export CLUSTER_ID=site_north
export MQTT_BROKER=192.168.1.50
docker-compose -p cluster_a up -d
```

**Cluster B (Vị trí 2):**
```bash
export CLUSTER_ID=site_south
export MQTT_BROKER=192.168.2.50
docker-compose -p cluster_b up -d
```

---

## Khắc phục Sự cố

### 1. Container không khởi động

**Triệu chứng:** `docker-compose ps` hiển thị "Exited" hoặc "Restarting"

**Nguyên nhân:**
- Port bị chiếm dụng
- Lỗi cấu hình
- Thiếu quyền truy cập

**Giải pháp:**

```bash
# Xem logs chi tiết
docker-compose logs <service-name>

# Kiểm tra port
sudo netstat -tulpn | grep <port>

# Dừng container xung đột
docker stop <conflicting-container>

# Recreate container
docker-compose up -d --force-recreate <service-name>
```

### 2. MQTT Bridge không kết nối được Kafka

**Triệu chứng:** Logs hiển thị "Cho Kafka khoi dong..."

**Kiểm tra:**

```bash
# 1. Kafka đã chạy chưa?
docker ps | grep kafka

# 2. Kafka có listen đúng port không?
docker exec kafka kafka-broker-api-versions --bootstrap-server localhost:9092

# 3. Network có thông không?
docker exec mqtt-bridge ping kafka  # Nếu cùng docker-compose
ping <kafka-server-ip>              # Nếu khác máy
```

**Giải pháp:**
- Đảm bảo `KAFKA_BROKER` trong env đúng format: `<ip>:<port>`
- Kiểm tra firewall: `sudo ufw allow 9092/tcp`
- Nếu chạy cùng máy, dùng Docker network: `kafka:29092`

### 3. Spark Job không xử lý dữ liệu

**Triệu chứng:** Dữ liệu vào Kafka nhưng không thấy output từ Spark

**Kiểm tra:**

```bash
# 1. Job có đang chạy không?
docker exec spark-master /opt/spark/bin/spark-submit --status <driver-id>

# 2. Xem Spark UI
# Truy cập http://<server-ip>:9090, tab "Running Applications"

# 3. Xem logs
docker logs spark-master | grep ERROR
docker logs spark-worker | grep ERROR
```

**Giải pháp:**

```bash
# Kill job cũ và restart
docker exec spark-master pkill -f spark-submit
sleep 5

# Submit lại
docker exec -d spark-master /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0 \
  /app/spark_jobs/processor.py
```

### 4. Permission denied khi Github Runner chạy

**Triệu chứng:** CI/CD deploy thành công nhưng lần sau chạy bị lỗi permission

**Nguyên nhân:** Container tạo file với quyền root

**Giải pháp:**

```bash
# Fix quyền cho runner workspace
sudo chown -R $USER:$USER ~/actions-runner/_work

# Trong docker-compose, dùng named volumes thay vì bind mounts
volumes:
  mosquitto_data:  # Thay vì ./mosquitto/data

services:
  mosquitto:
    volumes:
      - mosquitto_data:/mosquitto/data  # Thay vì ./mosquitto/data
```

### 5. Container name conflict

**Triệu chứng:** "The container name ... is already in use"

**Nguyên nhân:** Docker Compose nhận diện sai project name

**Giải pháp:**

```bash
# Set project name cố định
export COMPOSE_PROJECT_NAME=landslide_server

# Hoặc dùng flag -p
docker-compose -p landslide_server up -d

# Clean up containers cũ
docker-compose down --remove-orphans
```

### 6. Image pull bị lỗi 403 Forbidden

**Triệu chứng:** "denied: permission_denied: write_package"

**Nguyên nhân:** Không có quyền truy cập GHCR

**Giải pháp:**

```bash
# 1. Tạo Personal Access Token (PAT) trên Github
# Settings > Developer settings > Personal access tokens > Generate new token
# Chọn scope: read:packages, write:packages

# 2. Login vào GHCR
echo $GITHUB_TOKEN | docker login ghcr.io -u <username> --password-stdin

# 3. Trong Github Actions, đảm bảo permissions đã set
permissions:
  packages: write
```

### 7. Out of Memory

**Triệu chứng:** Spark job bị kill, container restart liên tục

**Giải pháp:**

```bash
# 1. Giảm memory cho Spark Worker
# Sửa docker-compose.yml
SPARK_WORKER_MEMORY=512m

# 2. Giảm partition size trong Spark
# Sửa processor.py
df = df.coalesce(2)  # Giảm số partition

# 3. Tăng RAM cho Docker Desktop (nếu dùng macOS/Windows)
# Docker Desktop > Settings > Resources > Memory: 4GB+
```

---

## Monitoring và Logging

### 1. Xem logs real-time

```bash
# Tất cả services
docker-compose logs -f

# Service cụ thể
docker-compose logs -f kafka

# Số dòng cuối
docker-compose logs --tail=100 spark-master
```

### 2. Kiểm tra resource usage

```bash
# CPU, Memory, Network I/O
docker stats

# Disk usage
docker system df
```

### 3. Export logs ra file

```bash
docker-compose logs > system-logs-$(date +%Y%m%d).log
```

### 4. Spark Monitoring

- Master UI: `http://<server-ip>:9090`
- Application UI: `http://<server-ip>:4040` (khi job đang chạy)

---

## Docker Images

Các Docker images được build tự động và lưu trữ tại Github Container Registry:

- **Gateway:** `ghcr.io/trandung6129/landslide-gateway:latest`
- **Server:** `ghcr.io/trandung6129/landslide-server:latest`

Để pull images thủ công:

```bash
docker pull ghcr.io/trandung6129/landslide-gateway:latest
docker pull ghcr.io/trandung6129/landslide-server:v1.0.5
```

---

## Cấu trúc Dự án

```
landslide-monitoring/
├── .github/
│   └── workflows/
│       ├── ci-check.yml           # Continuous Integration
│       └── ci-cd-pipeline.yml     # Build & Deploy pipeline
├── edge/
│   ├── docker-compose.yml         # Edge node orchestration
│   ├── Dockerfile                 # Sensor simulator image
│   ├── requirements.txt           # Python dependencies
│   ├── sensor_config.json         # Sensor configuration
│   ├── rain_sim.py               # Rain sensor simulator
│   ├── water_sim.py              # Water level simulator
│   ├── imu_processing.py         # IMU data processor
│   └── gnss_processing.py        # GNSS data processor
├── gateway/
│   ├── docker-compose.yml         # Gateway services
│   ├── Dockerfile                 # Bridge service image
│   ├── requirements.txt           # Python dependencies
│   ├── mqtt_to_kafka.py          # MQTT to Kafka bridge
│   └── mosquitto/
│       └── config/
│           └── mosquitto.conf    # MQTT broker config
├── server/
│   ├── docker-compose.yml         # Server infrastructure
│   ├── Dockerfile                 # Spark custom image
│   └── spark_jobs/
│       └── processor.py          # Stream processing logic
├── .gitignore
└── README.md
```

---

## Tài liệu Tham khảo

### Công nghệ sử dụng

- [Apache Kafka Documentation](https://kafka.apache.org/documentation/)
- [Apache Spark Structured Streaming](https://spark.apache.org/docs/latest/structured-streaming-programming-guide.html)
- [Eclipse Mosquitto](https://mosquitto.org/documentation/)
- [Docker Compose Reference](https://docs.docker.com/compose/compose-file/)
- [Github Actions](https://docs.github.com/en/actions)

### Chi tiết Cảm biến và Dữ liệu

Hệ thống hỗ trợ 4 loại cảm biến chính, mỗi loại có đặc trưng dữ liệu khác nhau:

#### 1. Rain Sensor (Cảm biến Mưa)

**Mục đích:** Đo lường cường độ mưa và lượng mưa tích lũy

**Tần suất:** 1 Hz (1 lần/giây)

**Tham số đầu ra:**
- `intensity` (mm/h): Cường độ mưa tức thời
- `accumulated` (mm): Lượng mưa tích lũy từ khi khởi động

**Đặc trưng dữ liệu mô phỏng:**
- **Miền giá trị:** 0 - 10 mm/h (có thể âm khi nhiễu nhưng được chuẩn hóa về 0)
- **Phân bố:** Gaussian với trung bình 0 mm/h và độ lệch ±5 mm/h
- **Đặc điểm:** 
  - Tích lũy theo thời gian (state-based)
  - Giá trị không âm
  - Reset tích lũy sau mỗi chu kỳ (60s mặc định)

**Ví dụ output:**
```json
{
  "timestamp": "2024-01-15T10:30:45.123456",
  "cluster_id": "cluster_A",
  "sensor_id": "rain_01_cluster_A",
  "sensor_type": "rain",
  "value": {
    "intensity": 3.25,
    "accumulated": 15.47
  },
  "unit": {
    "intensity": "mm/h",
    "accumulated": "mm"
  }
}
```

#### 2. Groundwater Sensor (Cảm biến Nước ngầm)

**Mục đích:** Đo mực nước ngầm và áp lực nước lỗ rỗng trong đất

**Tần suất:** 1 Hz (1 lần/giây)

**Tham số đầu ra:**
- `water_level` (m): Mực nước ngầm so với điểm tham chiếu
- `pore_pressure` (kPa): Áp lực nước lỗ rỗng

**Đặc trưng dữ liệu mô phỏng:**
- **Miền giá trị:**
  - Water level: 2.4 - 2.6 m (base ± 0.1m)
  - Pore pressure: 23.5 - 25.5 kPa (base ± 1 kPa)
- **Phân bố:** Uniform distribution trong khoảng biến thiên
- **Quan hệ vật lý:** `P = ρgh`, với ρ=1000 kg/m³, g=9.81 m/s²
  - P(kPa) ≈ 9.81 × water_level(m)
- **Đặc điểm:**
  - Hai tham số có tương quan
  - Biến thiên chậm (low-frequency change)
  - Phản ánh tình trạng bão hòa của đất

**Ví dụ output:**
```json
{
  "timestamp": "2024-01-15T10:30:45.123456",
  "cluster_id": "cluster_A",
  "sensor_id": "groundwater_01_cluster_A",
  "sensor_type": "groundwater",
  "value": {
    "water_level": 2.531,
    "pore_pressure": 24.82
  },
  "unit": {
    "water_level": "m",
    "pore_pressure": "kPa"
  }
}
```

#### 3. IMU Sensor (Inertial Measurement Unit)

**Mục đích:** Đo gia tốc, vận tốc góc, góc nghiêng, và tính toán chuyển động

**Tần suất:** 10 Hz (10 lần/giây) - High frequency

**Tham số đầu ra:**
- `acceleration` (m/s²): Gia tốc theo 3 trục X, Y, Z + RMS
- `angular_velocity` (rad/s): Vận tốc góc theo 3 trục
- `tilt` (degrees): Góc nghiêng Roll, Pitch, Yaw
- `velocity` (m/s): Vận tốc tích phân từ gia tốc
- `displacement` (m): Dịch chuyển tích phân từ vận tốc

**Đặc trưng dữ liệu mô phỏng:**
- **Miền giá trị:**
  - Acceleration: -0.1 đến +0.1 m/s² (nhiễu quanh trọng trường -9.81 trên Z)
  - Angular velocity: -0.01 đến +0.01 rad/s
  - Tilt: -0.5 đến +0.5 degrees (dao động nhỏ)
  - Velocity: Tích phân có damping (0.95) để tránh drift
  - Displacement: mm scale (tích lũy chậm)
- **Phân bố:** Gaussian white noise
- **Đặc điểm:**
  - High-frequency data (10 Hz)
  - Tích phân kép có damping factor
  - RMS được tính để phát hiện rung động
  - Drift compensation với damping 0.95

**Ví dụ output:**
```json
{
  "timestamp": "2024-01-15T10:30:45.123456",
  "cluster_id": "cluster_A",
  "sensor_id": "imu_01_cluster_A",
  "sensor_type": "imu",
  "value": {
    "acceleration": {
      "x": 0.0234,
      "y": -0.0156,
      "z": -9.8201,
      "rms": 0.0287
    },
    "angular_velocity": {
      "x": 0.0023,
      "y": -0.0015,
      "z": 0.0008
    },
    "tilt": {
      "roll": 0.12,
      "pitch": -0.08,
      "yaw": 0.25
    },
    "velocity": {
      "x": 0.0001,
      "y": -0.0002,
      "z": 0.0000
    },
    "displacement": {
      "x": 0.000012,
      "y": -0.000008,
      "z": 0.000003
    }
  },
  "unit": {
    "acceleration": "m/s²",
    "angular_velocity": "rad/s",
    "tilt": "degrees",
    "velocity": "m/s",
    "displacement": "m"
  }
}
```

**Công thức vật lý:**
- Tilt Roll: `arctan2(ay, az) × 180/π`
- Tilt Pitch: `arctan2(-ax, sqrt(ay² + az²)) × 180/π`
- Velocity: `v(t) = v(t-1) + a×dt`
- Displacement: `d(t) = d(t-1) + v×dt`

#### 4. GNSS Sensor (Global Navigation Satellite System)

**Mục đích:** Đo vị trí GPS chính xác và chuyển đổi sang hệ tọa độ VN-2000

**Tần suất:** 1 Hz (1 lần/giây)

**Tham số đầu ra:**
- `latitude` (degrees): Vĩ độ WGS84
- `longitude` (degrees): Kinh độ WGS84
- `vn2000.x` (m): Tọa độ Bắc (Northing) theo VN-2000
- `vn2000.y` (m): Tọa độ Đông (Easting) theo VN-2000
- `vn2000.z` (m): Độ cao ellipsoid

**Đặc trưng dữ liệu mô phỏng:**
- **Vị trí cơ sở:** Hà Nội (21.0285°N, 105.8542°E)
- **Miền giá trị:**
  - Latitude: 21.0285 ± 0.00001° (~1.1m precision)
  - Longitude: 105.8542 ± 0.00001° (~1.0m precision)
  - Elevation: 10.0 - 10.5 m
- **Phân bố:** Uniform random walk quanh điểm cơ sở
- **Đặc điểm:**
  - Độ chính xác: ~1 meter (GPS consumer grade)
  - Chuyển đổi WGS84 → VN-2000 tự động
  - VN-2000 Y có False Easting +500,000m

**Ví dụ output:**
```json
{
  "timestamp": "2024-01-15T10:30:45.123456",
  "cluster_id": "cluster_A",
  "sensor_id": "gnss_01_cluster_A",
  "sensor_type": "gnss",
  "value": {
    "latitude": 21.02850234,
    "longitude": 105.85420567,
    "vn2000": {
      "x": 2325678.234,
      "y": 567890.123,
      "z": 10.234
    }
  },
  "unit": {
    "latitude": "degrees",
    "longitude": "degrees",
    "vn2000": "m"
  }
}
```

**Công thức chuyển đổi (Simplified):**
- X (Northing): `lat_rad × a` (a = 6378137m - WGS84 semi-major axis)
- Y (Easting): `(lon_rad - lon0_rad) × a × cos(lat_rad) + 500000`
- Z (Elevation): Ellipsoid height (mô phỏng 10-10.5m)

### Tóm tắt Đặc trưng Dữ liệu

| Cảm biến | Tần suất | Kiểu dữ liệu | Đặc trưng chính | Ứng dụng |
|----------|----------|--------------|-----------------|----------|
| Rain | 1 Hz | Time-series, Accumulative | Tích lũy theo thời gian | Cảnh báo mưa lớn |
| Groundwater | 1 Hz | Time-series, Correlated | Hai tham số có tương quan vật lý | Giám sát độ bão hòa đất |
| IMU | 10 Hz | High-frequency, Multi-axis | 15 tham số, tích phân kép | Phát hiện chuyển động bất thường |
| GNSS | 1 Hz | Spatial, Coordinate | Vị trí tuyệt đối 2D+1D | Đo dịch chuyển tuyệt đối |

### MQTT Topics Structure

```
sensors/{cluster_id}/{sensor_type}

Ví dụ:
sensors/cluster_A/rain
sensors/cluster_A/gnss
sensors/cluster_B/imu
sensors/cluster_B/groundwater
```

**Quy tắc đặt tên:**
- `cluster_id`: Định danh cụm cảm biến (theo vị trí địa lý)
- `sensor_type`: Loại cảm biến (rain, groundwater, imu, gnss)
- Mỗi sensor có `sensor_id` duy nhất trong message payload

### Kafka Topics

- `landslide_data`: Topic chứa tất cả dữ liệu từ sensors
- Retention: 7 days (có thể cấu hình)
- Partitions: 3 (có thể scale)
- Replication factor: 1 (single broker)

---

## Đóng góp

Nếu bạn muốn đóng góp vào dự án:

1. Fork repository
2. Tạo branch mới: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Tạo Pull Request

---

## License

Dự án này được phát triển cho mục đích nghiên cứu khoa học.

---

## Liên hệ

- Developer: Tran Dung
- Project: Landslide Early Warning System Research
- Repository: https://github.com/TranDung6129/landslide-monitoring
- Issues: https://github.com/TranDung6129/landslide-monitoring/issues

Nếu gặp vấn đề kỹ thuật, vui lòng tạo issue trên Github với thông tin:
- Hệ điều hành và phiên bản Docker
- Logs liên quan
- Các bước tái hiện lỗi
