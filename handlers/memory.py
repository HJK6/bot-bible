import os
import json
import boto3
import re
import time
import logging
from concurrent.futures import ThreadPoolExecutor

from handlers.apigw import apigw_adapter

logger = logging.getLogger(__name__)

BUCKET = os.environ.get("MEDIA_BUCKET", "bartimaeus-chat-media")
PREFIX = "memory/files/"
INDEX_KEY = "memory/index.json"

s3 = boto3.client("s3")

# Module-level cache for tree
_tree_cache = {"tree": None, "timestamp": 0}
CACHE_TTL = 60


def _extract_description(body_bytes):
    """Extract description from frontmatter or first heading/line of a markdown file."""
    try:
        text = body_bytes.decode("utf-8", errors="replace")
    except Exception:
        return None

    # Try frontmatter
    fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).splitlines():
            m = re.match(r"description:\s*(.+)", line)
            if m:
                return m.group(1).strip().strip("\"'")

    # Try first heading
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        heading = re.match(r"^#+\s+(.+)", line)
        if heading:
            return heading.group(1).strip()
        # Fall back to first non-empty line
        return line[:120]

    return None


def _parse_frontmatter(text):
    """Parse YAML-like frontmatter from text, return dict or None."""
    fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not fm_match:
        return None
    result = {}
    for line in fm_match.group(1).splitlines():
        m = re.match(r"(\w+):\s*(.+)", line)
        if m:
            result[m.group(1)] = m.group(2).strip().strip("\"'")
    return result if result else None


def _fetch_description(key):
    """Fetch first 512 bytes of an S3 object and extract description."""
    try:
        resp = s3.get_object(Bucket=BUCKET, Key=key, Range="bytes=0-511")
        body = resp["Body"].read()
        return key, _extract_description(body)
    except Exception as e:
        logger.warning(f"Failed to read description for {key}: {e}")
        return key, None


def _build_tree():
    """List all objects under memory/ and build a directory tree with descriptions."""
    # List all objects
    objects = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=PREFIX):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            rel_path = key[len(PREFIX):]
            if not rel_path:
                continue
            objects.append({
                "key": key,
                "path": rel_path,
                "size": obj["Size"],
                "last_modified": obj["LastModified"].isoformat(),
            })

    # Fetch descriptions in parallel for .md files
    md_objects = [o for o in objects if o["key"].endswith(".md")]
    descriptions = {}
    if md_objects:
        with ThreadPoolExecutor(max_workers=min(20, len(md_objects))) as pool:
            results = pool.map(lambda o: _fetch_description(o["key"]), md_objects)
            for key, desc in results:
                if desc:
                    descriptions[key] = desc

    # Build tree structure
    root = []
    dirs = {}  # path -> children list

    def _get_dir(dir_path):
        """Get or create a directory node, creating parents as needed."""
        if dir_path in dirs:
            return dirs[dir_path]
        parts = dir_path.split("/")
        parent_list = root
        for i, part in enumerate(parts):
            current_path = "/".join(parts[: i + 1])
            if current_path not in dirs:
                node = {"name": part, "type": "directory", "children": []}
                dirs[current_path] = node["children"]
                parent_list.append(node)
            parent_list = dirs[current_path]
        return dirs[dir_path]

    for obj in objects:
        rel_path = obj["path"]
        parts = rel_path.split("/")
        name = parts[-1]

        file_node = {
            "name": name,
            "type": "file",
            "path": rel_path,
            "size": obj["size"],
            "last_modified": obj["last_modified"],
        }
        desc = descriptions.get(obj["key"])
        if desc:
            file_node["description"] = desc

        if len(parts) == 1:
            root.append(file_node)
        else:
            dir_path = "/".join(parts[:-1])
            parent = _get_dir(dir_path)
            parent.append(file_node)

    return root


@apigw_adapter
def getMemoryTreeHandler(event, context):
    """List all memory files as a tree structure."""
    now = time.time()
    if _tree_cache["tree"] is not None and (now - _tree_cache["timestamp"]) < CACHE_TTL:
        return {"tree": _tree_cache["tree"]}

    try:
        tree = _build_tree()
        _tree_cache["tree"] = tree
        _tree_cache["timestamp"] = now
        return {"tree": tree}
    except Exception as e:
        logger.exception("Failed to build memory tree")
        return {"status": "error", "message": str(e)}


@apigw_adapter
def getMemoryFileHandler(event, context):
    """Read a specific memory file by path."""
    path = event.get("path", "")

    # Validate path
    if not path:
        return {"status": "error", "message": "path is required", "code": 400}
    if ".." in path:
        return {"status": "error", "message": "invalid path", "code": 400}
    if not path.endswith((".md", ".json")):
        return {"status": "error", "message": "only .md and .json files are supported", "code": 400}

    s3_key = PREFIX + path

    try:
        resp = s3.get_object(Bucket=BUCKET, Key=s3_key)
        content = resp["Body"].read().decode("utf-8", errors="replace")
        size = resp["ContentLength"]
        last_modified = resp["LastModified"].isoformat()
    except s3.exceptions.NoSuchKey:
        return {"status": "error", "message": "file not found", "code": 404}
    except Exception as e:
        logger.exception(f"Failed to read memory file: {s3_key}")
        return {"status": "error", "message": str(e)}

    name = path.split("/")[-1]
    frontmatter = _parse_frontmatter(content) if path.endswith(".md") else None

    result = {
        "path": path,
        "name": name,
        "content": content,
        "last_modified": last_modified,
        "size": size,
    }
    if frontmatter:
        result["frontmatter"] = frontmatter

    return result


# Cache for index
_index_cache = {"data": None, "timestamp": 0}


@apigw_adapter
def getMemoryIndexHandler(event, context):
    """Read the structured memory index (parsed from MEMORY.md)."""
    now = time.time()
    if _index_cache["data"] is not None and (now - _index_cache["timestamp"]) < CACHE_TTL:
        return _index_cache["data"]

    try:
        resp = s3.get_object(Bucket=BUCKET, Key=INDEX_KEY)
        data = json.loads(resp["Body"].read().decode("utf-8"))
        _index_cache["data"] = data
        _index_cache["timestamp"] = now
        return data
    except s3.exceptions.NoSuchKey:
        return {"sections": [], "files": [], "synced_at": None}
    except Exception as e:
        logger.exception("Failed to read memory index")
        return {"status": "error", "message": str(e)}
