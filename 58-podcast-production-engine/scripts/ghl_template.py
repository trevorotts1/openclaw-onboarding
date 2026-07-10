#!/usr/bin/env python3
"""Create or verify the Skill 58 template inventory in one Convert and Flow location.

The tool is intentionally narrow. It manages only the fields, custom values, and
tags declared in config/ghl-template.json. It never creates surveys, workflows,
contacts, messages, or pipeline objects. Credentials remain in memory and output
contains object names, counts, and verification results only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


EXIT_OK = 0
EXIT_USAGE = 2
EXIT_AUTH = 3
EXIT_MISMATCH = 4
EXIT_RATE_LIMIT = 5

API_BASE = "https://services.leadconnectorhq.com"
USER_AGENT = "Mozilla/5.0 CodexPodcastEngine/1.0"
PIT_ENV = "PODCAST_ENGINE_GHL_PIT"
LOCATION_ENV = "PODCAST_ENGINE_GHL_LOCATION_ID"
FOREIGN_PREFIX = "antho" + "logy"

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SPEC = SKILL_DIR / "config" / "ghl-template.json"


class TemplateError(RuntimeError):
    pass


class AuthError(TemplateError):
    pass


class MismatchError(TemplateError):
    pass


class RateLimitError(TemplateError):
    pass


def load_spec(path: Path = DEFAULT_SPEC) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        spec = json.load(handle)
    validate_spec(spec)
    return spec


def expected_field_key(create_name: str) -> str:
    return "contact." + create_name


def validate_spec(spec: dict[str, Any]) -> None:
    target = spec.get("target") or {}
    if not target.get("location_id"):
        raise MismatchError("template spec has no target location")

    fields = spec.get("custom_fields") or []
    values = spec.get("custom_values") or []
    tags = spec.get("tags") or []
    if len(fields) != 28 or len(values) != 6 or len(tags) != 2:
        raise MismatchError(
            "inventory count mismatch: expected fields=28 values=6 tags=2"
        )

    names = [item.get("name") for item in fields]
    if len(names) != len(set(names)) or not all(names):
        raise MismatchError("custom field names must be non-empty and unique")
    if "podcast_survey__additional_info" not in names:
        raise MismatchError("double-underscore field is absent")
    if "podcast_survey_additional_info" in names:
        raise MismatchError("single-underscore field is forbidden")

    value_names = [item.get("name") for item in values]
    if len(value_names) != len(set(value_names)) or not all(value_names):
        raise MismatchError("custom value names must be non-empty and unique")
    if sum(bool(item.get("stamp_last")) for item in values) != 1:
        raise MismatchError("exactly one custom value must carry stamp_last")

    all_names = [str(name) for name in names + value_names + list(tags)]
    if any(FOREIGN_PREFIX in name.lower() for name in all_names):
        raise MismatchError("foreign object prefix found in template inventory")

    allowed_types = {"TEXT", "LARGE_TEXT", "SINGLE_OPTIONS", "DATE"}
    for item in fields:
        if item.get("data_type") not in allowed_types:
            raise MismatchError("unsupported data type for " + item["name"])
        options = item.get("options") or []
        if item["data_type"] == "SINGLE_OPTIONS" and not options:
            raise MismatchError("picklist options missing for " + item["name"])
        if item["data_type"] != "SINGLE_OPTIONS" and options:
            raise MismatchError("non-picklist field carries options: " + item["name"])


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise AuthError(name + " is NOT SET")
    return value


class ConvertFlowClient:
    def __init__(self, token: str, location_id: str, version: str, timeout: int = 25):
        if not token.startswith("pit-"):
            raise AuthError(PIT_ENV + " does not have the required token prefix")
        self._token = token
        self.location_id = location_id
        self.version = version
        self.timeout = timeout
        self.rate: dict[str, str] = {}

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = API_BASE + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = {
            "Authorization": "Bearer " + self._token,
            "Version": self.version,
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                self._remember_rate_headers(response.headers)
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as exc:
            self._remember_rate_headers(exc.headers)
            if exc.code == 429:
                raise RateLimitError("location rate limit reached") from None
            if exc.code in (401, 403):
                raise AuthError("location token was rejected or lacks the required scope") from None
            if exc.code in (400, 409, 422):
                raise MismatchError(
                    "Convert and Flow rejected %s %s with HTTP %s"
                    % (method, path, exc.code)
                ) from None
            raise TemplateError("Convert and Flow returned HTTP %s" % exc.code) from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise TemplateError("Convert and Flow transport failed: " + type(exc).__name__) from None

    def _remember_rate_headers(self, headers: Any) -> None:
        if not headers:
            return
        for name in (
            "x-ratelimit-remaining",
            "x-ratelimit-daily-remaining",
            "x-ratelimit-limit-daily",
            "x-ratelimit-daily-reset",
        ):
            value = headers.get(name)
            if value is not None:
                self.rate[name] = str(value)

    def get_location(self) -> dict[str, Any]:
        encoded = urllib.parse.quote(self.location_id, safe="")
        payload = self._request("GET", "/locations/" + encoded)
        return payload.get("location") or payload

    def list_fields(self) -> list[dict[str, Any]]:
        encoded = urllib.parse.quote(self.location_id, safe="")
        payload = self._request(
            "GET", "/locations/%s/customFields" % encoded, query={"model": "contact"}
        )
        return payload.get("customFields") or []

    def create_field(self, item: dict[str, Any]) -> dict[str, Any]:
        encoded = urllib.parse.quote(self.location_id, safe="")
        body: dict[str, Any] = {
            "name": item["name"],
            "dataType": item["data_type"],
            "model": "contact",
        }
        if item.get("options"):
            body["options"] = list(item["options"])
        payload = self._request("POST", "/locations/%s/customFields" % encoded, body=body)
        return payload.get("customField") or payload

    def list_values(self) -> list[dict[str, Any]]:
        encoded = urllib.parse.quote(self.location_id, safe="")
        payload = self._request("GET", "/locations/%s/customValues" % encoded)
        return payload.get("customValues") or []

    def create_value(self, item: dict[str, Any]) -> dict[str, Any]:
        encoded = urllib.parse.quote(self.location_id, safe="")
        payload = self._request(
            "POST",
            "/locations/%s/customValues" % encoded,
            body={"name": item["name"], "value": item["value"]},
        )
        return payload.get("customValue") or payload

    def list_tags(self) -> list[dict[str, Any]]:
        encoded = urllib.parse.quote(self.location_id, safe="")
        payload = self._request("GET", "/locations/%s/tags" % encoded)
        return payload.get("tags") or []

    def create_tag(self, name: str) -> dict[str, Any]:
        encoded = urllib.parse.quote(self.location_id, safe="")
        payload = self._request(
            "POST", "/locations/%s/tags" % encoded, body={"name": name}
        )
        return payload.get("tag") or payload


def make_client(spec: dict[str, Any]) -> ConvertFlowClient:
    token = _required_env(PIT_ENV)
    location_id = _required_env(LOCATION_ENV)
    expected = spec["target"]["location_id"]
    if location_id != expected:
        raise MismatchError("configured location does not match the template target")
    version = os.environ.get(
        "PODCAST_GHL_API_VERSION", spec["target"].get("api_version", "v3")
    ).strip()
    return ConvertFlowClient(token, location_id, version)


def prove_location(client: ConvertFlowClient, spec: dict[str, Any]) -> dict[str, Any]:
    location = client.get_location()
    if location.get("id") != spec["target"]["location_id"]:
        raise MismatchError("live location pair-probe did not match the template target")
    live_name = str(location.get("name") or "")
    allowed = {name.casefold() for name in spec["target"].get("allowed_location_names", [])}
    return {
        "id_match": True,
        "name_match": live_name.casefold() in allowed,
        "location_name": live_name,
    }


def _field_options(field: dict[str, Any]) -> list[str]:
    options = field.get("picklistOptions")
    if isinstance(options, list):
        return [str(item) for item in options]
    options = field.get("options")
    if not isinstance(options, list):
        return []
    out = []
    for item in options:
        if isinstance(item, dict):
            out.append(str(item.get("label") or item.get("value") or item.get("key") or ""))
        else:
            out.append(str(item))
    return out


def verify_field(item: dict[str, Any], live: dict[str, Any]) -> None:
    expected_key = expected_field_key(item["name"])
    if live.get("fieldKey") != expected_key:
        raise MismatchError("field key mismatch for " + item["name"])
    if live.get("dataType") != item["data_type"]:
        raise MismatchError("field data type mismatch for " + item["name"])
    expected_options = item.get("options") or []
    if expected_options and _field_options(live) != expected_options:
        raise MismatchError("field options mismatch for " + item["name"])


def apply_fields(client: ConvertFlowClient, spec: dict[str, Any]) -> dict[str, Any]:
    live = client.list_fields()
    by_key = {item.get("fieldKey"): item for item in live if item.get("fieldKey")}
    by_name = {item.get("name"): item for item in live if item.get("name")}
    created: list[str] = []
    verified: list[str] = []
    for item in spec["custom_fields"]:
        key = expected_field_key(item["name"])
        existing = by_key.get(key)
        if existing:
            verify_field(item, existing)
            verified.append(item["name"])
            continue
        if item["name"] in by_name:
            raise MismatchError("field name exists under a different key: " + item["name"])
        created_live = client.create_field(item)
        verify_field(item, created_live)
        created.append(item["name"])
        by_key[key] = created_live
        by_name[item["name"]] = created_live
    return {"created": created, "verified": verified}


def apply_values(
    client: ConvertFlowClient, spec: dict[str, Any], *, stamp_version: bool
) -> dict[str, Any]:
    live = client.list_values()
    by_name = {item.get("name"): item for item in live if item.get("name")}
    created: list[str] = []
    verified: list[str] = []
    deferred: list[str] = []
    for item in spec["custom_values"]:
        if item.get("stamp_last") and not stamp_version:
            deferred.append(item["name"])
            continue
        existing = by_name.get(item["name"])
        if existing:
            if str(existing.get("value")) != str(item["value"]):
                raise MismatchError("custom value content mismatch for " + item["name"])
            verified.append(item["name"])
            continue
        created_live = client.create_value(item)
        if created_live.get("name") != item["name"]:
            raise MismatchError("custom value name mismatch for " + item["name"])
        if str(created_live.get("value")) != str(item["value"]):
            raise MismatchError("custom value content mismatch for " + item["name"])
        created.append(item["name"])
        by_name[item["name"]] = created_live
    return {"created": created, "verified": verified, "deferred": deferred}


def apply_tags(client: ConvertFlowClient, spec: dict[str, Any]) -> dict[str, Any]:
    live = client.list_tags()
    by_folded = {str(item.get("name") or "").casefold(): item for item in live}
    created: list[str] = []
    verified: list[str] = []
    for name in spec["tags"]:
        existing = by_folded.get(name.casefold())
        if existing:
            verified.append(str(existing.get("name") or name))
            continue
        created_live = client.create_tag(name)
        live_name = str(created_live.get("name") or "")
        if live_name.casefold() != name.casefold():
            raise MismatchError("tag name mismatch for " + name)
        created.append(live_name or name)
        by_folded[name.casefold()] = created_live
    return {"created": created, "verified": verified}


def verify_inventory(
    client: ConvertFlowClient, spec: dict[str, Any], *, allow_unstamped: bool
) -> dict[str, Any]:
    fields = client.list_fields()
    values = client.list_values()
    tags = client.list_tags()
    field_by_key = {item.get("fieldKey"): item for item in fields}
    value_by_name = {item.get("name"): item for item in values}
    tag_by_folded = {str(item.get("name") or "").casefold(): item for item in tags}

    for item in spec["custom_fields"]:
        live = field_by_key.get(expected_field_key(item["name"]))
        if not live:
            raise MismatchError("missing field " + item["name"])
        verify_field(item, live)

    checked_values = 0
    for item in spec["custom_values"]:
        live = value_by_name.get(item["name"])
        if not live and allow_unstamped and item.get("stamp_last"):
            continue
        if not live:
            raise MismatchError("missing custom value " + item["name"])
        if str(live.get("value")) != str(item["value"]):
            raise MismatchError("custom value content mismatch for " + item["name"])
        checked_values += 1

    for name in spec["tags"]:
        if name.casefold() not in tag_by_folded:
            raise MismatchError("missing tag " + name)

    foreign = []
    for item in fields:
        marker = str(item.get("fieldKey") or item.get("name") or "").lower()
        if FOREIGN_PREFIX in marker:
            foreign.append(marker)
    for item in values:
        marker = str(item.get("name") or "").lower()
        if FOREIGN_PREFIX in marker:
            foreign.append(marker)
    for item in tags:
        marker = str(item.get("name") or "").lower()
        if FOREIGN_PREFIX in marker:
            foreign.append(marker)
    if foreign:
        raise MismatchError("foreign object contamination detected")

    return {
        "fields": len(spec["custom_fields"]),
        "custom_values": checked_values,
        "tags": len(spec["tags"]),
        "double_underscore_key": True,
        "foreign_object_count": 0,
    }


def plan(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "location_id": spec["target"]["location_id"],
        "api_version": spec["target"]["api_version"],
        "custom_field_count": len(spec["custom_fields"]),
        "custom_value_count": len(spec["custom_values"]),
        "tag_count": len(spec["tags"]),
        "field_keys": [expected_field_key(item["name"]) for item in spec["custom_fields"]],
        "version_stamp_deferred_until_final_qc": True,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage the Skill 58 template inventory")
    parser.add_argument("command", choices=("plan", "audit", "apply", "verify"))
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument(
        "--classes",
        default="fields,values,tags",
        help="comma-separated apply classes: fields,values,tags",
    )
    parser.add_argument(
        "--stamp-version",
        action="store_true",
        help="create or verify the version custom value after final QC",
    )
    parser.add_argument(
        "--allow-unstamped",
        action="store_true",
        help="verification may omit the deferred version stamp",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        spec = load_spec(args.spec)
        if args.command == "plan":
            print(json.dumps(plan(spec), indent=2, sort_keys=True))
            return EXIT_OK

        client = make_client(spec)
        location = prove_location(client, spec)
        output: dict[str, Any] = {"location": location, "api_version": client.version}

        if args.command == "audit":
            output["inventory"] = {
                "fields": len(client.list_fields()),
                "custom_values": len(client.list_values()),
                "tags": len(client.list_tags()),
            }
        elif args.command == "apply":
            classes = {item.strip() for item in args.classes.split(",") if item.strip()}
            unknown = classes - {"fields", "values", "tags"}
            if unknown:
                raise MismatchError("unknown object class in --classes")
            if "fields" in classes:
                output["fields"] = apply_fields(client, spec)
            if "values" in classes:
                output["custom_values"] = apply_values(
                    client, spec, stamp_version=args.stamp_version
                )
            if "tags" in classes:
                output["tags"] = apply_tags(client, spec)
        else:
            output["verification"] = verify_inventory(
                client, spec, allow_unstamped=args.allow_unstamped
            )
        output["rate"] = client.rate
        print(json.dumps(output, indent=2, sort_keys=True))
        return EXIT_OK
    except AuthError as exc:
        print("AUTH STOP: " + str(exc), file=sys.stderr)
        return EXIT_AUTH
    except RateLimitError as exc:
        print("RATE STOP: " + str(exc), file=sys.stderr)
        return EXIT_RATE_LIMIT
    except MismatchError as exc:
        print("MISMATCH STOP: " + str(exc), file=sys.stderr)
        return EXIT_MISMATCH
    except (TemplateError, OSError, ValueError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
