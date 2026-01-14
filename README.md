# Hệ thống giám sát và cảnh báo sớm sạt lở đất

Hệ thống IoT phân tán thời gian thực, thu thập dữ liệu từ các cảm biến môi trường (mưa, GNSS, IMU, nước ngầm), truyền tải qua MQTT/Kafka và xử lý luồng dữ liệu bằng Apache Spark.

Dự án được đóng gói hoàn toàn bằng Docker và tích hợp tự động hóa triển khai qua Github Actions.

---

## Mục lục

- [Kiến trúc hệ thống](#kiến-trúc-hệ-thống)
- [Yêu cầu hệ thống](#yêu-cầu-hệ-thống)
- [Hướng dẫn triển khai](#hướng-dẫn-triển-khai)
  - [1. Triển khai máy chủ trung tâm](#1-triển-khai-máy-chủ-trung-tâm)
  - [2. Triển khai cổng trung chuyển](#2-triển-khai-cổng-trung-chuyển)
  - [3. Triển khai nút biên](#3-triển-khai-nút-biên)
- [Quy trình phát triển](#quy-trình-phát-triển)
- [Cấu hình nâng cao](#cấu-hình-nâng-cao)
- [Khắc phục sự cố](#khắc-phục-sự-cố)

---

## Kiến trúc hệ thống

Hệ thống được thiết kế theo mô hình vi dịch vụ (microservices), chia thành 3 thành phần độc lập có thể triển khai trên các thiết bị vật lý khác nhau:

### Tổng quan luồng dữ liệu

```
[Nút biên] --MQTT--> [Cổng trung chuyển] --Kafka--> [Máy chủ] --Spark--> [Phân tích]
```

### Chi tiết các thành phần

**1. Nút biên (Edge Node) - Tầng cảm biến**
- Vai trò: Thu thập dữ liệu từ cảm biến và gửi về cổng trung chuyển
- Công nghệ: Python, MQTT Client
- Thiết bị đề xuất: Raspberry Pi, Jetson Nano, Arduino có hỗ trợ MQTT
- Cảm biến: Đo mưa, GNSS/GPS, IMU (gia tốc kế/con quay hồi chuyển), Mực nước ngầm

**2. Cổng trung chuyển (Gateway) - Tầng tập hợp dữ liệu**
- Vai trò: Trung chuyển và chuyển đổi giao thức (MQTT sang Kafka)
- Thành phần:
  - Eclipse Mosquitto: Môi giới MQTT (MQTT Broker)
  - Cầu nối MQTT-Kafka: Dịch vụ Python chuyển đổi giao thức
- Thiết bị đề xuất: Máy chủ tại chỗ, thiết bị cổng IoT

**3. Máy chủ (Server) - Tầng xử lý và lưu trữ**
- Vai trò: Lưu trữ hàng đợi thông điệp, xử lý luồng dữ liệu, phát hiện bất thường
- Thành phần:
  - Apache Kafka + Zookeeper: Môi giới thông điệp và bộ điều phối
  - Apache Spark: Công cụ xử lý luồng phân tán
- Thiết bị đề xuất: Máy chủ đám mây (AWS EC2, DigitalOcean), máy trạm

### Kiến trúc mạng

```
Cụm A (Vị trí 1)              Cụm B (Vị trí 2)
┌─────────────────┐           ┌─────────────────┐
│  Nút biên       │           │  Nút biên       │
│  - Cảm biến mưa │           │  - Cảm biến mưa │
│  - GNSS         │           │  - GNSS         │
│  - IMU          │           │  - IMU          │
└────────┬────────┘           └────────┬────────┘
         │ MQTT                        │ MQTT
         ▼                             ▼
┌─────────────────┐           ┌─────────────────┐
│  Cổng trung     │           │  Cổng trung     │
│  chuyển         │           │  chuyển         │
│  - Mosquitto    │           │  - Mosquitto    │
│  - Cầu nối MQTT │           │  - Cầu nối MQTT │
└────────┬────────┘           └────────┬────────┘
         │ Kafka                       │ Kafka
         └─────────────┬───────────────┘
                       ▼
              ┌─────────────────┐
              │  Máy chủ trung  │
              │  tâm            │
              │  - Kafka        │
              │  - Spark        │
              └─────────────────┘
```

---

## Yêu cầu hệ thống

### Phần mềm

- Docker Engine 20.10 trở lên
- Docker Compose phiên bản 2 (hoặc docker-compose phiên bản 1.29+)
- Git (để tải mã nguồn)

### Phần cứng đề xuất

**Máy chủ:**
- CPU: 4 nhân trở lên
- RAM: 4GB trở lên (đề xuất 8GB cho Spark)
- Ổ cứng: 20GB trở lên
- Mạng: Địa chỉ IP tĩnh hoặc tên miền

**Cổng trung chuyển:**
- CPU: 2 nhân
- RAM: 1GB
- Ổ cứng: 5GB
- Mạng: Kết nối ổn định tới máy chủ

**Nút biên:**
- CPU: 1 nhân (Raspberry Pi 3 trở lên)
- RAM: 512MB
- Ổ cứng: 2GB
- Mạng: Kết nối ổn định tới cổng trung chuyển (WiFi/Ethernet/4G)

### Các cổng mạng cần thiết

Đảm bảo các cổng sau chưa bị chiếm dụng:

| Dịch vụ | Cổng | Mô tả |
|---------|------|-------|
| Kafka | 9092 | Kết nối từ client bên ngoài |
| Kafka nội bộ | 29092 | Giao tiếp giữa các broker |
| MQTT | 1883 | Kết nối từ client MQTT |
| MQTT WebSocket | 9001 | MQTT qua WebSocket |
| Spark Master UI | 9090 | Giao diện web (ánh xạ từ 8080) |
| Spark Master | 7077 | Giao tiếp cụm |
| Zookeeper | 2181 | Dịch vụ nội bộ |

---

## Hướng dẫn triển khai

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

### 1. Triển khai máy chủ trung tâm

Máy chủ là thành phần cần chạy đầu tiên vì cổng trung chuyển và nút biên sẽ kết nối tới đây.

**Bước 1: Di chuyển vào thư mục server**

```bash
cd server
```

**Bước 2: Kiểm tra file cấu hình**

File `docker-compose.yml` chứa cấu hình cho Kafka, Zookeeper và Spark. Mặc định không cần chỉnh sửa.

**Bước 3: Khởi động các dịch vụ**

```bash
export COMPOSE_PROJECT_NAME=landslide_server
docker-compose up -d
```

**Bước 4: Kiểm tra trạng thái**

```bash
# Xem nhật ký
docker-compose logs -f

# Kiểm tra các container đang chạy
docker-compose ps
```

Bạn sẽ thấy 4 container:
- `zookeeper`: Dịch vụ điều phối
- `kafka`: Môi giới thông điệp
- `spark-master`: Nút chủ Spark
- `spark-worker`: Nút làm việc Spark

**Bước 5: Khởi chạy công việc Spark**

```bash
# Gửi công việc xử lý luồng dữ liệu
docker exec -d spark-master /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0 \
  /app/spark_jobs/processor.py
```

**Bước 6: Xác minh**

- Truy cập giao diện Spark Master: `http://<dia-chi-ip-may-chu>:9090`
- Kiểm tra công việc đang chạy trong tab "Running Applications"

**Lưu ý:** Ghi nhớ địa chỉ IP của máy chủ này (dùng lệnh `ip addr` hoặc `hostname -I`) để cấu hình cho cổng trung chuyển.

---

### 2. Triển khai cổng trung chuyển

Cổng trung chuyển có thể chạy trên cùng máy với máy chủ hoặc máy riêng biệt.

**Bước 1: Di chuyển vào thư mục gateway**

```bash
cd gateway
```

**Bước 2: Cấu hình kết nối tới máy chủ**

Chỉnh sửa file `docker-compose.yml`:

```yaml
environment:
  - MQTT_BROKER=mosquitto
  - KAFKA_BROKER=${KAFKA_ADDR:-192.168.1.100:9092}  # Thay bằng IP máy chủ
```

Hoặc thiết lập biến môi trường:

```bash
export KAFKA_ADDR=192.168.1.100:9092  # Thay bằng IP thật của máy chủ
```

**Bước 3: Khởi động cổng trung chuyển**

```bash
export COMPOSE_PROJECT_NAME=landslide_gateway
docker-compose up -d
```

**Bước 4: Kiểm tra nhật ký**

```bash
docker-compose logs -f mqtt-bridge
```

Bạn sẽ thấy:
```
>>> Bridge: Da ket noi MQTT va dang nghe sensors/#
>>> Bridge: Da ket noi Kafka thanh cong!
```

**Xử lý sự cố:** Nếu thấy lỗi "Connection refused to Kafka", kiểm tra:
- Kafka trên máy chủ đã chạy chưa (dùng `docker ps` trên máy chủ)
- Tường lửa có chặn cổng 9092 không
- IP trong `KAFKA_BROKER` có đúng không

---

### 3. Triển khai nút biên

Nút biên mô phỏng các cảm biến gửi dữ liệu tới cổng trung chuyển.

**Bước 1: Di chuyển vào thư mục edge**

```bash
cd edge
```

**Bước 2: Cấu hình kết nối tới cổng trung chuyển**

Tạo file `.env` trong thư mục `edge/`:

```bash
MQTT_BROKER=192.168.1.50      # IP của cổng trung chuyển
MQTT_PORT=1883
CLUSTER_ID=cluster_A           # Định danh cụm cảm biến
```

**Bước 3: Cấu hình thông số cảm biến**

Chỉnh sửa file `sensor_config.json` để điều chỉnh thông số mô phỏng (tần suất gửi, ngưỡng giá trị, v.v.)

**Bước 4: Khởi động các bộ mô phỏng cảm biến**

```bash
export CLUSTER_ID=cluster_A
export MQTT_BROKER=192.168.1.50  # IP cổng trung chuyển
export MQTT_PORT=1883

docker-compose up -d
```

**Bước 5: Xem dữ liệu đang gửi**

```bash
# Xem tất cả cảm biến
docker-compose logs -f

# Xem chỉ cảm biến mưa
docker-compose logs -f rain

# Xem chỉ cảm biến GNSS
docker-compose logs -f gnss
```

**Kiểm tra dữ liệu đã tới máy chủ chưa:**

Trên máy chủ, kiểm tra chủ đề Kafka:

```bash
docker exec -it kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic landslide_data \
  --from-beginning
```

---

## Quy trình phát triển

### Mô hình triển khai tự động

Dự án áp dụng quy trình tự động hóa:

```
Developer push code --> Kiểm tra tự động --> Build image --> Push lên GHCR --> Triển khai tự động
```

### Quy trình chi tiết

**1. Tích hợp liên tục (Continuous Integration)**

File: `.github/workflows/ci-check.yml`

Mỗi khi đẩy mã lên nhánh `main`, quy trình này sẽ:
- Kiểm tra cú pháp Python (flake8, black)
- Xác thực cấu hình YAML
- Kiểm thử cơ bản

**2. Triển khai liên tục (Continuous Deployment)**

File: `.github/workflows/ci-cd-pipeline.yml`

Kích hoạt khi tạo git tag có dạng `v*` (ví dụ: `v1.0.0`, `v2.1.3`)

**Giai đoạn 1: Build và push (chạy trên Github Cloud)**
- Build Docker image cho cổng trung chuyển và máy chủ
- Push image lên Github Container Registry (GHCR)
- Tag image với số phiên bản và `latest`

**Giai đoạn 2: Deploy (chạy trên máy tự lưu trữ)**
- Chờ giai đoạn 1 hoàn thành (`needs: build-and-push`)
- Pull image mới từ GHCR
- Deploy lên máy chủ thật
- Restart Spark job với code mới

### Hướng dẫn phát hành phiên bản mới

**Bước 1: Commit thay đổi**

```bash
git add .
git commit -m "feat: thêm thuật toán phát hiện bất thường"
git push origin main
```

**Bước 2: Tạo tag**

```bash
# Tag có message
git tag -a v1.0.5 -m "Release version 1.0.5 - Thêm phát hiện bất thường"

# Push tag lên remote
git push origin v1.0.5
```

**Bước 3: Theo dõi deployment**

- Truy cập: `https://github.com/<username>/landslide-monitoring/actions`
- Chọn workflow "CI/CD Pipeline"
- Xem tiến trình: Build --> Deploy (có mũi tên nối)

**Bước 4: Xác minh trên máy chủ**

```bash
# Kiểm tra phiên bản image
docker images | grep landslide

# Kiểm tra Spark job mới
docker logs spark-master | tail -20
```

### Cài đặt máy chạy tự lưu trữ

Để quy trình triển khai tự động hoạt động, cần cài Github Runner trên máy chủ sản xuất:

**1. Tải và cài đặt:**

```bash
mkdir -p ~/actions-runner && cd ~/actions-runner

# Tải runner (thay bằng liên kết từ Github repo settings)
curl -o actions-runner-linux-x64-2.311.0.tar.gz -L \
  https://github.com/actions/runner/releases/download/v2.311.0/actions-runner-linux-x64-2.311.0.tar.gz

tar xzf ./actions-runner-linux-x64-2.311.0.tar.gz
```

**2. Cấu hình:**

```bash
# Lấy token từ: Settings > Actions > Runners > New self-hosted runner
./config.sh --url https://github.com/<ten-nguoi-dung>/<ten-repo> --token <TOKEN-CUA-BAN>
```

**3. Chạy như dịch vụ:**

```bash
sudo ./svc.sh install
sudo ./svc.sh start
```

---

## Cấu hình nâng cao

### 1. Tăng hiệu năng Kafka

Chỉnh sửa `server/docker-compose.yml`:

```yaml
kafka:
  environment:
    KAFKA_HEAP_OPTS: "-Xmx1G -Xms1G"  # Tăng bộ nhớ
    KAFKA_NUM_NETWORK_THREADS: 8
    KAFKA_NUM_IO_THREADS: 8
```

### 2. Tăng số nút làm việc cho Spark

Chỉnh sửa `server/docker-compose.yml`:

```yaml
spark-worker:
  environment:
    - SPARK_WORKER_CORES=4          # Tăng số nhân
    - SPARK_WORKER_MEMORY=2g        # Tăng bộ nhớ
  deploy:
    replicas: 2                      # Chạy 2 nút làm việc
```

### 3. Lưu trữ bền vững cho Kafka

Thêm các ổ đĩa có tên:

```yaml
volumes:
  kafka_data:

services:
  kafka:
    volumes:
      - kafka_data:/var/lib/kafka/data
```

### 4. Bảo mật MQTT

Cấu hình xác thực trong `gateway/mosquitto/config/mosquitto.conf`:

```conf
allow_anonymous false
password_file /mosquitto/config/passwd

listener 1883
listener 8883
cafile /mosquitto/config/ca.crt
certfile /mosquitto/config/server.crt
keyfile /mosquitto/config/server.key
```

Tạo file mật khẩu:

```bash
docker exec -it mosquitto mosquitto_passwd -c /mosquitto/config/passwd ten-nguoi-dung
```

### 5. Triển khai nhiều cụm

Để triển khai nhiều cụm nút biên:

**Cụm A (Vị trí 1):**
```bash
export CLUSTER_ID=site_north
export MQTT_BROKER=192.168.1.50
docker-compose -p cluster_a up -d
```

**Cụm B (Vị trí 2):**
```bash
export CLUSTER_ID=site_south
export MQTT_BROKER=192.168.2.50
docker-compose -p cluster_b up -d
```

---

## Khắc phục sự cố

### 1. Container không khởi động

**Triệu chứng:** `docker-compose ps` hiển thị "Exited" hoặc "Restarting"

**Nguyên nhân:**
- Cổng bị chiếm dụng
- Lỗi cấu hình
- Thiếu quyền truy cập

**Giải pháp:**

```bash
# Xem nhật ký chi tiết
docker-compose logs <ten-dich-vu>

# Kiểm tra cổng
sudo netstat -tulpn | grep <cong>

# Dừng container xung đột
docker stop <container-xung-dot>

# Tạo lại container
docker-compose up -d --force-recreate <ten-dich-vu>
```

### 2. Cầu nối MQTT không kết nối được Kafka

**Triệu chứng:** Nhật ký hiển thị "Cho Kafka khoi dong..."

**Kiểm tra:**

```bash
# 1. Kafka đã chạy chưa?
docker ps | grep kafka

# 2. Kafka có lắng nghe đúng cổng không?
docker exec kafka kafka-broker-api-versions --bootstrap-server localhost:9092

# 3. Mạng có thông không?
docker exec mqtt-bridge ping kafka  # Nếu cùng docker-compose
ping <ip-may-chu-kafka>              # Nếu khác máy
```

**Giải pháp:**
- Đảm bảo `KAFKA_BROKER` trong biến môi trường đúng định dạng: `<ip>:<cong>`
- Kiểm tra tường lửa: `sudo ufw allow 9092/tcp`
- Nếu chạy cùng máy, dùng mạng Docker: `kafka:29092`

### 3. Công việc Spark không xử lý dữ liệu

**Triệu chứng:** Dữ liệu vào Kafka nhưng không thấy kết quả từ Spark

**Kiểm tra:**

```bash
# 1. Công việc có đang chạy không?
docker exec spark-master /opt/spark/bin/spark-submit --status <driver-id>

# 2. Xem giao diện Spark
# Truy cập http://<ip-may-chu>:9090, tab "Running Applications"

# 3. Xem nhật ký
docker logs spark-master | grep ERROR
docker logs spark-worker | grep ERROR
```

**Giải pháp:**

```bash
# Dừng công việc cũ và khởi động lại
docker exec spark-master pkill -f spark-submit
sleep 5

# Gửi lại
docker exec -d spark-master /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0 \
  /app/spark_jobs/processor.py
```

### 4. Lỗi quyền khi Github Runner chạy

**Triệu chứng:** Triển khai tự động thành công nhưng lần sau chạy bị lỗi quyền

**Nguyên nhân:** Container tạo file với quyền root

**Giải pháp:**

```bash
# Sửa quyền cho không gian làm việc của runner
sudo chown -R $USER:$USER ~/actions-runner/_work

# Trong docker-compose, dùng ổ đĩa có tên thay vì gắn kết trực tiếp
volumes:
  mosquitto_data:  # Thay vì ./mosquitto/data

services:
  mosquitto:
    volumes:
      - mosquitto_data:/mosquitto/data  # Thay vì ./mosquitto/data
```

### 5. Xung đột tên container

**Triệu chứng:** "The container name ... is already in use"

**Nguyên nhân:** Docker Compose nhận diện sai tên dự án

**Giải pháp:**

```bash
# Đặt tên dự án cố định
export COMPOSE_PROJECT_NAME=landslide_server

# Hoặc dùng cờ -p
docker-compose -p landslide_server up -d

# Dọn dẹp container cũ
docker-compose down --remove-orphans
```

### 6. Lỗi tải ảnh 403 Forbidden

**Triệu chứng:** "denied: permission_denied: write_package"

**Nguyên nhân:** Không có quyền truy cập GHCR

**Giải pháp:**

```bash
# 1. Tạo Personal Access Token (PAT) trên Github
# Settings > Developer settings > Personal access tokens > Generate new token
# Chọn scope: read:packages, write:packages

# 2. Đăng nhập vào GHCR
echo $GITHUB_TOKEN | docker login ghcr.io -u <ten-nguoi-dung> --password-stdin

# 3. Trong Github Actions, đảm bảo permissions đã thiết lập
permissions:
  packages: write
```

### 7. Hết bộ nhớ

**Triệu chứng:** Công việc Spark bị dừng, container khởi động lại liên tục

**Giải pháp:**

```bash
# 1. Giảm bộ nhớ cho Spark Worker
# Chỉnh sửa docker-compose.yml
SPARK_WORKER_MEMORY=512m

# 2. Giảm kích thước phân vùng trong Spark
# Chỉnh sửa processor.py
df = df.coalesce(2)  # Giảm số phân vùng

# 3. Tăng RAM cho Docker Desktop (nếu dùng macOS/Windows)
# Docker Desktop > Settings > Resources > Memory: 4GB+
```

---

## Giám sát và nhật ký

### 1. Xem nhật ký thời gian thực

```bash
# Tất cả dịch vụ
docker-compose logs -f

# Dịch vụ cụ thể
docker-compose logs -f kafka

# Số dòng cuối
docker-compose logs --tail=100 spark-master
```

### 2. Kiểm tra sử dụng tài nguyên

```bash
# CPU, bộ nhớ, I/O mạng
docker stats

# Sử dụng ổ đĩa
docker system df
```

### 3. Xuất nhật ký ra file

```bash
docker-compose logs > nhat-ky-he-thong-$(date +%Y%m%d).log
```

### 4. Giám sát Spark

- Giao diện Master: `http://<ip-may-chu>:9090`
- Giao diện ứng dụng: `http://<ip-may-chu>:4040` (khi công việc đang chạy)

---

## Các ảnh Docker

Các ảnh Docker được xây dựng tự động và lưu trữ tại Github Container Registry:

- **Cổng trung chuyển:** `ghcr.io/trandung6129/landslide-gateway:latest`
- **Máy chủ:** `ghcr.io/trandung6129/landslide-server:latest`

Để tải ảnh thủ công:

```bash
docker pull ghcr.io/trandung6129/landslide-gateway:latest
docker pull ghcr.io/trandung6129/landslide-server:v1.0.5
```

---

## Cấu trúc dự án

```
landslide-monitoring/
├── .github/
│   └── workflows/
│       ├── ci-check.yml           # Tích hợp liên tục
│       └── ci-cd-pipeline.yml     # Quy trình xây dựng và triển khai
├── edge/
│   ├── docker-compose.yml         # Điều phối nút biên
│   ├── Dockerfile                 # Ảnh mô phỏng cảm biến
│   ├── requirements.txt           # Thư viện Python
│   ├── sensor_config.json         # Cấu hình cảm biến
│   ├── rain_sim.py               # Mô phỏng cảm biến mưa
│   ├── water_sim.py              # Mô phỏng mực nước
│   ├── imu_processing.py         # Xử lý dữ liệu IMU
│   └── gnss_processing.py        # Xử lý dữ liệu GNSS
├── gateway/
│   ├── docker-compose.yml         # Dịch vụ cổng trung chuyển
│   ├── Dockerfile                 # Ảnh dịch vụ cầu nối
│   ├── requirements.txt           # Thư viện Python
│   ├── mqtt_to_kafka.py          # Cầu nối MQTT sang Kafka
│   └── mosquitto/
│       └── config/
│           └── mosquitto.conf    # Cấu hình môi giới MQTT
├── server/
│   ├── docker-compose.yml         # Hạ tầng máy chủ
│   ├── Dockerfile                 # Ảnh Spark tùy chỉnh
│   └── spark_jobs/
│       └── processor.py          # Logic xử lý luồng
├── .gitignore
└── README.md
```

---

## Chi tiết cảm biến và dữ liệu

Hệ thống hỗ trợ 4 loại cảm biến chính, mỗi loại có đặc trưng dữ liệu khác nhau:

### 1. Cảm biến mưa (Rain sensor)

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

**Ví dụ đầu ra:**
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

### 2. Cảm biến nước ngầm (Groundwater sensor)

**Mục đích:** Đo mực nước ngầm và áp lực nước lỗ rỗng trong đất

**Tần suất:** 1 Hz (1 lần/giây)

**Tham số đầu ra:**
- `water_level` (m): Mực nước ngầm so với điểm tham chiếu
- `pore_pressure` (kPa): Áp lực nước lỗ rỗng

**Đặc trưng dữ liệu mô phỏng:**
- **Miền giá trị:**
  - Mực nước: 2.4 - 2.6 m (cơ sở ± 0.1m)
  - Áp lực lỗ rỗng: 23.5 - 25.5 kPa (cơ sở ± 1 kPa)
- **Phân bố:** Phân bố đều trong khoảng biến thiên
- **Quan hệ vật lý:** `P = ρgh`, với ρ=1000 kg/m³, g=9.81 m/s²
  - P(kPa) ≈ 9.81 × mực_nước(m)
- **Đặc điểm:**
  - Hai tham số có tương quan
  - Biến thiên chậm
  - Phản ánh tình trạng bão hòa của đất

**Ví dụ đầu ra:**
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

### 3. Cảm biến IMU (Inertial Measurement Unit)

**Mục đích:** Đo gia tốc, vận tốc góc, góc nghiêng, và tính toán chuyển động

**Tần suất:** 10 Hz (10 lần/giây) - Tần suất cao

**Tham số đầu ra:**
- `acceleration` (m/s²): Gia tốc theo 3 trục X, Y, Z + RMS
- `angular_velocity` (rad/s): Vận tốc góc theo 3 trục
- `tilt` (độ): Góc nghiêng Roll, Pitch, Yaw
- `velocity` (m/s): Vận tốc tích phân từ gia tốc
- `displacement` (m): Dịch chuyển tích phân từ vận tốc

**Đặc trưng dữ liệu mô phỏng:**
- **Miền giá trị:**
  - Gia tốc: -0.1 đến +0.1 m/s² (nhiễu quanh trọng trường -9.81 trên Z)
  - Vận tốc góc: -0.01 đến +0.01 rad/s
  - Góc nghiêng: -0.5 đến +0.5 độ (dao động nhỏ)
  - Vận tốc: Tích phân có giảm chấn (0.95) để tránh trôi
  - Dịch chuyển: Thang mm (tích lũy chậm)
- **Phân bố:** Nhiễu trắng Gaussian
- **Đặc điểm:**
  - Dữ liệu tần suất cao (10 Hz)
  - Tích phân kép có hệ số giảm chấn
  - RMS được tính để phát hiện rung động
  - Bù trôi với giảm chấn 0.95

**Ví dụ đầu ra:**
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
    "tilt": "độ",
    "velocity": "m/s",
    "displacement": "m"
  }
}
```

**Công thức vật lý:**
- Góc Roll: `arctan2(ay, az) × 180/π`
- Góc Pitch: `arctan2(-ax, sqrt(ay² + az²)) × 180/π`
- Vận tốc: `v(t) = v(t-1) + a×dt`
- Dịch chuyển: `d(t) = d(t-1) + v×dt`

### 4. Cảm biến GNSS (Global Navigation Satellite System)

**Mục đích:** Đo vị trí GPS chính xác và chuyển đổi sang hệ tọa độ VN-2000

**Tần suất:** 1 Hz (1 lần/giây)

**Tham số đầu ra:**
- `latitude` (độ): Vĩ độ WGS84
- `longitude` (độ): Kinh độ WGS84
- `vn2000.x` (m): Tọa độ Bắc (Northing) theo VN-2000
- `vn2000.y` (m): Tọa độ Đông (Easting) theo VN-2000
- `vn2000.z` (m): Độ cao ellipsoid

**Đặc trưng dữ liệu mô phỏng:**
- **Vị trí cơ sở:** Hà Nội (21.0285°N, 105.8542°E)
- **Miền giá trị:**
  - Vĩ độ: 21.0285 ± 0.00001° (~1.1m độ chính xác)
  - Kinh độ: 105.8542 ± 0.00001° (~1.0m độ chính xác)
  - Độ cao: 10.0 - 10.5 m
- **Phân bố:** Bước ngẫu nhiên đều quanh điểm cơ sở
- **Đặc điểm:**
  - Độ chính xác: ~1 mét (GPS cấp người dùng)
  - Chuyển đổi WGS84 → VN-2000 tự động
  - VN-2000 Y có False Easting +500,000m

**Ví dụ đầu ra:**
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
    "latitude": "độ",
    "longitude": "độ",
    "vn2000": "m"
  }
}
```

**Công thức chuyển đổi (Đơn giản hóa):**
- X (Northing): `vĩ_độ_rad × a` (a = 6378137m - bán trục lớn WGS84)
- Y (Easting): `(kinh_độ_rad - kinh_độ_gốc_rad) × a × cos(vĩ_độ_rad) + 500000`
- Z (Độ cao): Độ cao ellipsoid (mô phỏng 10-10.5m)

### Tóm tắt đặc trưng dữ liệu

| Cảm biến | Tần suất | Kiểu dữ liệu | Đặc trưng chính | Ứng dụng |
|----------|----------|--------------|-----------------|----------|
| Mưa | 1 Hz | Chuỗi thời gian, Tích lũy | Tích lũy theo thời gian | Cảnh báo mưa lớn |
| Nước ngầm | 1 Hz | Chuỗi thời gian, Tương quan | Hai tham số có quan hệ vật lý | Giám sát độ bão hòa đất |
| IMU | 10 Hz | Tần suất cao, Đa trục | 15 tham số, tích phân kép | Phát hiện chuyển động bất thường |
| GNSS | 1 Hz | Không gian, Tọa độ | Vị trí tuyệt đối 2D+1D | Đo dịch chuyển tuyệt đối |

### Cấu trúc chủ đề MQTT

```
sensors/{id_cụm}/{loại_cảm_biến}

Ví dụ:
sensors/cluster_A/rain
sensors/cluster_A/gnss
sensors/cluster_B/imu
sensors/cluster_B/groundwater
```

**Quy tắc đặt tên:**
- `id_cụm`: Định danh cụm cảm biến (theo vị trí địa lý)
- `loại_cảm_biến`: Loại cảm biến (rain, groundwater, imu, gnss)
- Mỗi cảm biến có `sensor_id` duy nhất trong payload thông điệp

---

## Các chủ đề Kafka

- `landslide_data`: Chủ đề chứa tất cả dữ liệu từ cảm biến
- Thời gian lưu: 7 ngày (có thể cấu hình)
- Số phân vùng: 3 (có thể mở rộng)
- Hệ số sao chép: 1 (broker đơn)

---

## Tài liệu tham khảo

### Công nghệ sử dụng

- [Tài liệu Apache Kafka](https://kafka.apache.org/documentation/)
- [Xử lý luồng có cấu trúc Apache Spark](https://spark.apache.org/docs/latest/structured-streaming-programming-guide.html)
- [Eclipse Mosquitto](https://mosquitto.org/documentation/)
- [Tham chiếu Docker Compose](https://docs.docker.com/compose/compose-file/)
- [Github Actions](https://docs.github.com/en/actions)

---

## Đóng góp

Nếu bạn muốn đóng góp vào dự án:

1. Fork repository
2. Tạo branch mới: `git checkout -b feature/tinh-nang-moi`
3. Commit thay đổi: `git commit -m 'Thêm tính năng mới'`
4. Push lên branch: `git push origin feature/tinh-nang-moi`
5. Tạo Pull Request

---

## Giấy phép

Dự án này được phát triển cho mục đích nghiên cứu khoa học.

---

## Liên hệ

- Nhà phát triển: Trần Dũng
- Dự án: Nghiên cứu hệ thống cảnh báo sớm sạt lở đất
- Repository: https://github.com/TranDung6129/landslide-monitoring
- Issues: https://github.com/TranDung6129/landslide-monitoring/issues

Nếu gặp vấn đề kỹ thuật, vui lòng tạo issue trên Github với thông tin:
- Hệ điều hành và phiên bản Docker
- Nhật ký liên quan
- Các bước tái hiện lỗi
