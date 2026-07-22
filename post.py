# -*- coding: utf-8 -*-
"""PF-300 카드뉴스 → 인스타그램 캐러셀 자동 게시 (GitHub Actions에서 실행)

동작:
 1) 60일 장기 토큰을 갱신 시도(발급 24h 이후부터 가능)하고, GH_PAT가 있으면
    갱신된 토큰을 저장소 Secret(IG_TOKEN)에 다시 저장 → 사실상 무기한 무인 운영
 2) sets/ 폴더의 세트를 순서대로 하나 골라(state.json에 기록된 건 건너뜀)
 3) 이미지를 공개 CDN(jsDelivr, 실패 시 raw.githubusercontent)로 인스타에 넘겨 캐러셀 게시
 4) 성공하면 state.json에 기록하고 커밋. 모든 세트를 다 돌면 처음부터 순환.

환경변수(Actions Secret/기본 제공):
 IG_TOKEN, IG_USER_ID            (필수)
 GH_PAT                          (선택 — 토큰 자동 갱신 저장용, repo 권한)
 GITHUB_REPOSITORY, GITHUB_SHA   (Actions 기본 제공)
"""
import json, os, sys, time, glob
import urllib.request, urllib.parse, urllib.error

GRAPH = "https://graph.instagram.com/v23.0"
REPO = os.environ.get("GITHUB_REPOSITORY", "")   # "owner/name"
BRANCH = "main"
ROOT = os.path.dirname(os.path.abspath(__file__))


def api_get(url, params):
    q = url + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(q, timeout=60) as r:
        return json.load(r)


def api_post(url, data):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode())
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def refresh_token(token):
    """장기 토큰 갱신. 실패해도(24h 미경과 등) 기존 토큰 그대로 사용."""
    try:
        r = api_get("https://graph.instagram.com/refresh_access_token",
                    {"grant_type": "ig_refresh_token", "access_token": token})
        if r.get("access_token"):
            print(f"[token] refreshed, expires_in={r.get('expires_in')}s")
            return r["access_token"], True
    except Exception as e:
        print(f"[token] refresh skipped: {e}")
    return token, False


def persist_secret(name, value):
    """GH_PAT가 있으면 갱신된 토큰을 저장소 Secret에 다시 저장(암호화 필요)."""
    pat = os.environ.get("GH_PAT")
    if not (pat and REPO):
        print("[secret] GH_PAT/REPO 없음 → 토큰 저장 생략(60일 후 수동 갱신 필요)")
        return
    try:
        from nacl import encoding, public
    except Exception:
        print("[secret] pynacl 미설치 → 저장 생략")
        return
    try:
        # 저장소 공개키 조회
        req = urllib.request.Request(
            f"https://api.github.com/repos/{REPO}/actions/secrets/public-key",
            headers={"Authorization": f"token {pat}", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            pk = json.load(r)
        pub = public.PublicKey(pk["key"].encode(), encoding.Base64Encoder())
        sealed = public.SealedBox(pub).encrypt(value.encode())
        import base64
        enc = base64.b64encode(sealed).decode()
        body = json.dumps({"encrypted_value": enc, "key_id": pk["key_id"]}).encode()
        req2 = urllib.request.Request(
            f"https://api.github.com/repos/{REPO}/actions/secrets/{name}",
            data=body, method="PUT",
            headers={"Authorization": f"token {pat}", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req2, timeout=60) as r:
            print(f"[secret] {name} 저장 완료 (HTTP {r.status})")
    except Exception as e:
        print(f"[secret] 저장 실패(무시): {e}")


def list_sets():
    return sorted(d for d in os.listdir(os.path.join(ROOT, "sets"))
                  if os.path.isdir(os.path.join(ROOT, "sets", d)))


def pick_next():
    sp = os.path.join(ROOT, "state.json")
    state = {"posted": []}
    if os.path.exists(sp):
        state = json.load(open(sp))
    sets = list_sets()
    remaining = [s for s in sets if s not in state.get("posted", [])]
    if not remaining:                      # 다 돌았으면 순환
        state["posted"] = []
        remaining = sets
    return remaining[0], state, sp


def image_urls(set_id):
    jpgs = sorted(os.path.basename(p) for p in
                  glob.glob(os.path.join(ROOT, "sets", set_id, "card*.jpg")))
    hosts = [
        f"https://cdn.jsdelivr.net/gh/{REPO}@{BRANCH}/sets/{set_id}/{{f}}",
        f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/sets/{set_id}/{{f}}",
    ]
    return jpgs, hosts


def create_item(user_id, token, url):
    return api_post(f"{GRAPH}/{user_id}/media",
                    {"image_url": url, "is_carousel_item": "true",
                     "access_token": token})["id"]


def publish(set_id, token, user_id):
    jpgs, hosts = image_urls(set_id)
    assert 2 <= len(jpgs) <= 10, f"카드는 2~10장이어야 함(현재 {len(jpgs)})"
    caption = open(os.path.join(ROOT, "sets", set_id, "caption.txt"),
                   encoding="utf-8").read().strip()
    children = []
    for f in jpgs:
        last = None
        for host in hosts:                 # jsDelivr 실패 시 raw로 재시도
            url = host.format(f=f)
            try:
                children.append(create_item(user_id, token, url))
                print(f"[item] {f} <- {url.split('//')[1].split('/')[0]}")
                last = None
                break
            except urllib.error.HTTPError as e:
                last = f"{e.code} {e.read().decode()[:200]}"
        if last:
            raise RuntimeError(f"{f} 컨테이너 생성 실패: {last}")
    time.sleep(8)                          # 컨테이너 처리 대기
    car = api_post(f"{GRAPH}/{user_id}/media",
                   {"media_type": "CAROUSEL", "children": ",".join(children),
                    "caption": caption, "access_token": token})["id"]
    time.sleep(8)
    pub = api_post(f"{GRAPH}/{user_id}/media_publish",
                   {"creation_id": car, "access_token": token})
    return pub.get("id")


def main():
    token = os.environ["IG_TOKEN"]
    user_id = os.environ["IG_USER_ID"]
    token, changed = refresh_token(token)
    if changed:
        persist_secret("IG_TOKEN", token)

    set_id, state, sp = pick_next()
    print(f"[post] 세트 선택: {set_id}")
    media_id = publish(set_id, token, user_id)
    print(f"[post] 게시 완료 media_id={media_id}")

    state.setdefault("posted", []).append(set_id)
    state["last"] = {"set": set_id, "media_id": media_id, "sha": os.environ.get("GITHUB_SHA", "")}
    json.dump(state, open(sp, "w"), ensure_ascii=False, indent=1)
    print("[post] state.json 갱신")


if __name__ == "__main__":
    main()
