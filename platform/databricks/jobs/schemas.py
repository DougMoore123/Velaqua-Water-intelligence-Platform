from __future__ import annotations

from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

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
