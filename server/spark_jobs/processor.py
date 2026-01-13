from pyspark.sql import SparkSession  # pyright: ignore[reportMissingImports]
from pyspark.sql.functions import from_json, col, when, window, avg, max, to_timestamp  # pyright: ignore[reportMissingImports]
from pyspark.sql.types import StructType, StructField, StringType, DoubleType  # pyright: ignore[reportMissingImports]

# 1. Khoi tao Spark
spark = SparkSession.builder \
    .appName("Landslide_Windowing_Analysis") \
    .config("spark.sql.shuffle.partitions", "2") \
    .getOrCreate()

spark.sparkContext.setLogLevel("WARN")

# 2. Cau hinh Kafka (DUNG CONG 29092 CHO NOI BO)
kafka_server = "kafka:29092"
topic = "landslide_data"

# 3. Schema
json_schema = StructType([
    StructField("timestamp", StringType(), True),
    StructField("sensor_id", StringType(), True),
    StructField("sensor_type", StringType(), True),
    StructField("value", StructType([
        StructField("acceleration", StructType([
            StructField("z", DoubleType(), True)
        ]), True),
        StructField("intensity", DoubleType(), True),
        StructField("water_level", DoubleType(), True),
        StructField("longitude", DoubleType(), True)
    ]), True)
])

# 4. Doc Stream
df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", kafka_server) \
    .option("subscribe", topic) \
    .option("startingOffsets", "latest") \
    .load()

# 5. Parse JSON & Cast Timestamp
# QUAN TRONG: Phai chuyen timestamp string sang kieu Timestamp de dung Window
parsed_df = df.select(from_json(col("value").cast("string"), json_schema).alias("data")) \
              .select("data.*") \
              .withColumn("event_time", to_timestamp(col("timestamp")))

# 6. Chuan hoa du lieu (Flatting)
flat_df = parsed_df.select(
    col("event_time"),
    col("sensor_type"),
    when(col("sensor_type") == "imu", col("value.acceleration.z")).alias("acc_z"),
    when(col("sensor_type") == "rain", col("value.intensity")).alias("rain"),
    when(col("sensor_type") == "groundwater", col("value.water_level")).alias("water"),
    when(col("sensor_type") == "gnss", col("value.longitude")).alias("gnss")
)

# 7. LOGIC GOM NHOM (WINDOWING AGGREGATION)
# Gom 10 giay du lieu lai lam mot
windowed_df = flat_df \
    .withWatermark("event_time", "1 minutes") \
    .groupBy(window(col("event_time"), "10 seconds")) \
    .agg(
        avg("acc_z").alias("Avg_Acc_Z"),       # IMU thi tinh trung binh
        max("rain").alias("Max_Rain"),         # Mua thi lay gia tri cao nhat
        max("water").alias("Max_Water_Level"), # Nuoc cung vay
        max("gnss").alias("Last_GNSS")
    )

# 8. Hien thi ra man hinh
# Mode "update" giup chi hien thi nhung dong co thay doi
query = windowed_df.writeStream \
    .outputMode("update") \
    .format("console") \
    .option("truncate", "false") \
    .option("checkpointLocation", "/app/spark_jobs/checkpoint") \
    .start()

query.awaitTermination()
