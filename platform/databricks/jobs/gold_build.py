from __future__ import annotations

import argparse
import json

from pyspark.sql import SparkSession, Window
from pyspark.sql.functions import (
    avg,
    col,
    dayofweek,
    hour,
    lag,
    lead,
    lit,
    when,
)
from pyspark.sql.types import StringType, StructField, StructType

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


def _write_feature_dictionary(spark: SparkSession, path: str) -> None:
    feature_dict = {
        "event_ts_utc": "Standardized event timestamp in UTC",
        "sensor_node_id": "Network sensor/node identifier",
        "pressure_psi": "Pressure standardized to PSI",
        "flow_gpm": "Flow standardized to GPM",
        "demand_gpm": "Demand standardized to GPM",
        "pressure_lag_1": "Pressure lag by 1 timestep",
        "pressure_lag_2": "Pressure lag by 2 timesteps",
        "flow_lag_1": "Flow lag by 1 timestep",
        "demand_lag_1": "Demand lag by 1 timestep",
        "pressure_delta": "Pressure change vs previous timestep",
        "flow_delta": "Flow change vs previous timestep",
        "demand_delta": "Demand change vs previous timestep",
        "pressure_roc": "Pressure rate of change over 1 timestep",
        "flow_roc": "Flow rate of change over 1 timestep",
        "demand_roc": "Demand rate of change over 1 timestep",
        "pressure_roll_avg_3": "Rolling average pressure over 3 timesteps",
        "pressure_roll_avg_6": "Rolling average pressure over 6 timesteps",
        "flow_roll_avg_3": "Rolling average flow over 3 timesteps",
        "flow_roll_avg_6": "Rolling average flow over 6 timesteps",
        "demand_roll_avg_3": "Rolling average demand over 3 timesteps",
        "demand_roll_avg_6": "Rolling average demand over 6 timesteps",
        "hour_of_day": "Hour extracted from event timestamp",
        "day_of_week": "Day of week extracted from event timestamp",
        "is_weekend": "Weekend indicator",
        "node_degree": "Topology degree for sensor node from EPANET links",
        "target_leak_horizon": "Prediction target at configured horizon",
    }
    payload = json.dumps(feature_dict, indent=2)
    spark.sparkContext.parallelize([payload], 1).saveAsTextFile(path)


def main(
    silver_path: str,
    gold_path: str,
    raw_path: str = "data/raw",
    prediction_horizon_steps: int = 1,
    feature_dict_path: str = "data/gold/feature_dictionary_json",
) -> None:
    spark = SparkSession.builder.appName("water-gold-build").getOrCreate()
    silver_df = spark.read.parquet(silver_path)

    w = Window.partitionBy("sensor_node_id").orderBy("event_ts_utc")

    links_path = f"{raw_path.rstrip('/')}/net3_links.csv"
    node_degree = None
    if _path_exists(spark, links_path):
        links = spark.read.option("header", True).schema(EPANET_LINK_SCHEMA).csv(links_path)
        from_degree = (
            links.groupBy("from_node").count().withColumnRenamed("from_node", "sensor_node_id")
        )
        to_degree = links.groupBy("to_node").count().withColumnRenamed("to_node", "sensor_node_id")
        node_degree = (
            from_degree.unionByName(to_degree)
            .groupBy("sensor_node_id")
            .sum("count")
            .withColumnRenamed("sum(count)", "node_degree")
        )

    gold_df = (
        silver_df.withColumn("pressure_lag_1", lag("pressure_psi", 1).over(w))
        .withColumn("pressure_lag_2", lag("pressure_psi", 2).over(w))
        .withColumn("flow_lag_1", lag("flow_gpm", 1).over(w))
        .withColumn("demand_lag_1", lag("demand_gpm", 1).over(w))
        .withColumn("pressure_delta", col("pressure_psi") - col("pressure_lag_1"))
        .withColumn("flow_delta", col("flow_gpm") - col("flow_lag_1"))
        .withColumn("demand_delta", col("demand_gpm") - col("demand_lag_1"))
        .withColumn(
            "pressure_roc",
            when(
                col("pressure_lag_1") != 0,
                col("pressure_delta") / col("pressure_lag_1"),
            ).otherwise(0.0),
        )
        .withColumn(
            "flow_roc",
            when(col("flow_lag_1") != 0, col("flow_delta") / col("flow_lag_1")).otherwise(0.0),
        )
        .withColumn(
            "demand_roc",
            when(
                col("demand_lag_1") != 0,
                col("demand_delta") / col("demand_lag_1"),
            ).otherwise(0.0),
        )
        .withColumn("pressure_roll_avg_3", avg("pressure_psi").over(w.rowsBetween(-2, 0)))
        .withColumn("pressure_roll_avg_6", avg("pressure_psi").over(w.rowsBetween(-5, 0)))
        .withColumn("flow_roll_avg_3", avg("flow_gpm").over(w.rowsBetween(-2, 0)))
        .withColumn("flow_roll_avg_6", avg("flow_gpm").over(w.rowsBetween(-5, 0)))
        .withColumn("demand_roll_avg_3", avg("demand_gpm").over(w.rowsBetween(-2, 0)))
        .withColumn("demand_roll_avg_6", avg("demand_gpm").over(w.rowsBetween(-5, 0)))
        .withColumn("hour_of_day", hour(col("event_ts_utc")))
        .withColumn("day_of_week", dayofweek(col("event_ts_utc")))
        .withColumn("is_weekend", when(col("day_of_week").isin([1, 7]), lit(1)).otherwise(lit(0)))
        .withColumn("target_leak_horizon", lead("leak_label", prediction_horizon_steps).over(w))
    )

    if node_degree is not None:
        gold_df = gold_df.join(node_degree, on="sensor_node_id", how="left")
    else:
        gold_df = gold_df.withColumn("node_degree", lit(0))

    gold_df = (
        gold_df.withColumn(
            "node_degree",
            when(col("node_degree").isNull(), lit(0)).otherwise(col("node_degree")),
        )
        .withColumn(
            "_source_type",
            when(col("_source_type").isNull(), lit("real")).otherwise(col("_source_type")),
        )
        .withColumn(
            "target_leak_horizon",
            when(col("target_leak_horizon").isNull(), col("leak_label")).otherwise(
                col("target_leak_horizon")
            ),
        )
        .fillna(0)
    )

    gold_df.write.mode("overwrite").format("parquet").save(gold_path)
    _write_feature_dictionary(spark, feature_dict_path)
    spark.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--silver-path", default="data/silver/silver_telemetry.parquet")
    parser.add_argument("--gold-path", default="data/gold/gold_telemetry.parquet")
    parser.add_argument("--raw-path", default="data/raw")
    parser.add_argument("--prediction-horizon-steps", type=int, default=1)
    parser.add_argument("--feature-dict-path", default="data/gold/feature_dictionary_json")
    args = parser.parse_args()

    main(
        args.silver_path,
        args.gold_path,
        raw_path=args.raw_path,
        prediction_horizon_steps=args.prediction_horizon_steps,
        feature_dict_path=args.feature_dict_path,
    )
