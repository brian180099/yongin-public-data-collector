"""Command line entry point for one-time backfill and daily change checks."""

import argparse
import json
import logging
import os

from dotenv import load_dotenv

from .collect import collect
from .sources import DEFAULT_SOURCE_IDS, SOURCES
from .store import ROOT, Store


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("backfill", "daily", "status"))
    parser.add_argument("--source", choices=tuple(SOURCES))
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    store = Store()
    selected = ([SOURCES[args.source]] if args.source else
                [SOURCES[source_id] for source_id in DEFAULT_SOURCE_IDS])
    if args.mode == "status":
        for source in selected:
            state = store.manifest(source.source_id)
            print(json.dumps({"source": source.source_id,
                              "saved_items": len(state["items"]),
                              "last_checked_at": state["last_checked_at"],
                              "last_error": state["last_error"]}, ensure_ascii=False))
        return 0

    key = os.getenv("DATA_GO_KR_SERVICE_KEY")
    failed = False
    for source in selected:
        try:
            result = collect(source, store, key, mode=args.mode)
            store.record_checked(source.source_id)
            print(json.dumps(result, ensure_ascii=False))
        except Exception as exc:
            # Never log the exception string: HTTP URLs can contain the API key.
            message = f"{type(exc).__name__} while collecting {source.source_id}"
            if isinstance(exc, ValueError):
                message = f"{source.source_id}: {exc}"
            store.record_error(source.source_id, message)
            print(json.dumps({"source": source.source_id, "error": message},
                             ensure_ascii=False))
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
