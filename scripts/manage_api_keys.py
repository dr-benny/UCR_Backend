#!/usr/bin/env python
"""CLI to create, list, and revoke API keys.

Keys are plain JSON files under settings.API_KEY_DIR (see
app/services/api_key_store.py) — this script is just a convenience wrapper
so you don't have to hand-craft the JSON + generate a secret yourself.

Usage:
    python scripts/manage_api_keys.py create "client-a" --daily-limit 500
    python scripts/manage_api_keys.py create "client-b" --daily-limit 300 --max-samples 1
    python scripts/manage_api_keys.py list
    python scripts/manage_api_keys.py revoke <key_id>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.services import api_key_store  # noqa: E402


def _mask(secret: str) -> str:
    return f"...{secret[-4:]}" if len(secret) > 4 else "****"


def cmd_create(args: argparse.Namespace) -> None:
    record = api_key_store.create_key(args.name, daily_limit=args.daily_limit, max_samples=args.max_samples)
    limit = record["daily_limit"] or settings.DEFAULT_DAILY_AI_CALL_LIMIT
    print(f"Created key '{record['name']}' (id: {record['id']})")
    if record["max_samples"] is not None:
        print(f"Max samples per image: {record['max_samples']} (caller may request fewer)")
    print(f"Daily AI-call limit: {limit} (= images x samples actually used)")
    print(f"Secret (shown once, also stored in {settings.API_KEY_DIR}/{record['id']}.json):")
    print(f"  {record['key']}")


def cmd_list(_: argparse.Namespace) -> None:
    records = api_key_store.list_keys()
    if not records:
        print(f"No keys found in {settings.API_KEY_DIR}/")
        return
    for r in records:
        limit = r.get("daily_limit") or settings.DEFAULT_DAILY_AI_CALL_LIMIT
        max_samples = r.get("max_samples")
        suffix = f" (max samples={max_samples})" if max_samples is not None else ""
        print(f"{r['id']}  {r['name']:<20}  limit={limit} AI-calls/day{suffix}  key={_mask(r['key'])}")


def cmd_revoke(args: argparse.Namespace) -> None:
    if api_key_store.delete_key(args.key_id):
        print(f"Revoked key {args.key_id}")
    else:
        print(f"No such key: {args.key_id}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="Generate a new API key")
    p_create.add_argument("name", help="Human-readable label for the key (e.g. a client/team name)")
    p_create.add_argument(
        "--daily-limit", type=int, default=None,
        help=f"Daily AI-call quota, counted as images x samples actually used "
             f"(default: settings.DEFAULT_DAILY_AI_CALL_LIMIT={settings.DEFAULT_DAILY_AI_CALL_LIMIT})",
    )
    p_create.add_argument(
        "--max-samples", type=int, default=None,
        help="Cap on samples-per-image a caller may request with this key (they may still request fewer). "
             "Set to 1 to guarantee --daily-limit images/day regardless of what the caller asks for.",
    )
    p_create.set_defaults(func=cmd_create)

    p_list = sub.add_parser("list", help="List all keys (secrets shown masked)")
    p_list.set_defaults(func=cmd_list)

    p_revoke = sub.add_parser("revoke", help="Delete a key by id")
    p_revoke.add_argument("key_id", help="Key id, as shown by 'list'")
    p_revoke.set_defaults(func=cmd_revoke)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
