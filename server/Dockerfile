# Sử dụng Image Spark gốc làm nền
FROM apache/spark:3.5.0

# Chuyển sang quyền root để cài đặt và copy file
USER root

# Tạo thư mục làm việc
WORKDIR /app

# Copy toàn bộ code xử lý (Spark Jobs) vào trong Image
# Điều này giúp Image chứa sẵn code, không cần mount volume nữa
COPY spark_jobs /app/spark_jobs

# Nếu sau này processor.py cần thư viện ngoài (ví dụ numpy, pandas)
# thì uncomment 2 dòng dưới để cài đặt:
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt

# Thiết lập thư mục mặc định khi container chạy
WORKDIR /opt/spark/work-dir