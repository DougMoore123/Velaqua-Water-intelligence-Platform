from __future__ import annotations

import argparse
import os

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    concat_ws,
    current_timestamp,
    input_file_name,
    lit,
    lower,
    sha2,
    when,
)
from pyspark.sql.types import DoubleType, IntegerType, StringType, StructField, StructType

TELEMETRY_SCHEMA = StructType(
    [
        StructField("timestamp", StringType(), True),
        StructField("node_id", StringType(), True),
        StructField("pressure", DoubleType(), True),
        StructField("flow", DoubleType(), True),
        StructField("demand", DoubleType(), True),
        StructField("leak_label", IntegerType(), True),
        StructField("pressure_unit", StringType(), True),
        StructField("flow_unit", StringType(), True),
        StructField("demand_unit", StringType(), True),
    ]
)


def main(
    raw_path: str,
    bronze_path: str,
    output_format: str = "parquet",
    synthetic_raw_path: str | None = None,
) -> None:
    spark = SparkSession.builder.appName("water-bronze-ingest").getOrCreate()

    input_paths = [raw_path]
    if synthetic_raw_path and os.path.exists(synthetic_raw_path):
        input_paths.append(synthetic_raw_path)

    raw_df = (
        spark.read.option("header", True)
        .schema(TELEMETRY_SCHEMA)
        .csv(input_paths)
        .withColumn("node_id", col("node_id").cast("string"))
    )

    bronze_df = (
        raw_df.withColumn("_ingest_ts", current_timestamp())
        .withColumn("_source_file", input_file_name())
        .withColumn(
            "_source_type",
            when(lower(col("_source_file")).contains("/raw_synthetic/"), lit("synthetic"))
            .when(lower(col("_source_file")).contains("synth_"), lit("synthetic"))
            .otherwise(lit("real")),
        )
        .withColumn("_ingest_job", lit("bronze_ingest"))
        .withColumn("_schema_version", lit("v1"))
        .withColumn(
            "_row_hash",
            sha2(
                concat_ws(
                    "||",
                    col("timestamp").cast("string"),
                    col("node_id").cast("string"),
                    col("pressure").cast("string"),
                    col("flow").cast("string"),
                    col("demand").cast("string"),
                    col("leak_label").cast("string"),
                ),
                256,
            ),
        )
    )

    bronze_df.write.mode("overwrite").format(output_format).save(bronze_path)
    spark.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-path", default="data/raw")
    parser.add_argument("--synthetic-raw-path", default="")
    parser.add_argument("--bronze-path", default="data/bronze/bronze_telemetry.parquet")
    parser.add_argument("--output-format", default="parquet", choices=["parquet", "delta"])
    args = parser.parse_args()
    main(
        args.raw_path,
        args.bronze_path,
        args.output_format,
        synthetic_raw_path=args.synthetic_raw_path or None,
    )
