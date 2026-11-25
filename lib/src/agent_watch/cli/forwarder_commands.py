import logging
from typing import TextIO

import click

from agent_watch.api.forwarder.assign_event_identities import EventIdentityAssigner
from agent_watch.api.forwarder.event_buffer import InMemoryEventBuffer
from agent_watch.api.forwarder.forward_events import forward_tetragon_records
from agent_watch.api.forwarder.ingestion_client import IngestionClient
from agent_watch.api.forwarder.models import ForwardingResult, IngestionRequestError
from agent_watch.api.forwarder.normalize_tetragon_events import parse_tetragon_json_lines
from agent_watch.api.github_client import JsonObject

logger: logging.Logger = logging.getLogger(__name__)


@click.group("forwarder", help="Normalize host telemetry and send it to AgentWatch ingestion.")
def forwarder() -> None:
    pass


@forwarder.command("forward-tetragon-events",
                   help="Map a Tetragon JSON export to v1 events, redact secrets, and send them to POST /v1/events.")
@click.option("--tetragon-events-file", envvar="TETRAGON_EVENTS_FILE",
              type=click.File("r", encoding="utf-8", errors="replace"), required=True,
              help="Finished Tetragon JSON export, one record per line; - reads stdin to its end, so not a live "
                   "tetra getevents pipe. Env: TETRAGON_EVENTS_FILE")
@click.option("--ingestion-url", envvar="INGESTION_URL",
              help="Base URL of the AgentWatch REST API; required unless --dry-run. Env: INGESTION_URL")
@click.option("--ingestion-api-key", envvar="INGESTION_API_KEY",
              help="Sent as X-Api-Key; required unless --dry-run. Env: INGESTION_API_KEY")
@click.option("--dry-run/--no-dry-run", "is_dry_run", envvar="IS_DRY_RUN", default=False,
              help="Normalize and redact without sending. Env: IS_DRY_RUN")
def forward_tetragon_events_command(tetragon_events_file: TextIO, ingestion_url: str | None,
                                    ingestion_api_key: str | None, is_dry_run: bool) -> None:
    ingestion_client: IngestionClient | None = None
    if not is_dry_run:
        if not ingestion_url or not ingestion_api_key:
            raise click.UsageError("--ingestion-url and --ingestion-api-key are required unless --dry-run is set")
        ingestion_client = IngestionClient(ingestion_url, ingestion_api_key)
    tetragon_records: list[JsonObject]
    malformed_line_count: int
    tetragon_records, malformed_line_count = parse_tetragon_json_lines(tetragon_events_file.read())
    if malformed_line_count:
        logger.warning(f"Skipped {malformed_line_count} line(s) that are not JSON objects")
    try:
        result: ForwardingResult = forward_tetragon_records(
            tetragon_records, EventIdentityAssigner(), InMemoryEventBuffer(), ingestion_client)
    except IngestionRequestError as request_error:
        logger.error(f"Delivery failed: {request_error}")
        raise SystemExit(1) from request_error
    logger.info(f"{result.planned_event_count} event(s) planned, {result.skipped_record_count} record(s) skipped"
                f"{' (dry run)' if is_dry_run else ''}")
    if not is_dry_run:
        logger.info(f"{result.accepted_count} accepted, {len(result.rejected_events)} rejected, "
                    f"{len(result.duplicate_events)} duplicate")
    if result.rejected_events:
        raise SystemExit(1)
