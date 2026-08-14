from __future__ import annotations

import argparse

from pyspark.sql import SparkSession, Window
from pyspark.sql.functions import col, lit, lower, row_number, to_timestamp, to_utc_timestamp, when
from pyspark.sql.functions import max as spark_max
from pyspark.sql.types import StringType, StructField, StructType

LEAK_METADATA_SCHEMA = StructType(
    [
        StructField("incident_id", StringType(), True),
        StructField("node_id", StringType(), True),
        StructField("start_time", StringType(), True),
        StructField("end_time", StringType(), True),
    ]
)


EPANET_NODE_SCHEMA = StructType(
    [
        StructField("node_id", StringType(), True),
    ]
)


def _path_exists(spark: SparkSession, path: str) -> bool:
    jvm = spark._jvm
    conf = spark._jsc.hadoopConfiguration()
    fs = jvm.org.apache.hadoop.fs.FileSystem.get(conf)
    return bool(fs.exists(jvm.org.apache.hadoop.fs.Path(path)))


def _normalize_pressure_to_psi(df):
    return df.withColumn(
        "pressure_psi",
        when(lower(col("pressure_unit")) == "kpa", col("pressure") * lit(0.1450377377)).otherwise(
            col("pressure")
        ),
    )


def _normalize_flow_to_gpm(df):
    return df.withColumn(
        "flow_gpm",
        when(lower(col("flow_unit")) == "lps", col("flow") * lit(15.8503231415)).otherwise(
            col("flow")
        ),
    ).withColumn(
        "demand_gpm",
        when(lower(col("demand_unit")) == "lps", col("demand") * lit(15.8503231415)).otherwise(
            col("demand")
        ),
    )


def _align_labels_from_metadata(curated, leak_metadata_df):
    leak_ts = leak_metadata_df.withColumn("start_ts", to_timestamp(col("start_time"))).withColumn(
        "end_ts", to_timestamp(col("end_time"))
    )

    match = (
        curated.alias("t")
        .join(
            leak_ts.alias("l"),
            (col("t.sensor_node_id") == col("l.node_id"))
            & (col("t.event_ts_utc") >= col("l.start_ts"))
            & (col("t.event_ts_utc") <= col("l.end_ts")),
            "left",
        )
        .select(
            col("t._row_hash").alias("_row_hash"),
            when(col("l.incident_id").isNotNull(), lit(1)).otherwise(lit(0)).alias("meta_leak"),
        )
        .groupBy("_row_hash")
        .agg(spark_max("meta_leak").alias("meta_leak"))
    )

    return (
        curated.join(match, on="_row_hash", how="left")
        .withColumn(
            "meta_leak",
            when(col("meta_leak").isNull(), lit(0)).otherwise(col("meta_leak")),
        )
        .withColumn(
            "leak_label_aligned",
            when(col("meta_leak") == 1, lit(1)).otherwise(col("leak_label")),
        )
        .drop("meta_leak")
    )


