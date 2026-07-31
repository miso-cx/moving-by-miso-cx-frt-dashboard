# 미소방문 FRT 대시보드 — 팀 배포 가이드

팀원이 **브라우저 URL 하나**로 대시보드를 보려면, 아래 구조로 배포합니다.

## 구조 (한 줄)

```
[내 PC] MySQL 조회 → HTML 생성 → Netlify 업로드  →  [팀] https://xxx.netlify.app
         ↑ 30분마다 자동 (선택)
```

- **DB는 내 PC(또는 VPN)에서만** 조회 가능 → 빌드는 로컬에서 실행
- **배포물은 정적 HTML** → Netlify/GitHub Pages 등 어디든 올릴 수 있음
- 팀원 PC에 Python·MySQL 불필요

---

## 1단계: 지금 로컬에서 확인

```powershell
cd "C:\Users\misop\OneDrive\바탕 화면\miso_automation"
python tools/build_frt_ops_dashboard.py
python tools/prepare_frt_publish.py
```

브라우저에서 열기:

`docs\frt\_publish\index.html`

---

## 2단계: Netlify 계정 (추천, 처음 배포용)

1. [https://app.netlify.com](https://app.netlify.com) 가입 (GitHub/Google 로그인 가능)
2. **User settings → Applications → Personal access tokens** → 토큰 생성
3. PowerShell에 토큰 저장 (세션용):

```powershell
$env:NETLIFY_AUTH_TOKEN = "여기에_토큰"
```

4. Netlify CLI 설치 (Node.js 필요):

```powershell
npm install -g netlify-cli
```

5. **첫 배포**:

```powershell
python tools/deploy_frt_dashboard.py --build --deploy
```

출력에 `Website URL` / `Live URL` 이 나옵니다. **이 주소를 팀에 공유**하면 됩니다.

6. **같은 사이트에 다시 올릴 때** (두 번째부터):

Netlify 대시보드 → Site → Site configuration → **Site ID** 복사 후:

```powershell
$env:NETLIFY_SITE_ID = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
python tools/deploy_frt_dashboard.py --build --deploy
```

---

## 3단계: 30분마다 자동 갱신 + 배포 (선택)

로컬 30분 갱신(`MisoAutomation_FRT_OpsHourly`) **뒤에** Netlify 업로드를 붙입니다.

PowerShell:

```powershell
$env:NETLIFY_AUTH_TOKEN = "토큰"
$env:NETLIFY_SITE_ID = "사이트ID"
$env:FRT_AUTO_DEPLOY = "1"
```

Windows 작업 등록:

```powershell
powershell -ExecutionPolicy Bypass -File tools\register_frt_hourly_task.ps1
```

`FRT_AUTO_DEPLOY=1` 이고 토큰이 있으면, 갱신 성공 후 자동으로 `--deploy` 합니다.

---

## 대안: GitHub Pages (회사 GitHub 쓰는 경우)

1. 저장소 생성 후 `docs/frt/_publish` 내용을 `gh-pages` 브랜치에 push
2. Settings → Pages → branch `gh-pages` / root

자동화는 `deploy_frt_dashboard.py` 대신 git push 스크립트를 추가하면 됩니다. (DB는 여전히 로컬 빌드)

---

## 보안 참고

- 대시보드에는 **집계 FRT·채널 일부**가 들어갑니다. **사내용**으로만 URL 공유하세요.
- Netlify 사이트는 기본 공개 URL입니다. 필요하면 Netlify **Password protection**(유료) 또는 회사 VPN 뒤 호스팅을 검토하세요.
- `NETLIFY_AUTH_TOKEN`, DB 비밀번호는 **Git에 커밋하지 마세요.**

---

## 문제 해결

| 증상 | 확인 |
|------|------|
| 팀 URL 404 | `index.html` 이 `_publish` 루트에 있는지 |
| 데이터 오래됨 | 내 PC 작업 스케줄러 실행 중인지, `docs/frt/refresh_status.json` |
| deploy 실패 | `NETLIFY_AUTH_TOKEN`, `netlify-cli` 설치 |
| build 실패 | MySQL 연결 (`tools/MYSQL_CONNECTION.txt`) |

---

## 명령 요약

| 목적 | 명령 |
|------|------|
| HTML만 재생성 | `python tools/build_frt_ops_dashboard.py` |
| 배포 폴더 준비 | `python tools/prepare_frt_publish.py` |
| 빌드 + 배포 | `python tools/deploy_frt_dashboard.py --build --deploy` |
| 갱신 상태 | `docs/frt/refresh_status.json` |
