# 미소방문 FRT 대시보드 — GitHub Pages 배포

## 구조

```
[내 PC] MySQL → HTML 빌드 → gh-pages 브랜치 push → GitHub Pages URL
```

- **main** 브랜치: 소스 코드 (private)
- **gh-pages** 브랜치: `index.html` 만 (자동 생성·push, 직접 수정 안 함)

---

## 처음 한 번 (약 15분)

### 1. GitHub에서 private 저장소 생성

1. [https://github.com/new](https://github.com/new)
2. Repository name 예: `miso-frt-dashboard`
3. **Private** 선택 → Create repository

### 2. 로컬 git 연결

PowerShell:

```powershell
cd "C:\Users\misop\OneDrive\바탕 화면\miso_automation"

git init
git branch -M main
git remote add origin https://github.com/내아이디/miso-frt-dashboard.git
```

> `db_config.py`에 DB 비밀번호가 있으면 **private 저장소**만 사용하세요.

### 3. main 브랜치 첫 push (소스 보관, 선택)

```powershell
git add .
git commit -m "FRT dashboard source"
git push -u origin main
```

### 4. 대시보드 빌드 + GitHub Pages 배포

```powershell
python tools/deploy_frt_github.py --build --deploy
```

### 5. GitHub Pages 켜기

저장소 → **Settings** → **Pages**

| 항목 | 값 |
|------|-----|
| Source | Deploy from a branch |
| Branch | **gh-pages** / **/ (root)** |

1~2분 후 접속:

`https://내아이디.github.io/miso-frt-dashboard/`

이 URL을 팀에 공유합니다.

---

## 이후 갱신

데이터만 최신화해서 다시 올리기:

```powershell
python tools/deploy_frt_github.py --build --deploy
```

### 30분마다 자동 (선택)

```powershell
$env:FRT_AUTO_DEPLOY = "1"
$env:FRT_DEPLOY_TARGET = "github"
powershell -ExecutionPolicy Bypass -File tools\register_frt_hourly_task.ps1
```

---

## 회사 저장소로 옮길 때

1. 회사 org에 새 private repo 생성
2. `git remote set-url origin https://github.com/회사org/새repo.git`
3. `git push -u origin main`
4. `python tools/deploy_frt_github.py --deploy`
5. Pages 설정 동일 (gh-pages / root)

---

## 문제 해결

| 증상 | 해결 |
|------|------|
| `git 저장소가 없습니다` | `git init` + `remote add` |
| push 인증 실패 | GitHub Personal Access Token 또는 SSH 키 설정 |
| 404 | Pages 설정에서 gh-pages 브랜치 확인 |
| 빈 페이지 | `deploy_frt_github.py --build --deploy` 재실행 |

Netlify 등 다른 방식: `docs/frt/DEPLOY.md` 참고