def main(
    bronze_path: str,
    silver_path: str,
    output_format: str = "parquet",
    raw_path: str = "data/raw",
    quarantine_path: str = "data/silver/quarantine_records.parquet",
) -> None:
    spark = SparkSession.builder.appName("water-silver-transform").getOrCreate()
    bronze_df = spark.read.parquet(bronze_path)

    curated = bronze_df.select(
        to_utc_timestamp(to_timestamp(col("timestamp")), "UTC").alias("event_ts_utc"),
        col("node_id").alias("sensor_node_id"),
        col("pressure").cast("double").alias("pressure"),
        col("flow").cast("double").alias("flow"),
        col("demand").cast("double").alias("demand"),
        col("pressure_unit"),
        col("flow_unit"),
        col("demand_unit"),
        col("leak_label").cast("int").alias("leak_label"),
        col("_ingest_ts"),
        col("_source_file"),
        col("_source_type"),
        col("_row_hash"),
    ).filter(col("event_ts_utc").isNotNull())

    curated = _normalize_pressure_to_psi(curated)
    curated = _normalize_flow_to_gpm(curated)

    leak_metadata_path = f"{raw_path.rstrip('/')}/leak_metadata.csv"
    if _path_exists(spark, leak_metadata_path):
        leak_metadata_df = (
            spark.read.option("header", True)
            .schema(LEAK_METADATA_SCHEMA)
            .csv(leak_metadata_path)
        )
        curated = _align_labels_from_metadata(curated, leak_metadata_df)
    else:
        curated = curated.withColumn("leak_label_aligned", col("leak_label"))

    node_path = f"{raw_path.rstrip('/')}/net3_nodes.csv"
    if _path_exists(spark, node_path):
        valid_nodes = (
            spark.read.option("header", True)
            .schema(EPANET_NODE_SCHEMA)
            .csv(node_path)
            .select(col("node_id").alias("valid_node_id"))
            .dropna()
            .dropDuplicates()
        )
        curated = curated.join(
            valid_nodes,
            curated.sensor_node_id == valid_nodes.valid_node_id,
            "left",
        )
        curated = curated.withColumn(
            "invalid_sensor_id",
            col("valid_node_id").isNull(),
        ).drop("valid_node_id")
    else:
        curated = curated.withColumn("invalid_sensor_id", lit(False))

    aligned_measurements = (
        col("pressure_psi").isNotNull()
        & col("flow_gpm").isNotNull()
        & col("demand_gpm").isNotNull()
    )

    invalid_records = curated.withColumn(
        "quarantine_reason",
        when(col("event_ts_utc").isNull(), lit("invalid_timestamp"))
        .when(col("sensor_node_id").isNull(), lit("missing_sensor_node_id"))
        .when(col("invalid_sensor_id"), lit("sensor_not_in_network_model"))
        .when(col("pressure_psi") < 0, lit("negative_pressure"))
        .when(col("flow_gpm") < 0, lit("negative_flow"))
        .when(col("demand_gpm") < 0, lit("negative_demand"))
        .when(~aligned_measurements, lit("telemetry_alignment_failure"))
        .otherwise(lit(None)),
    ).filter(col("quarantine_reason").isNotNull())

    invalid_records.write.mode("overwrite").format(output_format).save(quarantine_path)

    silver_df = (
        curated.withColumn(
            "pressure_psi", when(col("pressure_psi") < 0, None).otherwise(col("pressure_psi"))
        )
        .withColumn("flow_gpm", when(col("flow_gpm") < 0, None).otherwise(col("flow_gpm")))
        .withColumn("demand_gpm", when(col("demand_gpm") < 0, None).otherwise(col("demand_gpm")))
        .dropna(subset=["sensor_node_id", "pressure_psi", "flow_gpm", "demand_gpm"])
        .filter(aligned_measurements)
        .filter(~col("invalid_sensor_id"))
        .withColumn(
            "_source_priority",
            when(col("_source_type") == "real", lit(0)).otherwise(lit(1)),
        )
        .withColumn(
            "_dup_rank",
            row_number().over(
                Window.partitionBy("event_ts_utc", "sensor_node_id").orderBy(
                    col("_source_priority").asc(),
                    col("_ingest_ts").asc(),
                )
            ),
        )
        .filter(col("_dup_rank") == 1)
        .drop("_source_priority", "_dup_rank")
        .withColumn("pressure_unit_standard", lit("psi"))
        .withColumn("flow_unit_standard", lit("gpm"))
        .withColumn("demand_unit_standard", lit("gpm"))
        .withColumn("leak_label", col("leak_label_aligned").cast("int"))
        .drop("leak_label_aligned", "invalid_sensor_id")
    )

    silver_df.write.mode("overwrite").format(output_format).save(silver_path)
    spark.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bronze-path", default="data/bronze/bronze_telemetry.parquet")
    parser.add_argument("--silver-path", default="data/silver/silver_telemetry.parquet")
    parser.add_argument("--output-format", default="parquet", choices=["parquet", "delta"])
    parser.add_argument("--raw-path", default="data/raw")
    parser.add_argument("--quarantine-path", default="data/silver/quarantine_records.parquet")
    args = parser.parse_args()
    main(
        args.bronze_path,
        args.silver_path,
        args.output_format,
        args.raw_path,
        args.quarantine_path,
    )
