# GitAutoPush - 방법론 및 아키텍처 문서

## 1. 프로젝트 개요

**GitAutoPush**는 반복적인 Git commit/push 작업을 자동화하는 데스크톱 애플리케이션입니다.
Local LLM(Ollama)을 활용하여 .gitignore 분석, 커밋 메시지 생성, 보안 검사를 수행합니다.

## 2. 기술 스택

| 구분 | 기술 | 선택 이유 |
|------|------|-----------|
| GUI Framework | PyQt6 | 크로스플랫폼, 네이티브 룩앤필, 풍부한 위젯 |
| Git Operations | GitPython + subprocess | GitPython API + fallback CLI |
| Local LLM | Ollama REST API | 로컬 실행, 보안, 무료, 다양한 모델 |
| Database | SQLite3 | 서버리스, 경량, 내장형 |
| Config | JSON | 사람이 읽기 쉬움, 편집 용이 |
| Versioning | SemVer (자동 증가) | 명확한 버전 추적 |

## 3. 아키텍처

```
┌──────────────────────────────────────────────────┐
│                  GitAutoPush App                  │
├──────────────┬──────────────┬────────────────────┤
│   UI Layer   │  Core Logic  │   Data Layer       │
│  (PyQt6)     │  (Python)    │   (SQLite/JSON)    │
├──────────────┼──────────────┼────────────────────┤
│ Dashboard    │ GitManager   │ commit_logs.db     │
│ ProjectPanel │ OllamaClient │ config.json        │
│ LogViewer    │ VersionMgr   │ projects.json      │
│ Settings     │ FileAnalyzer │                    │
└──────────────┴──────┬───────┴────────────────────┘
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
      Git CLI    Ollama API   File System
```

## 4. 핵심 워크플로우

### 4.1 프로젝트 등록 플로우
```
사용자 → [GitHub Repo URL 입력] → [로컬 폴더 선택] → [위치(집/회사) 설정]
       → GitManager.init_or_clone() → config 저장
```

### 4.2 커밋 자동화 플로우
```
[커밋 버튼 클릭]
    → FileAnalyzer.scan_project()          # 프로젝트 파일 스캔
    → OllamaClient.analyze_gitignore()     # LLM이 제외 파일 분석
    → 사용자 확인 (제외 목록 편집 가능)
    → OllamaClient.generate_commit_msg()   # LLM이 커밋 메시지 생성
    → GitManager.stage_and_commit()        # git add + commit
    → GitManager.push()                    # git push
    → VersionManager.increment()           # 버전 증가
    → LogManager.record()                  # 로그 기록
```

### 4.3 LLM 분석 플로우 (.gitignore 생성)
```
프로젝트 폴더 스캔
    → 파일/폴더 목록 추출
    → Ollama에 프롬프트 전송:
       "다음 프로젝트 구조를 분석하여 .gitignore에 포함할 항목을 추천하세요"
    → LLM 응답 파싱
    → 제외 목록 UI에 표시
    → 사용자 확인 후 .gitignore 생성/업데이트
```

## 5. 보안 고려사항

- **Local LLM Only**: 모든 AI 분석은 Ollama를 통해 로컬에서 처리
- **No Cloud API**: 코드/파일 내용이 외부로 전송되지 않음
- **Credential 관리**: Git credentials는 OS keychain 사용
- **민감 파일 탐지**: LLM이 API 키, 비밀번호 등 포함 파일 자동 감지

## 6. 설치 요구사항

```bash
# Python 패키지
pip install PyQt6 gitpython requests

# Ollama 설치 (Linux)
curl -fsSL https://ollama.ai/install.sh | sh

# 추천 모델 (택 1)
ollama pull llama3.1:8b      # 범용 (8GB VRAM)
ollama pull codellama:13b    # 코드 특화 (16GB VRAM)
ollama pull qwen2.5:7b       # 한국어 지원 양호
```

## 7. 데이터베이스 스키마

```sql
CREATE TABLE commit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name TEXT NOT NULL,
    repo_url TEXT,
    commit_hash TEXT,
    commit_message TEXT,
    version TEXT,
    location TEXT CHECK(location IN ('home', 'office')),
    branch TEXT DEFAULT 'main',
    files_changed INTEGER,
    insertions INTEGER,
    deletions INTEGER,
    committed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    pushed_at DATETIME,
    status TEXT CHECK(status IN ('committed', 'pushed', 'failed'))
);
```

## 8. 버전 관리 전략

- 형식: `v{major}.{minor}.{patch}-{build}`
- 자동 증가: 매 커밋마다 patch +1
- 사용자가 major/minor 수동 변경 가능
- 예: v1.0.0-001 → v1.0.1-002 → v1.0.2-003

## 9. 확장 가능성

- **멀티 브랜치 지원**: branch 선택/생성
- **PR 자동 생성**: GitHub API 연동
- **스케줄링**: cron 기반 자동 커밋
- **팀 동기화**: 여러 개발자 로그 통합
- **AI 코드 리뷰**: 커밋 전 LLM 코드 리뷰
