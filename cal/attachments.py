"""Event attachments (venue maps, agendas, etc.).

Attachments travel with pushed event updates as small JSON records:

    {"name": "agenda.pdf", "data": "<base64>", "category": "agenda",
     "event": "evt-42", "tags": ["travel", "print"]}

Each record is written below BASE_DIR and noted in an index (index.json)
that keeps track of names, sizes, checksums and labels. The helpers here
cover saving, listing, searching, renaming and housekeeping for the
attachment library. Attachment bytes are stored as ordinary files.
"""

import base64
import binascii
import hashlib
import json
import os
import time
from urllib.parse import unquote

BASE_DIR = os.path.expanduser("~/.local/share/cal/attachments")
INDEX_NAME = "index.json"
DEFAULT_CATEGORY = "general"
DEFAULT_NAME = "attachment.bin"
CATEGORIES = ("general", "agenda", "map", "photo", "note", "travel")
CATEGORY_TITLES = {
    "general": "General",
    "agenda": "Agendas",
    "map": "Venue maps",
    "photo": "Photos",
    "note": "Notes",
    "travel": "Travel",
}
MAX_BYTES = 8 * 1024 * 1024

MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"%PDF-", "application/pdf"),
    (b"PK\x03\x04", "application/zip"),
    (b"\x1f\x8b", "application/gzip"),
    (b"OggS", "application/ogg"),
    (b"RIFF", "application/riff"),
    (b"ID3", "audio/mpeg"),
    (b"fLaC", "audio/flac"),
    (b"\x1aE\xdf\xa3", "video/webm"),
)


def decode_field(value):
    """Decode the light escaping used for text fields in event feeds."""
    return unquote(str(value))


def attachment_name(name):
    """Name used on disk for an attachment record."""
    name = decode_field(name).lstrip("/")
    return name or DEFAULT_NAME


def category_for(att):
    """Library section for an attachment, falling back to general."""
    category = decode_field(att.get("category") or DEFAULT_CATEGORY)
    category = category.strip().lower()
    if category in CATEGORIES:
        return category
    return DEFAULT_CATEGORY


def tags_for(att):
    """Lower-case labels attached to a record, without duplicates."""
    tags = att.get("tags") or []
    if isinstance(tags, str):
        tags = tags.split(",")
    collected = []
    for tag in tags:
        tag = decode_field(tag).strip().lower()
        if tag and tag not in collected:
            collected.append(tag)
    return collected


def digest(data):
    """Content checksum for an attachment."""
    return hashlib.sha256(data).hexdigest()


def short_digest(value):
    """Compact form of a checksum for listings."""
    return str(value or "")[:12]


def kind_of(data):
    """Best-effort content label from the leading bytes."""
    for prefix, kind in MAGIC:
        if data.startswith(prefix):
            return kind
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return "application/octet-stream"
    return "text/plain"


