"""App-owned local history and immutable image attachments (never website history)."""
from __future__ import annotations

import base64
import copy
from dataclasses import asdict, dataclass, field
from io import BytesIO
from pathlib import Path
import time
import uuid

from PIL import Image

from .storage import atomic_json, open_regular, read_json

MAX_IMAGE = 8 * 1024 * 1024
MAX_ATTACHMENTS_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class Attachment:
    name: str
    mime: str
    data: str
    size: int

    @classmethod
    def snapshot(cls, path: Path):
        with open_regular(path) as file:
            data = file.read(MAX_IMAGE + 1)
        if len(data) > MAX_IMAGE:
            raise ValueError("Each image must be no larger than 8 MiB.")
        with Image.open(BytesIO(data)) as image:
            mime = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp", "GIF": "image/gif"}.get(image.format)
            if not mime or getattr(image, "is_animated", False):
                raise ValueError("Use a non-animated PNG, JPEG, WEBP, or GIF image.")
            if image.width * image.height > 25_000_000:
                raise ValueError("Image exceeds the 25 megapixel safety limit.")
            image.verify()
        return cls(path.name, mime, base64.b64encode(data).decode("ascii"), len(data))

    def input(self):
        return {"type": "input_image", "image_url": f"data:{self.mime};base64,{self.data}"}


@dataclass
class Conversation:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = "New conversation"
    messages: list = field(default_factory=list)
    draft: str = ""
    attachments: list[Attachment] = field(default_factory=list)
    status: str = "Ready"
    updated: float = field(default_factory=time.time)
    dirty: bool = False

    def payload(self):
        result = []
        for message in self.messages:
            if message["role"] == "user":
                content = [{"type": "input_text", "text": message["text"]}]
                content.extend(Attachment(**a).input() for a in message.get("attachments", []))
                result.append({"role": "user", "content": content})
            elif message.get("text"):
                # Partial/stopped text remains visible context, rather than being falsely marked complete.
                result.append({"role": "assistant", "content": message["text"]})
        return result

    def serialize(self):
        value = asdict(self)
        value.pop("dirty", None)
        return value


class History:
    def __init__(self, store):
        self.store = store
        self.index_path = store.history / "index.json"
        self.index = read_json(self.index_path, {})
        if not isinstance(self.index, dict):
            raise ValueError("Invalid conversation index; original file was preserved.")
        for key, entry in self.index.items():
            uuid.UUID(key)
            if (not isinstance(entry, dict) or not isinstance(entry.get("title"), str)
                    or not isinstance(entry.get("updated"), (int, float))):
                raise ValueError("Invalid conversation index entry; original file was preserved.")
        self.memory = {}

    def save(self, conversation, force=False):
        conversation.updated = time.time()
        value = conversation.serialize()
        if self.store.config["history_persistence"] or force:
            atomic_json(self.store.history / f"{conversation.id}.json", value)
            self.index[conversation.id] = {"title": conversation.title, "updated": conversation.updated}
            atomic_json(self.index_path, self.index)
        self.memory[conversation.id] = value
        conversation.dirty = False

    def entries(self):
        values = dict(self.index)
        for key, value in self.memory.items():
            values[key] = {"title": value["title"], "updated": value["updated"]}
        return sorted(values.items(), key=lambda item: item[1]["updated"], reverse=True)

    def load(self, key):
        # Never use untrusted persisted IDs as path components.
        uuid.UUID(key)
        value = self.memory.get(key) or read_json(self.store.history / f"{key}.json", None)
        if not value or value.get("id") != key:
            raise ValueError("Conversation record is missing or inconsistent.")
        value = copy.deepcopy(value)
        value["attachments"] = [Attachment(**a) for a in value.get("attachments", [])]
        value["dirty"] = False
        if value.get("status") == "Generating…":
            value["status"] = "Interrupted by previous shutdown"
            for message in value.get("messages", []):
                if message.get("state") == "generating":
                    message["state"] = "interrupted"
        return Conversation(**value)

    def delete(self, key):
        uuid.UUID(key)
        (self.store.history / f"{key}.json").unlink(missing_ok=True)
        self.index.pop(key, None)
        self.memory.pop(key, None)
        atomic_json(self.index_path, self.index)
