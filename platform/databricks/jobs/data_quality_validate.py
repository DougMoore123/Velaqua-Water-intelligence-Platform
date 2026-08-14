from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    count,
    lag,
    mean,
    to_timestamp,
    unix_timestamp,
    when,
)
from pyspark.sql.functions import (
    max as spark_max,
)
from pyspark.sql.functions import (
    min as spark_min,
)
from pyspark.sql.functions import (
    sum as spark_sum,
)
from pyspark.sql.types import DoubleType, IntegerType, StringType, StructField, StructType
from pyspark.sql.window import Window

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

LEAK_METADATA_SCHEMA = StructType(
    [
        StructField("incident_id", StringType(), True),
        StructField("node_id", StringType(), True),
        StructField("start_time", StringType(), True),
        StructField("end_time", StringType(), True),
        StructField("severity", StringType(), True),
        StructField("confidence", DoubleType(), True),
    ]
)

EPANET_NODE_SCHEMA = StructType(
    [
        StructField("node_id", StringType(), True),
        StructField("node_type", StringType(), True),
    ]
)

EPANET_LINK_SCHEMA = StructType(
    [
        StructField("link_id", StringType(), True),
        StructField("from_node", StringType(), True),
        StructField("to_node", StringType(), True),
        StructField("link_type", StringType(), True),
    ]
)


def _path_exists(spark: SparkSession, path: str) -> bool:
    jvm = spark._jvm
    conf = spark._jsc.hadoopConfiguration()
    fs = jvm.org.apache.hadoop.fs.FileSystem.get(conf)
    return bool(fs.exists(jvm.org.apache.hadoop.fs.Path(path)))


def _list_inventory(spark: SparkSession, root_path: str) -> list[str]:
    jvm = spark._jvm
    conf = spark._jsc.hadoopConfiguration()
    fs = jvm.org.apache.hadoop.fs.FileSystem.get(conf)
    path = jvm.org.apache.hadoop.fs.Path(root_path)
    if not fs.exists(path):
        return []

    out: list[str] = []
    for item in fs.listStatus(path):
        out.append(item.getPath().toString())
    return sorted(out)


def _safe_float(v) -> float | None:
    return float(v) if v is not None else None


