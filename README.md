# 🚀 GitAutoPush

**Git Commit & Push 자동화 데스크톱 도구 — Local LLM (Ollama) 기반**

집과 회사에서 반복적인 Git CLI 작업을 UI/UX 기반으로 자동화합니다.

---

## 📸 스크린샷

### Dashboard
![Dashboard](screenshots/01_dashboard.png)

---

## ✨ 주요 기능

| 기능 | 설명 |
|------|------|
| **원클릭 Commit & Push** | 버튼 하나로 stage → commit → push 자동 처리 |
| **LLM .gitignore 분석** | Ollama가 프로젝트 구조를 분석하여 제외 파일 자동 추천 |
| **AI 커밋 메시지 생성** | 변경사항을 분석하여 Conventional Commits 형식 메시지 자동 생성 |
| **버전 자동 증가** | 매 커밋마다 SemVer 버전 자동 관리 (v1.0.0-001 → v1.0.1-002) |
| **위치 기반 로그** | 🏠 집 / 🏢 회사 구분하여 커밋 이력 기록 |
| **GitHub PAT 인증** | Settings에서 Personal Access Token 등록, HTTPS push 시 자동 적용 |
| **보안 우선** | 모든 AI 분석은 로컬 Ollama에서 수행 (데이터 유출 없음) |
| **로그 내보내기** | CSV 형식으로 커밋 이력 내보내기 |

---

## 📦 설치

### 사전 요구사항

```bash
# Python 3.10+
python3 --version

# Git
git --version

# Ollama 설치
curl -fsSL https://ollama.ai/install.sh | sh

# LLM 모델 다운로드 (택 1)
ollama pull llama3.1:8b         # 범용 (권장, 8GB VRAM)
ollama pull qwen2.5:7b          # 한국어 지원 양호
ollama pull qwen2.5-coder:7b    # 코드 특화
```

### 프로젝트 설치

```bash
cd git-autopush

# 자동 설정 & 실행
chmod +x run.sh
./run.sh

# 또는 수동 설치
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

---

## 🖥️ 사용법

### 1. 프로젝트 등록
1. **➕ New Project** 클릭
2. 프로젝트 이름, GitHub URL, 로컬 폴더 경로 입력
3. 현재 위치 (Home/Office) 선택

### 2. GitHub PAT 설정
1. **⚙️ Settings** 탭 이동
2. **GitHub PAT** 필드에 Personal Access Token 입력
3. **💾 Save Settings** 클릭
4. 저장 후 재시작 시 `••••••••`로 마스킹 표시
5. HTTPS remote URL 사용 시 push에 자동 적용 (SSH는 무관)

### 3. .gitignore 분석 (LLM)
1. **🧠 Analyze .gitignore** 클릭
2. Ollama가 프로젝트 구조를 분석하여 제외 패턴 추천
3. 편집기에서 확인/수정 후 적용

### 4. Commit & Push
1. 커밋 메시지 입력 (비워두면 LLM이 자동 생성)
2. **🚀 Commit & Push** 클릭
3. 자동으로: stage → commit → push → 버전 증가 → 로그 기록

### 5. 로그 확인
- **📜 Commit Log** 탭에서 전체 이력 확인
- 프로젝트별, 위치별 필터링
- CSV 내보내기 가능

---

## 📁 프로젝트 구조

```
git-autopush/
├── main.py                  # 메인 앱 (PyQt6 GUI)
├── run.sh                   # 자동 설정 & 실행 스크립트
├── requirements.txt         # Python 의존성
├── README.md               # 이 문서
├── METHODOLOGY.md          # 방법론 및 아키텍처 문서
├── screenshots/            # 앱 스크린샷
│   └── 01_dashboard.png
├── core/
│   ├── __init__.py
│   ├── git_manager.py      # Git 작업 자동화
│   ├── ollama_client.py    # Ollama LLM 클라이언트
│   ├── version_manager.py  # 버전 관리 & 로그 DB
│   └── config_manager.py   # 설정 관리
└── ~.gitautopush/           # 앱 데이터 (홈 디렉토리)
    ├── config.json          # 앱 설정
    ├── projects.json        # 프로젝트 목록
    └── commit_logs.db       # SQLite 커밋 로그
```

---

## ⚙️ 설정

### Ollama 모델 추천

| 모델 | VRAM | 특징 |
|------|------|------|
| `llama3.1:8b` | 8GB | 범용, 안정적 (기본) |
| `qwen2.5:7b` | 8GB | 한국어 지원 우수 |
| `qwen2.5-coder:7b` | 8GB | 코드 분석 특화 |
| `codellama:13b` | 16GB | 코드 특화, 고품질 |
| `deepseek-coder-v2:16b` | 20GB | 최고 코드 품질 |

### Git 인증 설정

**방법 1: GitHub PAT (앱 내 설정 - 권장)**

1. GitHub → Settings → Developer settings → Personal access tokens → Generate new token
2. `repo` 권한 체크 후 토큰 생성
3. 앱의 **⚙️ Settings** 탭 → **GitHub PAT** 필드에 붙여넣기 → Save

**방법 2: CLI 직접 설정**

```bash
# HTTPS 방식
git config --global credential.helper store
# 첫 push 시 username + PAT 입력

# SSH 방식
ssh-keygen -t ed25519 -C "your@email.com"
# ~/.ssh/id_ed25519.pub 내용을 GitHub Settings > SSH Keys에 추가
```

---

## 🔒 보안

- **Zero Cloud API**: 모든 AI 분석은 Ollama 로컬 서버에서 처리
- **No Data Leakage**: 코드와 파일 내용이 외부로 전송되지 않음
- **Local Storage Only**: 설정/로그는 `~/.gitautopush/`에 로컬 저장
- **PAT 마스킹**: GitHub PAT는 설정 파일에 저장되며, UI에서는 마스킹 처리
- **민감 파일 감지**: LLM이 API 키, 비밀번호 등 포함 파일 자동 탐지

---

## 📄 License

MIT License
