from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    from_json, col, when, window, avg, max, last,
    to_timestamp
)
from pyspark.sql.types import (
    StructType, StructField, StringType, DoubleType
)
import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS

# --- CẤU HÌNH INFLUXDB ---
INFLUX_URL = "http://influxdb:8086"
INFLUX_TOKEN = "my-super-secret-auth-token"
INFLUX_ORG = "landslide_org"
INFLUX_BUCKET = "sensor_data"

# 1. Khởi tạo Spark
spark = SparkSession.builder \
    .appName("Landslide_Monitoring_Full_Stack") \
    .config("spark.sql.shuffle.partitions", "2") \
    .getOrCreate()
spark.sparkContext.setLogLevel("WARN")

# 2. Schema (Thêm cluster_id)
json_schema = StructType([
    StructField("timestamp", StringType(), True),
    StructField("cluster_id", StringType(), True),
    StructField("sensor_type", StringType(), True),
    StructField("value", StructType([
        StructField("velocity", StructType([
            StructField("x", DoubleType(), True),
            StructField("y", DoubleType(), True)
        ]), True),
        StructField("acceleration", StructType([
            StructField("rms", DoubleType(), True)
        ]), True),
        StructField("intensity", DoubleType(), True),
        StructField("pore_pressure", DoubleType(), True),
        StructField("vn2000", StructType([
            StructField("x", DoubleType(), True)
        ]), True)
    ]), True)
])

# 3. Đọc Kafka
df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "kafka:29092") \
    .option("subscribe", "landslide_data") \
    .option("startingOffsets", "latest") \
    .load()

# 4. Parse & Trích xuất Feature
parsed_df = df.select(from_json(col("value").cast("string"), json_schema).alias("data")) \
              .select("data.*") \
              .withColumn("event_time", to_timestamp(col("timestamp")))

feature_df = parsed_df.select(
    col("event_time"),
    col("cluster_id"),
    col("sensor_type"),
    when(col("sensor_type") == "imu",
         (col("value.velocity.x")**2 + col("value.velocity.y")**2)**0.5
    ).alias("imu_velocity"),
    col("value.acceleration.rms").alias("acc_rms"),
    col("value.intensity").alias("rain"),
    col("value.pore_pressure").alias("pressure"),
    col("value.vn2000.x").alias("gnss_x")
)

# 5. Resampling (Cửa sổ 1 giây) + Gom nhóm theo Cluster
resampled_df = feature_df \
    .withWatermark("event_time", "10 seconds") \
    .groupBy(window(col("event_time"), "1 second"), col("cluster_id")) \
    .agg(
        avg("imu_velocity").alias("avg_velocity"),
        max("acc_rms").alias("max_vibration"),
        last("gnss_x", ignorenulls=True).alias("last_gnss_x"),
        max("rain").alias("rain_intensity"),
        max("pressure").alias("pore_pressure")
    )

# 6. Tính toán Fukuzono
final_df = resampled_df.withColumn(
    "inv_velocity",
    when(col("avg_velocity") > 0.00001, 1.0 / col("avg_velocity")).otherwise(1000.0)
).withColumn(
    "alert_level",
    when(col("inv_velocity") < 10.0, 3)
    .when(col("rain_intensity") > 50.0, 2)
    .otherwise(1)
)

# --- HÀM GHI VÀO INFLUXDB ---
def write_to_influxdb(batch_df, batch_id):
    # Chuyển Spark DataFrame thành Pandas để dễ xử lý (vì batch nhỏ ~1s)
    # Lưu ý: Nếu dữ liệu cực lớn, nên dùng mapPartitions thay vì toPandas
    pdf = batch_df.toPandas()

    if pdf.empty:
        return

    client = influxdb_client.InfluxDBClient(
        url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG
    )
    write_api = client.write_api(write_options=SYNCHRONOUS)

    points = []
    for _, row in pdf.iterrows():
        p = influxdb_client.Point("landslide_metrics") \
            .tag("cluster_id", row["cluster_id"]) \
            .field("inv_velocity", float(row["inv_velocity"])) \
            .field("avg_velocity", float(row["avg_velocity"])) \
            .field("rain_intensity", float(row["rain_intensity"] or 0)) \
            .field("pore_pressure", float(row["pore_pressure"] or 0)) \
            .field("gnss_x", float(row["last_gnss_x"] or 0)) \
            .field("alert_level", int(row["alert_level"])) \
            .time(row["window"]["start"])
        points.append(p)

    try:
        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=points)
        print(f"Batch {batch_id}: Wrote {len(points)} records into InfluxDB")
    except Exception as e:
        print(f"Error writing to InfluxDB: {e}")
    finally:
        client.close()

# 7. Output: foreachBatch (Ghi vào DB thay vì Console)
query = final_df.writeStream \
    .outputMode("update") \
    .foreachBatch(write_to_influxdb) \
    .start()

query.awaitTermination()
