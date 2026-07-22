# -*- coding: utf-8 -*-
"""진단: 연결된 계정 정보 + 마지막 게시물의 실제 링크/상태를 diag.json에 기록."""
import json, os, urllib.request, urllib.parse

GRAPH = os.environ.get("IG_API_BASE", "https://graph.instagram.com")
token = os.environ["IG_TOKEN"]
user_id = os.environ["IG_USER_ID"]

def get(path, fields):
    url = f"{GRAPH}/{path}?" + urllib.parse.urlencode(
        {"fields": fields, "access_token": token})
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode()[:400]}

out = {}
out["me"] = get("me", "user_id,username,account_type")
# 계정 최근 미디어 목록(최신 5개)
out["recent_media"] = get(f"{user_id}/media", "id,permalink,media_type,timestamp")
# state.json의 마지막 media_id 상태
try:
    st = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")))
    mid = st.get("last", {}).get("media_id")
    if mid:
        out["last_media"] = get(mid, "id,permalink,media_type,timestamp,caption")
except Exception as e:
    out["state_err"] = str(e)

json.dump(out, open("diag.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))