def validate(raw_path: str, report_path: str) -> dict:
    spark = SparkSession.builder.appName("water-data-quality-validate").getOrCreate()

    telemetry = spark.read.option("header", True).schema(TELEMETRY_SCHEMA).csv(raw_path)

    expected_columns = [f.name for f in TELEMETRY_SCHEMA.fields]
    actual_columns = telemetry.columns
    missing_columns = [c for c in expected_columns if c not in actual_columns]

    telemetry_ts = telemetry.withColumn("event_ts", to_timestamp(col("timestamp")))

    row_count = telemetry_ts.count()
    column_count = len(actual_columns)

    ts_stats = telemetry_ts.select(
        spark_min("event_ts").alias("min_ts"),
        spark_max("event_ts").alias("max_ts"),
        spark_sum(when(col("event_ts").isNull(), 1).otherwise(0)).alias("null_ts_count"),
    ).collect()[0]

    w = Window.partitionBy("node_id").orderBy("event_ts")
    interval_stats = (
        telemetry_ts.withColumn("prev_ts", lag("event_ts", 1).over(w))
        .withColumn(
            "interval_seconds",
            unix_timestamp("event_ts") - unix_timestamp("prev_ts"),
        )
        .filter(col("interval_seconds").isNotNull() & (col("interval_seconds") > 0))
        .select(
            spark_min("interval_seconds").alias("min_interval_seconds"),
            mean("interval_seconds").alias("mean_interval_seconds"),
            spark_max("interval_seconds").alias("max_interval_seconds"),
        )
        .collect()[0]
    )

    alignment_stats = telemetry_ts.select(
        count("*").alias("total_rows"),
        spark_sum(
            when(
                col("pressure").isNotNull() & col("flow").isNotNull() & col("demand").isNotNull(),
                1,
            ).otherwise(0)
        ).alias("aligned_rows"),
    ).collect()[0]
    aligned_ratio = (
        float(alignment_stats["aligned_rows"]) / float(alignment_stats["total_rows"])
        if alignment_stats["total_rows"]
        else 0.0
    )

    label_stats = telemetry_ts.groupBy("leak_label").count().orderBy("leak_label").collect()
    observed_labels = [r["leak_label"] for r in label_stats if r["leak_label"] is not None]

    missing_values = telemetry_ts.select(
        *[
            spark_sum(when(col(c).isNull(), 1).otherwise(0)).alias(c)
            for c in actual_columns
        ]
    ).collect()[0].asDict()

    duplicate_count = (
        telemetry_ts.groupBy("timestamp", "node_id").count().filter(col("count") > 1).count()
    )

    outlier_stats = telemetry_ts.select(
        spark_sum(when((col("pressure") < 0) | (col("pressure") > 200), 1).otherwise(0)).alias(
            "pressure_outliers"
        ),
        spark_sum(when((col("flow") < 0) | (col("flow") > 10000), 1).otherwise(0)).alias(
            "flow_outliers"
        ),
        spark_sum(when((col("demand") < 0) | (col("demand") > 10000), 1).otherwise(0)).alias(
            "demand_outliers"
        ),
    ).collect()[0].asDict()

    leak_metadata_path = f"{raw_path.rstrip('/')}/leak_metadata.csv"
    leak_metadata_status = {"found": False, "row_count": 0, "invalid_time_rows": 0}
    if _path_exists(spark, leak_metadata_path):
        leak_metadata_status["found"] = True
        leak_df = (
            spark.read.option("header", True)
            .schema(LEAK_METADATA_SCHEMA)
            .csv(leak_metadata_path)
        )
        leak_df_ts = leak_df.withColumn("start_ts", to_timestamp(col("start_time"))).withColumn(
            "end_ts", to_timestamp(col("end_time"))
        )
        leak_metadata_status["row_count"] = leak_df_ts.count()
        leak_metadata_status["invalid_time_rows"] = leak_df_ts.filter(
            col("start_ts").isNull() | col("end_ts").isNull() | (col("end_ts") < col("start_ts"))
        ).count()

    node_path = f"{raw_path.rstrip('/')}/net3_nodes.csv"
    link_path = f"{raw_path.rstrip('/')}/net3_links.csv"
    topology_status = {"nodes_found": False, "links_found": False, "orphan_link_rows": None}
    if _path_exists(spark, node_path) and _path_exists(spark, link_path):
        topology_status["nodes_found"] = True
        topology_status["links_found"] = True

        nodes = spark.read.option("header", True).schema(EPANET_NODE_SCHEMA).csv(node_path)
        links = spark.read.option("header", True).schema(EPANET_LINK_SCHEMA).csv(link_path)
        valid_nodes = nodes.select(col("node_id").alias("nid")).dropna()

        orphan_links = (
            links.join(valid_nodes, links.from_node == valid_nodes.nid, "left")
            .withColumnRenamed("nid", "from_ok")
            .join(valid_nodes, links.to_node == valid_nodes.nid, "left")
            .withColumnRenamed("nid", "to_ok")
            .filter(col("from_ok").isNull() | col("to_ok").isNull())
            .count()
        )
        topology_status["orphan_link_rows"] = orphan_links

    inventory = _list_inventory(spark, raw_path)
    file_inventory_ok = len(inventory) > 0

    report = {
        "report_generated_utc": datetime.now(timezone.utc).isoformat(),
        "checks": {
            "complete_file_inventory": {
                "ok": file_inventory_ok,
                "files": inventory,
            },
            "schemas": {
                "ok": len(missing_columns) == 0,
                "expected_columns": expected_columns,
                "actual_columns": actual_columns,
                "missing_columns": missing_columns,
            },
            "row_column_counts": {
                "row_count": row_count,
                "column_count": column_count,
            },
            "timestamps": {
                "min_timestamp": str(ts_stats["min_ts"]),
                "max_timestamp": str(ts_stats["max_ts"]),
                "null_timestamp_rows": int(ts_stats["null_ts_count"] or 0),
            },
            "sampling_interval_seconds": {
                "min": _safe_float(interval_stats["min_interval_seconds"]),
                "mean": _safe_float(interval_stats["mean_interval_seconds"]),
                "max": _safe_float(interval_stats["max_interval_seconds"]),
            },
            "pressure_flow_demand_alignment": {
                "aligned_ratio": aligned_ratio,
                "aligned_rows": int(alignment_stats["aligned_rows"] or 0),
                "total_rows": int(alignment_stats["total_rows"] or 0),
            },
            "labels": {
                "ok": set(observed_labels).issubset({0, 1}),
                "distribution": [row.asDict() for row in label_stats],
            },
            "leak_metadata": leak_metadata_status,
            "epanet_network_topology": topology_status,
            "missing_values": missing_values,
            "duplicates": {
                "duplicate_rows_by_timestamp_node": duplicate_count,
            },
            "invalid_or_outlier_sensor_values": outlier_stats,
        },
    }

    report_json = json.dumps(report, indent=2)
    spark.sparkContext.parallelize([report_json], 1).saveAsTextFile(report_path)
    print(report_json)

    spark.stop()
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-path", default="data/raw")
    parser.add_argument("--report-path", default="data/bronze/data_quality_report_json")
    args = parser.parse_args()

    validate(args.raw_path, args.report_path)


if __name__ == "__main__":
    main()
