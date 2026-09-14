"""한국어 경제 기사 RSS digest를 Slack Incoming Webhook으로 전송한다.

동작 개요
---------
1. feeds.py 의 FEEDS 목록을 순회하며 각 RSS를 파싱한다.
2. 최근 LOOKBACK_HOURS 시간 안에 발행된 기사만 골라 최신순 정렬한다.
3. 피드별 상위 MAX_PER_FEED 건까지 Slack 블록 메시지로 구성한다.
4. SLACK_WEBHOOK_URL 로 POST 한다.

상태(state)를 저장하지 않는다. 중복 방지는 "발행 시각 기준 시간창(window)"
으로만 처리하므로, LOOKBACK_HOURS 는 실행 주기와 맞추는 것이 좋다
(하루 1회 실행 → 24, 하루 2회 → 12).

환경변수
--------
- SLACK_WEBHOOK_URL : (필수) Slack Incoming Webhook URL
- LOOKBACK_HOURS    : (선택) 몇 시간 이내 기사를 볼지. 기본 24
- MAX_PER_FEED      : (선택) 피드당 최대 기사 수. 기본 5
- SEND_WHEN_EMPTY   : (선택) 새 기사가 없어도 알림을 보낼지("1"이면 전송). 기본 미전송
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta, timezone

import feedparser
import requests

# 한국 표준시(KST). 표시·시간창 계산 기준.
KST = timezone(timedelta(hours=9))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("digest")

# 일부 언론사는 기본 python-urllib User-Agent를 차단하므로 브라우저 UA로 요청한다.
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
}


def fetch_feed(url: str):
    """URL을 requests로 받아 feedparser로 파싱한 결과를 반환한다.

    requests를 쓰는 이유: (1) 브라우저 User-Agent 지정으로 차단 회피,
    (2) 명시적 timeout, (3) HTTP(S)_PROXY 등 환경 프록시 설정을 그대로 존중.
    """
    resp = requests.get(url, headers=HTTP_HEADERS, timeout=15)
    resp.raise_for_status()
    return feedparser.parse(resp.content)


def _get_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        log.warning("%s 값(%r)을 정수로 해석할 수 없어 기본값 %d 사용", name, raw, default)
        return default


def _entry_published(entry) -> datetime | None:
    """RSS 엔트리의 발행 시각을 UTC-aware datetime으로 반환. 없으면 None."""
    for key in ("published_parsed", "updated_parsed"):
        tm = entry.get(key)
        if tm:
            # feedparser의 *_parsed는 UTC 기준 time.struct_time.
            return datetime(*tm[:6], tzinfo=timezone.utc)
    return None


def collect_entries(lookback_hours: int, max_per_feed: int):
    """FEEDS를 순회하며 최근 기사 목록을 수집한다.

    반환: [(feed_name, [ {title, link, published(datetime|None)}, ... ]), ...]
    죽은 피드는 건너뛰고 경고 로그만 남긴다.
    """
    from feeds import FEEDS

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    results = []

    for feed in FEEDS:
        name, url = feed["name"], feed["url"]
        try:
            parsed = fetch_feed(url)
        except Exception as exc:  # noqa: BLE001 - 피드 하나 때문에 전체 실행이 죽지 않게
            log.warning("[%s] 수집 실패, 건너뜀: %s", name, exc)
            continue

        if parsed.bozo and not parsed.entries:
            log.warning("[%s] 유효한 항목 없음(bozo=%s), 건너뜀: %s",
                        name, parsed.bozo, getattr(parsed, "bozo_exception", ""))
            continue

        picked = []
        for entry in parsed.entries:
            published = _entry_published(entry)
            # 발행 시각을 못 읽는 피드는 시간창 판단이 불가능하므로 일단 포함한다
            # (단, 최신순 정렬 뒤 max_per_feed로 잘리므로 폭주하지 않는다).
            if published is not None and published < cutoff:
                continue
            title = (entry.get("title") or "(제목 없음)").strip()
            link = entry.get("link") or ""
            if not link:
                continue
            picked.append({"title": title, "link": link, "published": published})

        # 최신순 정렬(발행 시각 없는 항목은 뒤로).
        picked.sort(
            key=lambda e: e["published"] or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        picked = picked[:max_per_feed]

        if picked:
            log.info("[%s] 기사 %d건 수집", name, len(picked))
            results.append((name, picked))
        else:
            log.info("[%s] 최근 %d시간 내 새 기사 없음", name, lookback_hours)

    return results


def build_blocks(results, lookback_hours: int):
    """수집 결과를 Slack Block Kit 형식으로 변환한다."""
    now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    total = sum(len(items) for _, items in results)

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"📰 경제 뉴스 digest ({now_kst} KST)"},
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"최근 {lookback_hours}시간 · 총 {total}건 · 출처 {len(results)}곳",
                }
            ],
        },
        {"type": "divider"},
    ]

    for name, items in results:
        lines = []
        for item in items:
            when = ""
            if item["published"] is not None:
                when = f" _{item['published'].astimezone(KST).strftime('%m/%d %H:%M')}_"
            lines.append(f"• <{item['link']}|{_escape(item['title'])}>{when}")
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{_escape(name)}*\n" + "\n".join(lines)},
            }
        )

    # Slack은 메시지당 블록 50개 제한. 넉넉히 자른다.
    return blocks[:48]


def _escape(text: str) -> str:
    """Slack mrkdwn에서 링크 구문을 깨뜨리는 문자를 이스케이프."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send_to_slack(webhook_url: str, blocks, fallback_text: str) -> None:
    payload = {"text": fallback_text, "blocks": blocks}
    resp = requests.post(webhook_url, json=payload, timeout=15)
    if resp.status_code != 200 or resp.text.strip() != "ok":
        raise RuntimeError(
            f"Slack 전송 실패: status={resp.status_code}, body={resp.text[:300]!r}"
        )
    log.info("Slack 전송 성공")


def main() -> int:
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        log.error("환경변수 SLACK_WEBHOOK_URL 이 설정되지 않았습니다.")
        return 1

    lookback_hours = _get_int_env("LOOKBACK_HOURS", 24)
    max_per_feed = _get_int_env("MAX_PER_FEED", 5)
    send_when_empty = os.environ.get("SEND_WHEN_EMPTY", "") == "1"

    results = collect_entries(lookback_hours, max_per_feed)
    total = sum(len(items) for _, items in results)

    if total == 0:
        log.info("전송할 새 기사가 없습니다.")
        if not send_when_empty:
            return 0
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📭 최근 {lookback_hours}시간 내 새 경제 기사가 없습니다.",
                },
            }
        ]
        send_to_slack(webhook_url, blocks, "경제 뉴스 digest: 새 기사 없음")
        return 0

    blocks = build_blocks(results, lookback_hours)
    send_to_slack(webhook_url, blocks, f"경제 뉴스 digest: {total}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
