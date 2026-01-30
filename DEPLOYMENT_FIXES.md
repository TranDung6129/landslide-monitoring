# 🔧 Deployment Fixes & Improvements

Tài liệu này mô tả chi tiết các vấn đề gặp phải trong quá trình deployment và cách khắc phục.

---

## 📋 Tổng Quan

**Ngày:** 30/01/2026  
**Phiên bản:** v1.0.32+  
**Mục tiêu:** Tự động hóa hoàn toàn quy trình CI/CD deployment cho hệ thống Landslide Monitoring

---

## ❌ Các Vấn Đề Đã Gặp

### 1. Container Conflict Issues
**Triệu chứng:**
```
Error: The container name "/mosquitto" is already in use
Error: The container name "/mqtt-bridge" is already in use
```

**Nguyên nhân:**
- Gateway và Server deploy riêng biệt nhưng có containers trùng tên
- CI/CD deployment không cleanup containers cũ trước khi tạo mới

**Khắc phục:**
- Thêm step cleanup toàn diện trước khi deploy
- Xóa tất cả containers: `mosquitto`, `mqtt-bridge`, `kafka`, `spark-master`, `spark-worker`, `zookeeper`

### 2. Permission Denied Issues
**Triệu chứng:**
```
Error: EACCES: permission denied, unlink '/mosquitto/log/mosquitto.log'
```

**Nguyên nhân:**
- Docker containers tạo files với user `root`
- GitHub Actions runner (user `dungtm`) không có quyền xóa

**Khắc phục:**
```bash
# Thêm vào /etc/sudoers.d/github-runner
dungtm ALL=(ALL) NOPASSWD: /bin/rm, /bin/chown
```

### 3. Network Isolation Issues
**Triệu chứng:**
```
>>> Bridge: Cho Kafka khoi dong... (NoBrokersAvailable)
```

**Nguyên nhân:**
- Gateway (mosquitto, mqtt-bridge) và Server (kafka, spark) trong 2 networks riêng
- `mqtt-bridge` không thể resolve hostname `kafka:29092`

**Khắc phục:**
- Tạo shared Docker network: `landslide_network`
- Tất cả containers đều join network này

### 4. Missing Spark Jobs Volume Mount
**Triệu chứng:**
```
ls: cannot access '/app/spark_jobs/': No such file or directory
```

**Nguyên nhân:**
- `processor.py` nằm ở host nhưng không được mount vào spark-master container

**Khắc phục:**
```yaml
spark-master:
  volumes:
    - ./spark_jobs:/app/spark_jobs
```

### 5. Spark Batch Data Not Visible
**Triệu chứng:**
- Spark job chạy nhưng không thấy batch output (bảng ASCII)

**Nguyên nhân:**
- Sử dụng `docker exec -d` (detached mode) → console output bị mất
- `.format("console")` output không được capture

**Khắc phục:**
```bash
# Redirect output vào file
docker exec spark-master bash -c "nohup /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  /app/spark_jobs/processor.py \
  > /app/spark_jobs/spark_output.log 2>&1 &"
```

---

## ✅ Các Thay Đổi Đã Thực Hiện

### 1. Docker Compose Files

#### `gateway/docker-compose.yml`
```yaml
services:
  mosquitto:
    networks:
      - landslide_network
  
  mqtt-bridge:
    networks:
      - landslide_network

networks:
  landslide_network:
    external: true
    name: landslide_network
```

#### `server/docker-compose.yml`
```yaml
services:
  kafka:
    networks:
      - landslide_network
  
  spark-master:
    volumes:
      - ./spark_jobs:/app/spark_jobs
    networks:
      - landslide_network
  
  spark-worker:
    networks:
      - landslide_network
  
  zookeeper:
    networks:
      - landslide_network

networks:
  landslide_network:
    external: true
    name: landslide_network
```

### 2. CI/CD Pipeline (`ci-cd-pipeline.yml`)

#### Bước 1: Cleanup với Permission Fix
```yaml
- name: Clean Workspace (Fix Permission Issues)
  run: |
    sudo rm -rf "$WORKSPACE_DIR/gateway/mosquitto/log"
    sudo chown -R $(whoami):$(whoami) "$WORKSPACE_DIR"
```

