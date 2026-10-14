"""Queue the ready-to-post X threads in Buffer (config/x.json "mode": "buffer").

pipeline/social.py writes each thread's chart images into the site (_site/x/) and a manifest (_site/x/pending.json)
during the scan; this runs after the site is live, because Buffer fetches images by public URL:

    python -m pipeline.buffer --site _site --site-url https://filing-flows.com/

Secrets / variables: BUFFER_API_KEY (Buffer → Settings → API → Personal Access); BUFFER_CHANNEL_ID optional —
without it the first X / Twitter channel of the account is used. Posts go to the channel's queue (Buffer's own
posting schedule); nothing is published without a slot in that schedule.
"""
import argparse
import json
import os
import sys

import requests

API = "https://api.buffer.com"


class BufferError(RuntimeError):
    pass


def gql(key, query, variables=None):
    r = requests.post(API, json={"query": query, "variables": variables or {}},
                      headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, timeout=60)
    try:
        body = r.json()
    except ValueError:
        raise BufferError(f"HTTP {r.status_code}: {r.text[:200]}")
    if r.status_code >= 400 or body.get("errors"):
        raise BufferError(f"HTTP {r.status_code}: {json.dumps(body.get('errors') or body)[:400]}")
    return body["data"]


def x_channel(key, wanted=None):
    orgs = gql(key, "query { account { organizations { id name } } }")["account"]["organizations"]
    for org in orgs:
        chans = gql(key, "query($org: OrganizationId!) { channels(input: { organizationId: $org }) { id name service isQueuePaused } }",
                    {"org": org["id"]})["channels"]
        for ch in chans:
            if wanted and ch["id"] == wanted:
                return ch
            if not wanted and str(ch.get("service", "")).lower() in ("twitter", "x"):
                return ch
    raise BufferError("no X channel found" + (f" with id {wanted}" if wanted else "") + "; connect X in Buffer or set BUFFER_CHANNEL_ID")


def create_thread(key, channel_id, parts, due_at=None):
    """parts: [{"text": str, "images": [public url, ...]}]; the first part carries the charts."""
    thread = [{"text": p["text"], **({"assets": [{"image": {"url": u}} for u in p.get("images", [])[:4]]} if p.get("images") else {})}
              for p in parts]
    inp = {"channelId": channel_id, "text": parts[0]["text"], "schedulingType": "automatic",
           "mode": "customScheduled" if due_at else "addToQueue", "metadata": {"twitter": {"thread": thread}}}
    if due_at:
        inp["dueAt"] = due_at
    data = gql(key, """mutation($input: CreatePostInput!) { createPost(input: $input) {
        ... on PostActionSuccess { post { id status dueAt } } ... on MutationError { message } } }""", {"input": inp})
    res = data["createPost"]
    if "message" in res:
        raise BufferError(res["message"])
    return res["post"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="_site")
    ap.add_argument("--site-url", default=os.environ.get("SITE_URL", ""))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    key = os.environ.get("BUFFER_API_KEY", "")
    path = os.path.join(args.site, "x", "pending.json")
    if not os.path.exists(path):
        print("buffer: nothing queued by the scan")
        return
    items = json.load(open(path, encoding="utf-8"))
    if not items:
        print("buffer: nothing queued by the scan")
        return
    if not key:
        print(f"::warning::BUFFER_API_KEY missing; {len(items)} thread(s) not queued")
        return
    base = args.site_url.rstrip("/")
    if not base:
        print("::error::site URL unknown; Buffer needs public image URLs")
        sys.exit(1)
    ch = x_channel(key, os.environ.get("BUFFER_CHANNEL_ID") or None)
    print(f"buffer: channel {ch['name']} ({ch['service']}, {ch['id']}){' · queue paused' if ch.get('isQueuePaused') else ''}")
    failed = 0
    for it in items:
        parts = [{"text": p, "images": ([f"{base}/x/{n}" for n in it["images"]] if i == 0 else [])} for i, p in enumerate(it["posts"])]
        if args.dry_run:
            print(f"would queue {it['label']}: {len(parts)} posts, images {parts[0]['images']}")
            continue
        try:
            post = create_thread(key, ch["id"], parts)
            print(f"queued {it['label']}: post {post['id']} ({post.get('status')}, due {post.get('dueAt')})")
        except BufferError as err:
            failed += 1
            print(f"::warning::{it['label']} not queued: {err}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
