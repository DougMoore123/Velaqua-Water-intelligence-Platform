from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from azure.eventhub import EventHubConsumerClient
from azure.storage.filedatalake import DataLakeServiceClient

CONNECTION_STRING = os.getenv("EVENTHUB_CONNECTION_STRING", "")
CONSUMER_GROUP = os.getenv("EVENTHUB_CONSUMER_GROUP", "$Default")
EVENTHUB_NAME = os.getenv("EVENTHUB_NAME", "telemetry-ingest")
STORAGE_CONN_STR = os.getenv("ADLS_CONNECTION_STRING", "")
FILE_SYSTEM = os.getenv("ADLS_RAW_FILE_SYSTEM", "raw")


def write_raw_event(payload: dict) -> None:
    if not STORAGE_CONN_STR:
        return

    service = DataLakeServiceClient.from_connection_string(STORAGE_CONN_STR)
    fs = service.get_file_system_client(FILE_SYSTEM)
    now = datetime.now(timezone.utc)
    path = f"streaming/year={now:%Y}/month={now:%m}/day={now:%d}/{now:%H%M%S%f}.json"
    file_client = fs.get_file_client(path)
    content = json.dumps(payload)
    file_client.create_file()
    file_client.append_data(content, 0, len(content))
    file_client.flush_data(len(content))


def on_event(partition_context, event) -> None:
    body = json.loads(event.body_as_str(encoding="UTF-8"))
    write_raw_event(body)
    partition_context.update_checkpoint(event)


def main() -> None:
    if not CONNECTION_STRING:
        raise RuntimeError("EVENTHUB_CONNECTION_STRING must be set")

    client = EventHubConsumerClient.from_connection_string(
        conn_str=CONNECTION_STRING,
        consumer_group=CONSUMER_GROUP,
        eventhub_name=EVENTHUB_NAME,
    )
    with client:
        client.receive(on_event=on_event, starting_position="-1")


if __name__ == "__main__":
    main()