#### Bước 2: Tạo Shared Network
```yaml
docker network create landslide_network
```

#### Bước 3: Deploy Gateway → Server
```yaml
# Gateway trước
cd gateway
docker-compose up -d

# Server sau
cd ../server
docker-compose up -d
```

#### Bước 4: Submit Spark Job với Output Redirection
```yaml
docker exec spark-master bash -c "nohup /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0 \
  /app/spark_jobs/processor.py \
  > /app/spark_jobs/spark_output.log 2>&1 &"
```

#### Bước 5: Wait 5 Minutes với Progress Indicator
```yaml
for i in {1..10}; do
  ELAPSED=$((i * 30))
  echo "Progress: ${ELAPSED}s / 300s"
  sleep 30
done
```

#### Bước 6: Collect Logs với Batch Data
```yaml
docker exec spark-master cat /app/spark_jobs/spark_output.log | grep -B 3 -A 10 "Batch:"
```

---

## 🚀 Quy Trình Deployment Mới

### Tự Động (CI/CD)
```bash
# Push code với tag
git add .
git commit -m "Your changes"
git tag v1.0.32
git push origin main
git push origin v1.0.32
```

**Thời gian:** ~7-8 phút (bao gồm 5 phút đợi data flow)

**Kết quả:**
- ✅ 6 containers running: mosquitto, mqtt-bridge, kafka, zookeeper, spark-master, spark-worker
- ✅ Shared network: landslide_network
- ✅ Spark job processing batches
- ✅ Log file: `~/spark_logs/spark_deployment_[timestamp].log`

### Thủ Công (Troubleshooting)

#### 1. Cleanup Hoàn Toàn
```bash
# Xóa containers
docker rm -f mosquitto mqtt-bridge kafka spark-master spark-worker zookeeper

# Xóa network
docker network rm landslide_network

# Cleanup files
sudo rm -rf ~/landslide-server/spark_jobs/checkpoint
sudo rm -rf ~/landslide-server/gateway/mosquitto/log
```

#### 2. Deploy Từ Đầu
```bash
# Tạo network
docker network create landslide_network

# Deploy gateway
cd ~/landslide-server/gateway
docker-compose up -d

# Deploy server
cd ~/landslide-server/server
docker-compose up -d

# Submit Spark job
docker exec spark-master bash -c "nohup /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0 \
  /app/spark_jobs/processor.py \
  > /app/spark_jobs/spark_output.log 2>&1 &"

# Đợi và xem batch data
sleep 60
docker exec spark-master tail -f /app/spark_jobs/spark_output.log
```

---

## 📊 Kiểm Tra Kết Quả

### 1. Container Status
```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

**Expected:**
```
NAMES          STATUS         PORTS
mosquitto      Up X minutes   0.0.0.0:1883->1883/tcp, 0.0.0.0:9001->9001/tcp
mqtt-bridge    Up X minutes   
kafka          Up X minutes   0.0.0.0:9092->9092/tcp
zookeeper      Up X minutes   2181/tcp, 2888/tcp, 3888/tcp
spark-master   Up X minutes   0.0.0.0:7077->7077/tcp, 0.0.0.0:9090->8080/tcp
spark-worker   Up X minutes   
```

### 2. Network Connectivity
```bash
docker network inspect landslide_network | grep Name
```

**Expected:** Tất cả 6 containers trong cùng network

### 3. MQTT Bridge → Kafka
```bash
docker logs mqtt-bridge --tail 20
```

**Expected:**
```
>>> Bridge: Da ket noi Kafka thanh cong!
 -> Da chuyen ti: sensors/cluster_01/rain
 -> Da chuyen ti: sensors/cluster_01/imu
```

### 4. Kafka Messages
```bash
docker exec kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic landslide_data \
  --from-beginning \
  --max-messages 5
