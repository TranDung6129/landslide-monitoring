from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    from_json, col, when, window, avg, max, last, 
    to_timestamp, stddev, lit
)
from pyspark.sql.types import (
    StructType, StructField, StringType, DoubleType
)

# 1. KHOI TAO SPARK
# Cấu hình để chạy Streaming mượt mà
spark = SparkSession.builder \
    .appName("Landslide_Fukuzono_System") \
    .config("spark.sql.shuffle.partitions", "2") \
    .config("spark.sql.streaming.stateStore.minDeltasForSnapshot", "2") \
    .getOrCreate()

spark.sparkContext.setLogLevel("WARN")

# 2. CAU HINH KAFKA
kafka_server = "kafka:29092"
topic = "landslide_data"

# 3. DINH NGHIA SCHEMA (Khop voi du lieu tu Simulator)
json_schema = StructType([
    StructField("timestamp", StringType(), True),
    StructField("sensor_id", StringType(), True),
    StructField("sensor_type", StringType(), True),
    StructField("value", StructType([
        # IMU Data
        StructField("velocity", StructType([
            StructField("x", DoubleType(), True),
            StructField("y", DoubleType(), True),
            StructField("z", DoubleType(), True)
        ]), True),
        StructField("acceleration", StructType([
            StructField("rms", DoubleType(), True)
        ]), True),
        # Rain Data
        StructField("intensity", DoubleType(), True),
        # Groundwater Data
        StructField("pore_pressure", DoubleType(), True),
        # GNSS Data
        StructField("vn2000", StructType([
            StructField("x", DoubleType(), True),
            StructField("y", DoubleType(), True)
        ]), True)
    ]), True)
])

# 4. DOC DU LIEU STREAM
raw_df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", kafka_server) \
    .option("subscribe", topic) \
    .option("startingOffsets", "latest") \
    .load()

# 5. PARSE JSON & TIEN XU LY
parsed_df = raw_df.select(
    from_json(col("value").cast("string"), json_schema).alias("data")
).select("data.*").withColumn("event_time", to_timestamp(col("timestamp")))

# Tao Feature co ban
feature_df = parsed_df.select(
    col("event_time"),
    col("sensor_type"),
    # Tinh van toc tong hop (Magnitude) tu IMU: v = sqrt(vx^2 + vy^2)
    when(col("sensor_type") == "imu", 
         (col("value.velocity.x")**2 + col("value.velocity.y")**2)**0.5
    ).alias("imu_velocity"),
    col("value.acceleration.rms").alias("acc_rms"),
    col("value.intensity").alias("rain"),
    col("value.pore_pressure").alias("pressure"),
    col("value.vn2000.x").alias("gnss_x")
)

# 6. FEATURE ENGINEERING: DONG BO DU LIEU (RESAMPLING)
# Gom tat ca ve cua so 1 giay de khop tan so
window_duration = "1 second"
slide_duration = "1 second"

resampled_df = feature_df \
    .withWatermark("event_time", "10 seconds") \
    .groupBy(window(col("event_time"), window_duration, slide_duration)) \
    .agg(
        # IMU (200Hz): Lay trung binh de giam nhieu (Low-pass filter)
        avg("imu_velocity").alias("avg_velocity"),
        max("acc_rms").alias("max_vibration"),
        
        # GNSS (10Hz): Lay gia tri cuoi cung (Forward Fill / Interpolation bac 0)
        # ignorenulls=True giup giu lai gia tri neu giay do bi rot mang
        last("gnss_x", ignorenulls=True).alias("last_gnss_x"),
        
        # Mua & Nuoc ngam (1Hz): Lay max
        max("rain").alias("rain_intensity"),
        max("pressure").alias("pore_pressure")
    )

# 7. AP DUNG MO HINH FUKUZONO & CANH BAO
final_df = resampled_df.withColumn(
    # Tinh Inverse Velocity (1/v)
    # Tranh chia cho 0 bang cach dat nguong 0.00001
    "inv_velocity",
    when(col("avg_velocity") > 0.00001, 1.0 / col("avg_velocity")).otherwise(1000.0)
).withColumn(
    "alert_level",
    # Logic canh bao:
    # 1. Nguy hiem: Neu 1/v < 10 (tuc la van toc > 0.1 m/s) -> Dat sap truot
    # 2. Canh bao mua: Neu mua to (>50mm/h)
    when(col("inv_velocity") < 10.0, "DANGER: LANDSLIDE IMMINENT")
    .when(col("rain_intensity") > 50.0, "WARNING: HEAVY RAIN")
    .otherwise("NORMAL")
).select(
    col("window.start").alias("time"),
    col("alert_level"),
    col("inv_velocity").cast("decimal(10,2)"),
    col("avg_velocity").cast("decimal(10,5)"),
    col("last_gnss_x").cast("decimal(10,2)"), # GNSS da duoc noi suy
    col("rain_intensity")
)

# 8. XUAT KET QUA RA MAN HINH
query = final_df.writeStream \
    .outputMode("update") \
    .format("console") \
    .option("truncate", "false") \
    .option("checkpointLocation", "/app/spark_jobs/checkpoint") \
    .start()

query.awaitTermination()
