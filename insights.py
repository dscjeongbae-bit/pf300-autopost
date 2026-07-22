# -*- coding: utf-8 -*-
"""PF-300 인스타그램 반응 지표 수집 (GitHub Actions에서 매일 실행)

동작:
 1) IG_TOKEN 갱신 시도(메모리 내에서만 — 저장은 post.py가 담당, Secret write 경합 회피)
 2) 계정 스냅샷(followers_count, media_count) 조회
 3) 최근 게시물 목록 + 게시물별 인사이트(reach·likes·comments·saved·shares 등) 조회
 4) insights.json에 누적 저장 → 워크플로가 커밋
    - account: 최신 계정 지표
    - history: 날짜별 팔로워 스냅샷(성장 추이 계산용)
    - media[media_id]: 게시물별 최신 지표 + 캡션 일부·permalink·시각

이 파일은 GitHub Actions 러너에서 돌며(datetime 사용 가능), 리포트/이상징후 예약작업이
저장소를 clone해 insights.json을 읽어 분석한다.

환경변수: IG_TOKEN, IG_USER_ID (필수)
"""
import json, os, datetime
import urllib.request, urllib.parse, urllib.error

GRAPH = os.environ.get("IG_API_BASE", "https://graph.instagram.com")
ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "insights.json")

# 게시물(이미지·캐러셀)에서 시도할 지표. API 버전마다 제공 항목이 달라 개별 폴백.
MEDIA_METRICS = ["reach", "likes", "comments", "saved", "shares",
                 "total_interactions", "views"]


def api_get(url, params):
    q = url + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(q, timeout=60) as r:
        return json.load(r)


def refresh_token(token):
    """장기 토큰 갱신(메모리 내에서만 사용). 실패해도 기존 토큰 사용."""
    try:
        r = api_get("https://graph.instagram.com/refresh_access_token",
                    {"grant_type": "ig_refresh_token", "access_token": token})
        if r.get("access_token"):
            return r["access_token"]
    except Exception as e:
        print(f"[token] refresh skipped: {e}")
    return token


def get_account(user_id, token):
    try:
        return api_get(f"{GRAPH}/{user_id}",
                       {"fields": "username,followers_count,media_count",
                        "access_token": token})
    except Exception as e:
        print(f"[account] 조회 실패: {e}")
        return {}


def get_media_list(user_id, token, limit=50):
    try:
        r = api_get(f"{GRAPH}/{user_id}/media",
                    {"fields": "id,caption,media_type,permalink,timestamp",
                     "limit": str(limit), "access_token": token})
        return r.get("data", [])
    except Exception as e:
        print(f"[media] 목록 실패: {e}")
        return []


def get_media_insights(media_id, token):
    """묶어서 시도 → 실패하면 지표 하나씩 폴백."""
    def _fetch(metrics):
        r = api_get(f"{GRAPH}/{media_id}/insights",
                    {"metric": ",".join(metrics), "access_token": token})
        out = {}
        for item in r.get("data", []):
            vals = item.get("values", [{}])
            out[item["name"]] = vals[0].get("value") if vals else item.get("total_value", {}).get("value")
        return out
    try:
        return _fetch(MEDIA_METRICS)
    except urllib.error.HTTPError:
        got = {}
        for m in MEDIA_METRICS:
            try:
                got.update(_fetch([m]))
            except Exception:
                pass
        return got
    except Exception as e:
        print(f"[insights] {media_id} 실패: {e}")
        return {}


def load_prev():
    if os.path.exists(OUT):
        try:
            return json.load(open(OUT, encoding="utf-8"))
        except Exception:
            pass
    return {"account": {}, "history": [], "media": {}}


def main():
    token = refresh_token(os.environ["IG_TOKEN"])
    user_id = os.environ["IG_USER_ID"]
    now = datetime.datetime.now(datetime.timezone.utc)
    today = now.strftime("%Y-%m-%d")
    stamp = now.isoformat(timespec="seconds")

    data = load_prev()

    # 1) 계정 스냅샷
    acct = get_account(user_id, token)
    if acct:
        acct["checked_at"] = stamp
        data["account"] = acct
        # 날짜별 팔로워 추이(하루 1개만 유지)
        hist = [h for h in data.get("history", []) if h.get("date") != today]
        hist.append({"date": today,
                     "followers_count": acct.get("followers_count"),
                     "media_count": acct.get("media_count")})
        data["history"] = hist[-120:]   # 최근 120일
        print(f"[account] @{acct.get('username')} followers={acct.get('followers_count')} media={acct.get('media_count')}")

    # 2) 게시물별 지표
    media = data.get("media", {})
    for m in get_media_list(user_id, token):
        mid = m["id"]
        ins = get_media_insights(mid, token)
        cap = (m.get("caption") or "").strip().replace("\n", " ")
        media[mid] = {
            "permalink": m.get("permalink"),
            "media_type": m.get("media_type"),
            "timestamp": m.get("timestamp"),
            "caption_excerpt": cap[:80],
            "metrics": ins,
            "checked_at": stamp,
        }
        print(f"[media] {mid} {ins}")
    data["media"] = media
    data["updated_at"] = stamp

    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[done] insights.json 저장 — media {len(media)}개")


if __name__ == "__main__":
    main()