```

**Expected:** JSON messages từ sensors

### 5. Spark Batch Processing
```bash
docker exec spark-master cat /app/spark_jobs/spark_output.log | grep -A 10 "Batch:"
```

**Expected:**
```
-------------------------------------------
Batch: 0
-------------------------------------------
+------------------------------------------+---------+--------+---------------+---------+
|window                                    |Avg_Acc_Z|Max_Rain|Max_Water_Level|Last_GNSS|
+------------------------------------------+---------+--------+---------------+---------+
|{2026-01-30 09:00:00, 2026-01-30 09:00:10}|-9.8123  |4.2     |2.45           |105.8542 |
+------------------------------------------+---------+--------+---------------+---------+
```

### 6. Deployment Log
```bash
ls -lt ~/spark_logs/ | head -2
cat ~/spark_logs/spark_deployment_*.log | grep "SUCCESS"
```

---

## 🔍 Troubleshooting

### Issue: Không thấy batch data
**Check:**
```bash
# 1. Spark job có chạy không?
docker exec spark-master ps aux | grep processor.py

# 2. Output file có tồn tại không?
docker exec spark-master ls -lh /app/spark_jobs/spark_output.log

# 3. Có lỗi trong output không?
docker exec spark-master tail -100 /app/spark_jobs/spark_output.log | grep -i error

# 4. Kafka có data không?
docker exec kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic landslide_data \
  --from-beginning \
  --max-messages 1
```

**Fix:**
```bash
# Restart Spark job
docker exec spark-master pkill -f processor.py
docker exec spark-master rm -rf /app/spark_jobs/checkpoint
docker exec spark-master bash -c "nohup /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0 \
  /app/spark_jobs/processor.py \
  > /app/spark_jobs/spark_output.log 2>&1 &"
```

### Issue: MQTT Bridge không connect Kafka
**Check:**
```bash
docker logs mqtt-bridge | grep -i kafka
docker network inspect landslide_network | grep mqtt-bridge
```

**Fix:**
```bash
# Recreate mqtt-bridge trong đúng network
docker rm -f mqtt-bridge
cd ~/landslide-server/gateway
docker-compose up -d mqtt-bridge
```

### Issue: Permission denied khi deploy
**Check:**
```bash
sudo -l | grep dungtm
```

**Fix:**
```bash
sudo nano /etc/sudoers.d/github-runner
# Thêm: dungtm ALL=(ALL) NOPASSWD: /bin/rm, /bin/chown
sudo chmod 440 /etc/sudoers.d/github-runner
```

---

## 📈 Metrics & Monitoring

### CI/CD Pipeline Duration
- **Build & Push:** ~2-3 phút
- **Deploy:** ~5-6 phút (bao gồm 5 phút wait time)
- **Total:** ~7-9 phút

### Resource Usage
```bash
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"
```

### Batch Processing Rate
```bash
# Đếm số batches trong 5 phút
docker exec spark-master grep -c "Batch:" /app/spark_jobs/spark_output.log
```

**Expected:** ~30-50 batches/5 minutes (10s window)

---

## 📝 Checklist Trước Khi Deploy

- [ ] Edge sensors đang chạy
- [ ] Server có quyền sudo cho user `dungtm`
- [ ] GitHub Actions runner đang hoạt động
- [ ] Ports available: 1883, 9001, 9092, 7077, 9090
- [ ] Disk space đủ cho logs và checkpoints
- [ ] Code đã được test locally

---

## 🎯 Best Practices

1. **Always use tags:** `v1.0.x` format
2. **Monitor first deployment:** Check logs manually
3. **Keep cleanup steps:** Don't skip permission fixes
4. **Use shared network:** Ensure all services communicate
5. **Redirect Spark output:** Never use detached mode without logging
6. **Wait for data flow:** 5 minutes minimum for meaningful batch data

---

## 🔗 Related Files

- `.github/workflows/ci-cd-pipeline.yml` - CI/CD configuration
- `gateway/docker-compose.yml` - Gateway services
- `server/docker-compose.yml` - Server services
- `server/spark_jobs/processor.py` - Spark streaming job

---

## ✍️ Authors & Contributors

**Fixed by:** AI Assistant  
**Tested on:** Server `apache-server` (ubuntu)  
**Date:** 30/01/2026

---

## 📞 Support

Nếu gặp vấn đề, check:
1. Deployment log: `~/spark_logs/spark_deployment_*.log`
2. Container logs: `docker logs <container_name>`
3. Spark output: `docker exec spark-master cat /app/spark_jobs/spark_output.log`
4. This document: `DEPLOYMENT_FIXES.md`

