import hashlib
import json
from collections import OrderedDict

from agent_watch.api.github_client import JsonObject

EVENT_IDENTITY_FIELD_NAMES: tuple[str, ...] = ("host", "timestamp", "process", "activity_type", "target", "details")
EVENT_ID_PREFIX: str = "sha256:"
DEFAULT_REMEMBERED_EVENT_ID_COUNT: int = 10_000


class EventIdentityAssigner:
    def __init__(self, remembered_event_id_count: int = DEFAULT_REMEMBERED_EVENT_ID_COUNT) -> None:
        self._next_forwarder_seq: int = 1
        self._remembered_event_id_count: int = remembered_event_id_count
        self._recent_event_ids: OrderedDict[str, None] = OrderedDict()

    def assign_identity(self, event: JsonObject) -> JsonObject:
        forwarder_seq: int = self._next_forwarder_seq
        self._next_forwarder_seq += 1
        event_id: str = compute_event_id(event)
        if event_id in self._recent_event_ids:
            event_id = compute_event_id(event, forwarder_seq)
        self.remember_event_id(event_id)
        return {"schema_version": event["schema_version"], "event_id": event_id, "forwarder_seq": forwarder_seq,
                **event}

    def remember_event_id(self, event_id: str) -> None:
        self._recent_event_ids[event_id] = None
        if len(self._recent_event_ids) > self._remembered_event_id_count:
            self._recent_event_ids.popitem(last=False)


def canonical_event_text(event: JsonObject, distinguishing_forwarder_seq: int | None = None) -> str:
    identity_fields: JsonObject = {name: event[name] for name in EVENT_IDENTITY_FIELD_NAMES if name in event}
    if distinguishing_forwarder_seq is not None:
        identity_fields["forwarder_seq"] = distinguishing_forwarder_seq
    return json.dumps(identity_fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_event_id(event: JsonObject, distinguishing_forwarder_seq: int | None = None) -> str:
    canonical_text: str = canonical_event_text(event, distinguishing_forwarder_seq)
    return f"{EVENT_ID_PREFIX}{hashlib.sha256(canonical_text.encode('utf-8')).hexdigest()}"
