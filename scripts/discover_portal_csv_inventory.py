"""Inventory Yongin portal file search results without collecting or publishing them."""

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
URL = "https://www.data.go.kr/tcs/dss/selectDataSetList.do"
LINK = re.compile(r'/data/(\d+)/fileData\.do')
TAG = re.compile(r'<[^>]+>')


def plain(fragment: str) -> str:
    return re.sub(r'\s+', ' ', html.unescape(TAG.sub(' ', fragment))).strip()


def parse_page(content: bytes) -> tuple[int, list[dict]]:
    document = content.decode('utf-8')
    match = re.search(r'파일데이터\s*<span>\s*\((\d+)건\)', document)
    total = int(match.group(1)) if match else -1
    rows = []
    for chunk in document.split('<div class="apply-result-item">')[1:]:
        link = LINK.search(chunk)
        if not link:
            continue
        title = re.search(r'<a href="/data/\d+/fileData\.do">(.*?)</a>', chunk, re.S)
        provider = re.search(r'<strong>제공기관</strong>(.*?)</li>', chunk, re.S)
        extensions = re.findall(r'data-ext="([A-Za-z0-9]+)"', chunk[:link.start() + 500])
        rows.append({"portal_id": link.group(1), "title": plain(title.group(1)) if title else "",
                     "provider": plain(provider.group(1)) if provider else "",
                     "extensions": sorted(set(extensions)),
                     "url": f"https://www.data.go.kr/data/{link.group(1)}/fileData.do"})
    return total, rows


def main() -> None:
    inventory = {}
    counts = {}
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        for keyword in ("용인", "용인시"):
            page = 1
            while True:
                response = client.get(URL, params={"keyword": keyword, "conditionType": "search",
                                                   "dType": "FILE", "currentPage": page, "perPage": 40})
                response.raise_for_status()
                total, rows = parse_page(response.content)
                if total < 0 or not rows or page > 30:
                    raise RuntimeError(f"unexpected portal pagination for {keyword}: page={page} total={total} rows={len(rows)}")
                counts[keyword] = total
                for row in rows:
                    inventory.setdefault(row["portal_id"], row)["keywords"] = sorted(set(
                        inventory.get(row["portal_id"], {}).get("keywords", [])) | {keyword})
                print(f"keyword={keyword} page={page} rows={len(rows)} total={total}")
                if page * 40 >= total:
                    break
                page += 1
    path = ROOT / "data" / "state" / "portal_search_inventory.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"searched_at": datetime.now(timezone.utc).isoformat(),
                                "search_counts": counts, "datasets": list(inventory.values())},
                               ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"unique_file_results={len(inventory)} csv_badged={sum('CSV' in x['extensions'] for x in inventory.values())}")


if __name__ == "__main__":
    main()