def human_size(count):
    """Readable byte count, e.g. 1.4 MB."""
    count = float(count or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if count < 1024 or unit == "GB":
            if unit == "B":
                return "%d B" % count
            return "%.1f %s" % (count, unit)
        count /= 1024
    return "%.1f GB" % count


def index_path(base_dir=BASE_DIR):
    """Location of the library index."""
    return os.path.join(base_dir, INDEX_NAME)


def load_index(base_dir=BASE_DIR):
    """Rows currently recorded in the library index."""
    try:
        with open(index_path(base_dir)) as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return []
    if not isinstance(raw, list):
        return []
    return [row for row in raw if isinstance(row, dict)]


def write_index(rows, base_dir=BASE_DIR):
    """Replace the library index with the supplied rows."""
    os.makedirs(base_dir, exist_ok=True)
    path = index_path(base_dir)
    temporary = path + ".new"
    with open(temporary, "w") as f:
        json.dump(rows, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(temporary, path)


def full_path(row, base_dir=BASE_DIR):
    """Absolute location for an index row."""
    return os.path.join(base_dir, row.get("path", ""))


def _match(rows, name):
    for row in rows:
        if row.get("name") == name:
            return row
        if os.path.basename(row.get("path", "")) == name:
            return row
    return None


def get(name, base_dir=BASE_DIR):
    """Index row for a display name or stored base name."""
    return _match(load_index(base_dir), name)


def free_name(path):
    """Adjust a path so it does not sit on top of an existing file."""
    root, extension = os.path.splitext(path)
    candidate = path
    counter = 2
    while os.path.exists(candidate):
        candidate = "%s-%d%s" % (root, counter, extension)
        counter += 1
    return candidate


def save(att, base_dir=BASE_DIR):
    """Store one attachment under the attachments directory."""
    os.makedirs(base_dir, exist_ok=True)
    payload = att.get("data") or ""
    try:
        data = base64.b64decode(payload)
    except (binascii.Error, ValueError, TypeError):
        data = b""
    if len(data) > MAX_BYTES:
        raise ValueError("attachment is larger than %s" % human_size(MAX_BYTES))

    checksum = digest(data)
    rows = load_index(base_dir)
    category = category_for(att)
    name = attachment_name(att.get("name"))
    path = os.path.join(base_dir, category, name)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)

    rows.append({
        "name": str(att.get("name") or DEFAULT_NAME),
        "path": os.path.relpath(path, base_dir),
        "category": category,
        "size": len(data),
        "sha256": checksum,
        "kind": kind_of(data),
        "added": int(time.time()),
        "event": att.get("event") or att.get("event_id") or "",
        "tags": tags_for(att),
    })
    write_index(rows, base_dir)
    return path


def save_many(items, base_dir=BASE_DIR):
    """Store a batch of attachment records and return their paths."""
    saved = []
    for att in items or []:
        if isinstance(att, dict):
            saved.append(save(att, base_dir=base_dir))
    return saved


def entries(base_dir=BASE_DIR, category=None, tag=None, event=None, query=None):
    """Index rows, optionally narrowed by category, tag, event or text."""
    rows = load_index(base_dir)
    if category:
        rows = [row for row in rows if row.get("category") == category]
    if tag:
        wanted = decode_field(tag).strip().lower()
        rows = [row for row in rows if wanted in row.get("tags", [])]
    if event:
        rows = [row for row in rows if row.get("event") == event]
    if query:
        needle = decode_field(query).strip().lower()
        rows = [row for row in rows if needle in _haystack(row)]
    return rows


def _haystack(row):
    return " ".join([
        str(row.get("name", "")),
        str(row.get("category", "")),
        str(row.get("event", "")),
        " ".join(row.get("tags", [])),
    ]).lower()


def recent(count=10, base_dir=BASE_DIR):
    """Most recently added attachments."""
    rows = sorted(load_index(base_dir),
                  key=lambda row: row.get("added", 0),
                  reverse=True)
    return rows[:count]


def largest(count=10, base_dir=BASE_DIR):
    """Largest attachments in the library."""
    rows = sorted(load_index(base_dir),
                  key=lambda row: int(row.get("size", 0) or 0),
                  reverse=True)
    return rows[:count]


def by_event(items):
    """Group index rows by the event they arrived with."""
    groups = {}
    for row in items:
        key = row.get("event") or "unfiled"
        groups.setdefault(key, []).append(row)
    return groups


def by_day(items):
    """Group index rows by the day they were added."""
    groups = {}
    for row in items:
        stamp = time.strftime("%Y-%m-%d", time.localtime(row.get("added", 0)))
        groups.setdefault(stamp, []).append(row)
    return groups


def top_tags(items, count=10):
    """Most common labels across the supplied rows."""
    counts = {}
    for row in items:
        for tag in row.get("tags", []):
            counts[tag] = counts.get(tag, 0) + 1
    ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    return ranked[:count]


def kind_counts(items):
    """Number of rows per content label."""
    counts = {}
    for row in items:
        kind = row.get("kind", "application/octet-stream")
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def folders(base_dir=BASE_DIR):
    """Attachment count per library section."""
    counts = {}
    for row in load_index(base_dir):
        category = row.get("category", DEFAULT_CATEGORY)
        counts[category] = counts.get(category, 0) + 1
    return counts


def stats(base_dir=BASE_DIR):
    """A small summary of the attachment library."""
    rows = load_index(base_dir)
    total = 0
    for row in rows:
        total += int(row.get("size", 0) or 0)
    newest = max(rows, key=lambda row: row.get("added", 0)) if rows else None
    oldest = min(rows, key=lambda row: row.get("added", 0)) if rows else None
    return {
        "count": len(rows),
        "bytes": total,
        "size": human_size(total),
        "categories": folders(base_dir),
        "kinds": kind_counts(rows),
        "tags": top_tags(rows),
        "newest": newest.get("name") if newest else None,
        "oldest": oldest.get("name") if oldest else None,
    }


def duplicates(base_dir=BASE_DIR):
    """Groups of rows that share the same checksum."""
    groups = {}
    for row in load_index(base_dir):
        checksum = row.get("sha256")
        if checksum:
            groups.setdefault(checksum, []).append(row)
    return [group for group in groups.values() if len(group) > 1]


def read(row, base_dir=BASE_DIR):
    """Bytes stored for one index row."""
    with open(full_path(row, base_dir), "rb") as f:
        return f.read()


def remove(name, base_dir=BASE_DIR):
    """Drop one attachment and its index row."""
    rows = load_index(base_dir)
    row = _match(rows, name)
    if row is None:
        return False
    try:
        os.remove(full_path(row, base_dir))
    except OSError:
        pass
    rows.remove(row)
    write_index(rows, base_dir)
    return True


def rename(name, new_name, base_dir=BASE_DIR):
    """Give an attachment a new display name and stored name."""
    rows = load_index(base_dir)
    row = _match(rows, name)
    if row is None:
        return None
    category = row.get("category", DEFAULT_CATEGORY)
    old_path = full_path(row, base_dir)
    new_path = os.path.join(base_dir, category, attachment_name(new_name))
    new_path = free_name(new_path)
    parent = os.path.dirname(new_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    os.replace(old_path, new_path)
    row["name"] = str(new_name)
    row["path"] = os.path.relpath(new_path, base_dir)
    write_index(rows, base_dir)
    return new_path


def prune(base_dir=BASE_DIR):
    """Forget rows whose files are gone and drop empty sections."""
    rows = load_index(base_dir)
    kept = [row for row in rows if os.path.exists(full_path(row, base_dir))]
    dropped = len(rows) - len(kept)
    if dropped:
        write_index(kept, base_dir)
    for category in CATEGORIES:
        try:
            os.rmdir(os.path.join(base_dir, category))
        except OSError:
            pass
    return dropped


def reindex(base_dir=BASE_DIR):
    """Rebuild the index from the files currently in the library."""
    rows = load_index(base_dir)
    known = {row.get("path"): row for row in rows}
    fresh = []
    for root, dirs, files in os.walk(base_dir):
        dirs.sort()
        for file_name in sorted(files):
            if root == base_dir and file_name == INDEX_NAME:
                continue
            path = os.path.join(root, file_name)
            relative = os.path.relpath(path, base_dir)
            previous = known.get(relative, {})
            try:
                with open(path, "rb") as f:
                    data = f.read()
            except OSError:
                continue
            parts = relative.split(os.sep)
            category = previous.get("category")
            if not category:
                if parts[0] in CATEGORIES:
                    category = parts[0]
                else:
                    category = DEFAULT_CATEGORY
            fresh.append({
                "name": previous.get("name") or file_name,
                "path": relative,
                "category": category,
                "size": len(data),
                "sha256": digest(data),
                "kind": kind_of(data),
                "added": previous.get("added") or int(os.path.getmtime(path)),
                "event": previous.get("event") or "",
                "tags": list(previous.get("tags", [])),
            })
    write_index(fresh, base_dir)
    return len(fresh)


def summary_lines(items):
    """One line per attachment, ordered by the time it was added."""
    lines = []
    ordered = sorted(items, key=lambda row: (row.get("added", 0),
                                             row.get("name", "")))
    for row in ordered:
        stamp = time.strftime("%Y-%m-%d %H:%M",
                              time.localtime(row.get("added", 0)))
        line = "%s  %s" % (stamp, row.get("name", DEFAULT_NAME))
        details = []
        category = row.get("category")
        if category:
            details.append(CATEGORY_TITLES.get(category, category))
        if row.get("size") is not None:
            details.append(human_size(row.get("size", 0)))
        if row.get("tags"):
            details.append(",".join(row["tags"]))
        if details:
            line += "  (%s)" % " / ".join(details)
        lines.append(line)
    return lines


def describe(row):
    """Multi-line detail card for one attachment."""
    return "\n".join([
        "name:     %s" % row.get("name", DEFAULT_NAME),
        "stored:   %s" % row.get("path", ""),
        "category: %s" % CATEGORY_TITLES.get(
            row.get("category", DEFAULT_CATEGORY),
            row.get("category", DEFAULT_CATEGORY)),
        "kind:     %s" % row.get("kind", "application/octet-stream"),
        "size:     %s" % human_size(row.get("size", 0)),
        "sha256:   %s" % short_digest(row.get("sha256")),
        "added:    %s" % time.strftime(
            "%Y-%m-%d %H:%M", time.localtime(row.get("added", 0))),
        "event:    %s" % (row.get("event") or "-"),
        "tags:     %s" % (", ".join(row.get("tags", [])) or "-"),
    ])


def category_bytes(base_dir=BASE_DIR):
    """Total stored bytes for each library section."""
    totals = {}
    for row in load_index(base_dir):
        category = row.get("category", DEFAULT_CATEGORY)
        size = int(row.get("size", 0) or 0)
        totals[category] = totals.get(category, 0) + size
    return totals


def oldest(count=10, base_dir=BASE_DIR):
    """Least recently added attachments."""
    rows = sorted(load_index(base_dir),
                  key=lambda row: row.get("added", 0))
    return rows[:count]


def event_index(base_dir=BASE_DIR):
    """Event ids present in the library with their attachment counts."""
    counts = {}
    for row in load_index(base_dir):
        event = row.get("event") or "unfiled"
        counts[event] = counts.get(event, 0) + 1
    return counts


def text_preview(row, base_dir=BASE_DIR, limit=400):
    """Readable excerpt for text attachments, empty for other kinds."""
    if not str(row.get("kind", "")).startswith("text/"):
        return ""
    try:
        with open(full_path(row, base_dir), "rb") as f:
            data = f.read(limit)
    except OSError:
        return ""
    return data.decode("utf-8", "replace")


def manifest(base_dir=BASE_DIR):
    """JSON-friendly snapshot of the library index."""
    return {
        "generated": int(time.time()),
        "stats": stats(base_dir),
        "attachments": load_index(base_dir),
    }


def report(base_dir=BASE_DIR):
    """Plain-text overview used by the calendar status display."""
    overview = stats(base_dir)
    lines = ["attachments: %d (%s)" % (overview["count"], overview["size"])]
    for category, count in sorted(overview["categories"].items()):
        title = CATEGORY_TITLES.get(category, category)
        lines.append("  %-12s %d" % (title, count))
    if overview["tags"]:
        labels = ["%s (%d)" % pair for pair in overview["tags"]]
        lines.append("tags: " + ", ".join(labels))
    latest = recent(5, base_dir)
    if latest:
        lines.append("recent:")
        for line in summary_lines(latest):
            lines.append("  " + line)
    repeated = duplicates(base_dir)
    if repeated:
        lines.append("duplicates: %d group(s)" % len(repeated))
    return "\n".join(lines)


def relocate(name, category, base_dir=BASE_DIR):
    """Move an attachment to another library section."""
    rows = load_index(base_dir)
    row = _match(rows, name)
    if row is None or category not in CATEGORIES:
        return None
    old_path = full_path(row, base_dir)
    folder = os.path.join(base_dir, category)
    new_path = os.path.join(folder, os.path.basename(row.get("path", "")))
    new_path = free_name(new_path)
    os.makedirs(folder, exist_ok=True)
    os.replace(old_path, new_path)
    row["path"] = os.path.relpath(new_path, base_dir)
    row["category"] = category
    write_index(rows, base_dir)
    return new_path
