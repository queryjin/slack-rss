"""RSS feed 목록 설정.

한국어 경제 기사 RSS 피드를 여기에 등록한다.
- name: Slack 메시지에 표시될 출처 이름
- url:  RSS(XML) 주소

주의: 국내 언론사 RSS 주소는 개편 때마다 바뀌는 경우가 많다.
아래는 널리 쓰이는 후보들이며, 반드시 브라우저나
`python -m feedparser <url>` 로 실제 동작을 확인한 뒤 사용할 것.
동작하지 않는 피드는 실행 시 자동으로 건너뛰고 로그에 남는다.
"""

FEEDS = [
    {"name": "연합뉴스 경제", "url": "https://www.yna.co.kr/rss/economy.xml"},
    {"name": "한겨레 경제", "url": "https://www.hani.co.kr/rss/economy/"},
    {"name": "경향신문 경제", "url": "https://www.khan.co.kr/rss/rssdata/economy_news.xml"},
    {"name": "한국경제", "url": "https://rss.hankyung.com/feed/economy.xml"},
    {"name": "매일경제 경제", "url": "https://www.mk.co.kr/rss/30100041/"},
]
