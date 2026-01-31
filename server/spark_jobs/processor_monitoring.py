"""
Spark Streaming Job for Landslide Monitoring System with InfluxDB Integration
This is a separate monitoring pipeline that writes processed data to InfluxDB
for visualization in Grafana, without affecting the existing console output pipeline.
"""

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    from_json, col, when, window, avg, max, last, 
    to_timestamp, expr, regexp_extract
)
from pyspark.sql.types import (
    StructType, StructField, StringType, DoubleType
)
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from datetime import datetime
import traceback

# ============================================
# CONFIGURATION
# ============================================
INFLUX_URL = "http://influxdb:8086"
INFLUX_TOKEN = "my-super-secret-auth-token"
INFLUX_ORG = "landslide_org"
INFLUX_BUCKET = "sensor_data"

KAFKA_SERVER = "kafka:29092"
KAFKA_TOPIC = "landslide_data"

# ============================================
# 1. INITIALIZE SPARK SESSION
# ============================================
print("=" * 60)
print("Starting Landslide Monitoring Pipeline with InfluxDB")
print("=" * 60)

spark = SparkSession.builder \
    .appName("Landslide_Monitoring_InfluxDB_Pipeline") \
    .config("spark.sql.shuffle.partitions", "2") \
    .config("spark.sql.streaming.stateStore.minDeltasForSnapshot", "2") \
    .getOrCreate()

spark.sparkContext.setLogLevel("WARN")

# ============================================
# 2. DEFINE SCHEMA
# ============================================
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

# ============================================
# 3. READ KAFKA STREAM
# ============================================
print(f"Connecting to Kafka: {KAFKA_SERVER}, Topic: {KAFKA_TOPIC}")

raw_df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", KAFKA_SERVER) \
    .option("subscribe", KAFKA_TOPIC) \
    .option("startingOffsets", "latest") \
    .option("failOnDataLoss", "false") \
    .load()

# ============================================
# 4. PARSE JSON & EXTRACT FEATURES
# ============================================
parsed_df = raw_df.select(
    from_json(col("value").cast("string"), json_schema).alias("data")
).select("data.*").withColumn("event_time", to_timestamp(col("timestamp")))

# Extract cluster_id from sensor_id (e.g., "imu_cluster_01_001" -> "cluster_01")
feature_df = parsed_df.select(
    col("event_time"),
    col("sensor_id"),
    regexp_extract(col("sensor_id"), r"(cluster_\d+)", 1).alias("cluster_id"),
    col("sensor_type"),
    # Calculate velocity magnitude from IMU
    when(col("sensor_type") == "imu", 
         (col("value.velocity.x")**2 + col("value.velocity.y")**2)**0.5
    ).alias("imu_velocity"),
    col("value.acceleration.rms").alias("acc_rms"),
    col("value.intensity").alias("rain"),
    col("value.pore_pressure").alias("pressure"),
    col("value.vn2000.x").alias("gnss_x"),
    col("value.vn2000.y").alias("gnss_y")
)

# ============================================
# 5. RESAMPLING (1-second windows)
# ============================================
window_duration = "1 second"

resampled_df = feature_df \
    .withWatermark("event_time", "10 seconds") \
    .groupBy(
        window(col("event_time"), window_duration),
        col("cluster_id")
    ) \
    .agg(
        # IMU: Average velocity for noise reduction
        avg("imu_velocity").alias("avg_velocity"),
        max("acc_rms").alias("max_vibration"),
        
        # GNSS: Last value (forward fill)
        last("gnss_x", ignorenulls=True).alias("last_gnss_x"),
        last("gnss_y", ignorenulls=True).alias("last_gnss_y"),
        
        # Rain & Groundwater: Max values
        max("rain").alias("rain_intensity"),
        max("pressure").alias("pore_pressure")
    )

# ============================================
# 6. APPLY FUKUZONO MODEL & ALERTS
# ============================================
final_df = resampled_df.withColumn(
    # Calculate Inverse Velocity (1/v)
    "inv_velocity",
    when(col("avg_velocity") > 0.00001, 1.0 / col("avg_velocity")).otherwise(1000.0)
).withColumn(
    # Alert level: 3 = DANGER, 2 = WARNING, 1 = NORMAL
    "alert_level",
    when(col("inv_velocity") < 10.0, 3)  # DANGER: Landslide imminent
    .when(col("rain_intensity") > 50.0, 2)  # WARNING: Heavy rain
    .when(col("max_vibration") > 0.5, 2)  # WARNING: High vibration
    .otherwise(1)  # NORMAL
).withColumn(
    # Alert message
    "alert_message",
    when(col("alert_level") == 3, "DANGER: LANDSLIDE IMMINENT")
    .when(col("alert_level") == 2, "WARNING: HIGH RISK CONDITIONS")
    .otherwise("NORMAL")
)

# ============================================
# 7. WRITE TO INFLUXDB
# ============================================
def write_to_influxdb(batch_df, batch_id):
    """
    Write each micro-batch to InfluxDB
    """
    try:
        # Convert to Pandas for easier processing
        pdf = batch_df.toPandas()
        
        if pdf.empty:
            print(f"Batch {batch_id}: No data to write")
            return
        
        # Initialize InfluxDB client
        client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
        write_api = client.write_api(write_options=SYNCHRONOUS)
        
        points = []
        for index, row in pdf.iterrows():
            # Extract timestamp from window
            timestamp = row['window']['start']
            
            # Create InfluxDB Point with measurement name
            point = Point("landslide_metrics") \
                .tag("cluster_id", str(row['cluster_id'] or 'unknown')) \
                .field("inv_velocity", float(row['inv_velocity'] or 0)) \
                .field("avg_velocity", float(row['avg_velocity'] or 0)) \
                .field("max_vibration", float(row['max_vibration'] or 0)) \
                .field("rain_intensity", float(row['rain_intensity'] or 0)) \
                .field("pore_pressure", float(row['pore_pressure'] or 0)) \
                .field("gnss_x", float(row['last_gnss_x'] or 0)) \
                .field("gnss_y", float(row['last_gnss_y'] or 0)) \
                .field("alert_level", int(row['alert_level'])) \
                .time(timestamp)
            
            points.append(point)
        
        # Write batch to InfluxDB
        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=points)
        
        # Log success
        print(f"✓ Batch {batch_id}: Successfully wrote {len(points)} points to InfluxDB")
        
        # Print alerts if any
        alerts = pdf[pdf['alert_level'] > 1]
        if not alerts.empty:
            print(f"⚠ ALERTS DETECTED in Batch {batch_id}:")
            for _, alert in alerts.iterrows():
                print(f"  - Cluster: {alert['cluster_id']}, "
                      f"Level: {alert['alert_level']}, "
                      f"Message: {alert['alert_message']}")
        
        client.close()
        
    except Exception as e:
        print(f"✗ Error in Batch {batch_id}: {str(e)}")
        traceback.print_exc()

# ============================================
# 8. START STREAMING QUERY
# ============================================
print("\n" + "=" * 60)
print("Starting streaming query to InfluxDB...")
print(f"InfluxDB: {INFLUX_URL}")
print(f"Bucket: {INFLUX_BUCKET}")
print("=" * 60 + "\n")

query = final_df.writeStream \
    .outputMode("update") \
    .foreachBatch(write_to_influxdb) \
    .option("checkpointLocation", "/app/checkpoint/influxdb_monitoring") \
    .trigger(processingTime="1 second") \
    .start()

print("✓ Streaming query started successfully!")
print("Waiting for data from Kafka...")
print("Press Ctrl+C to stop\n")

# Keep the job running
query.awaitTermination()

