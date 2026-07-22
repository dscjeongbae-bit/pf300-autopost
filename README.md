# PF-300 카드뉴스 자동 게시

@ilovewaterwel 인스타그램에 카드뉴스 캐러셀을 **월·수·금 오전 11시(KST)** 자동 게시합니다.

## 구조
- `sets/<세트>/card*.jpg` — 게시할 카드 이미지(1080×1350), `caption.txt` — 캡션
- `post.py` — 게시 스크립트(토큰 갱신 → 다음 세트 선택 → 캐러셀 게시 → state 기록)
- `.github/workflows/post.yml` — 스케줄 + 수동 실행 버튼
- `state.json` — 게시 완료된 세트 기록(다 돌면 처음부터 순환)

## Secrets (Settings → Secrets and variables → Actions)
| 이름 | 값 |
|---|---|
| `IG_TOKEN` | 인스타그램 장기 액세스 토큰 |
| `IG_USER_ID` | 인스타그램 계정 ID |
| `GH_PAT` | (선택) 토큰 자동 갱신 저장용 PAT(repo 권한) |

## 새 카드 추가
`sets/` 아래에 `NN_이름/` 폴더를 만들고 `card1.jpg`~`cardN.jpg` + `caption.txt`를 넣으면 다음 순번에 자동 게시됩니다.

## 수동 테스트
Actions 탭 → "PF-300 카드뉴스 자동 게시" → Run workflow.
