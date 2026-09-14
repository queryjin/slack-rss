# slack-rss

한국어 경제 기사 RSS를 모아 매일 아침 Slack으로 보내는 digest 봇.
GitHub Actions 스케줄로 실행되며, 서버·상태 저장소가 필요 없다.

## 동작 방식

```
경제 RSS 피드(여러 개)  →  최근 24시간 기사 필터  →  Slack Incoming Webhook 전송
```

- 매일 **08:00 KST**(= 23:00 UTC)에 GitHub Actions가 `send_digest.py`를 실행한다.
- 최근 `LOOKBACK_HOURS`(기본 24) 시간 내 발행 기사만 골라 출처별로 묶어 전송한다.
- 상태를 저장하지 않는다. 중복 방지는 "발행 시각 기준 시간창"으로만 처리하므로
  **실행 주기와 `LOOKBACK_HOURS`를 맞추는 것**이 중요하다(하루 1회 → 24).

## 구성 파일

| 파일 | 역할 |
|------|------|
| `feeds.py` | 수집할 RSS 피드 목록(`FEEDS`). 여기서 추가·삭제 |
| `send_digest.py` | 수집·필터·Slack 전송 본체 |
| `.github/workflows/digest.yml` | 스케줄 실행 워크플로 |
| `requirements.txt` | 의존성(`feedparser`, `requests`) |
| `.env.example` | 로컬 실행용 환경변수 예시 |

## 설정

### 1) Slack Incoming Webhook 발급
Slack → 앱 관리 → **Incoming Webhooks** 활성화 → 채널 선택 → Webhook URL 복사
(`https://hooks.slack.com/services/...`).

### 2) GitHub Secret 등록
저장소 **Settings → Secrets and variables → Actions → New repository secret**

| 이름 | 값 |
|------|-----|
| `SLACK_WEBHOOK_URL` | 위에서 복사한 Webhook URL |

> Webhook URL은 노출되면 누구나 채널에 메시지를 보낼 수 있으므로 **절대 코드에 커밋하지 말 것.**
> 공개 저장소이므로 반드시 Secret으로만 관리한다.

### 3) 피드 편집
`feeds.py`의 `FEEDS` 리스트에서 원하는 언론사 RSS를 추가/삭제한다.

> ⚠️ **국내 언론사 RSS 주소는 개편 때마다 바뀐다.** 현재 시드로 넣은 주소들은
> 실제 동작을 보장하지 않는다. 브라우저나 아래 로컬 실행으로 각 피드가
> 유효한지 확인할 것. 죽은 피드는 실행 시 자동으로 건너뛰고 경고 로그를 남긴다.

## 로컬 실행 (테스트)

```bash
pip install -r requirements.txt
cp .env.example .env        # .env 에 실제 Webhook URL 채우기
export $(grep -v '^#' .env | xargs)
python send_digest.py
```

수동 실행은 GitHub Actions의 **Actions 탭 → econ-slack-digest → Run workflow**(workflow_dispatch)로도 가능하다.

## 환경변수

| 변수 | 필수 | 기본 | 설명 |
|------|:---:|:---:|------|
| `SLACK_WEBHOOK_URL` | ✅ | – | Slack Incoming Webhook URL |
| `LOOKBACK_HOURS` | | 24 | 몇 시간 이내 기사를 볼지 |
| `MAX_PER_FEED` | | 5 | 피드당 최대 기사 수 |
| `SEND_WHEN_EMPTY` | | 미전송 | `1`이면 새 기사가 없어도 알림 전송 |

## 스케줄 변경

`.github/workflows/digest.yml`의 cron은 **UTC 기준**이다. KST는 +9시간이므로
원하는 KST 시각에서 9를 빼서 UTC로 환산한다(자정을 넘기면 날짜 필드도 조정).

| 원하는 시각(KST) | cron(UTC) |
|---|---|
| 매일 08:00 | `0 23 * * *` |
| 매일 18:00 | `0 9 * * *` |
| 평일 08:00 | `0 23 * * 0-4` |
