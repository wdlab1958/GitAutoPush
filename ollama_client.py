"""
OllamaClient - 로컬 LLM 통합 모듈
Ollama REST API를 통해 .gitignore 분석 및 커밋 메시지 생성
"""

import json
import os
import requests
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class OllamaConfig:
    base_url: str = "http://localhost:11434"
    model: str = "llama3.1:8b"
    timeout: int = 120
    temperature: float = 0.3


class OllamaClient:
    """Ollama 로컬 LLM 클라이언트"""

    def __init__(self, config: Optional[OllamaConfig] = None):
        self.config = config or OllamaConfig()

    def is_available(self) -> Tuple[bool, str]:
        """Ollama 서버 상태 확인"""
        try:
            resp = requests.get(
                f"{self.config.base_url}/api/tags",
                timeout=5
            )
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                model_names = [m["name"] for m in models]
                if self.config.model in model_names:
                    return True, f"Ollama ready. Model: {self.config.model}"
                # 모델명 부분 매칭
                for name in model_names:
                    if self.config.model.split(":")[0] in name:
                        self.config.model = name
                        return True, f"Ollama ready. Model: {name}"
                return False, (
                    f"Model '{self.config.model}' not found.\n"
                    f"Available: {', '.join(model_names)}\n"
                    f"Run: ollama pull {self.config.model}"
                )
            return False, f"Ollama returned status {resp.status_code}"
        except requests.ConnectionError:
            return False, (
                "Cannot connect to Ollama.\n"
                "Start with: ollama serve\n"
                "Install: curl -fsSL https://ollama.ai/install.sh | sh"
            )
        except Exception as e:
            return False, f"Ollama check failed: {e}"

    def get_available_models(self) -> List[str]:
        """사용 가능한 모델 목록"""
        try:
            resp = requests.get(f"{self.config.base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                return [m["name"] for m in resp.json().get("models", [])]
        except:
            pass
        return []

    def _generate(self, prompt: str, system: str = "") -> Tuple[bool, str]:
        """Ollama API 호출"""
        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": 2048
            }
        }
        if system:
            payload["system"] = system

        try:
            resp = requests.post(
                f"{self.config.base_url}/api/generate",
                json=payload,
                timeout=self.config.timeout
            )
            if resp.status_code == 200:
                data = resp.json()
                return True, data.get("response", "").strip()
            return False, f"API error: {resp.status_code} - {resp.text[:200]}"
        except requests.Timeout:
            return False, "LLM response timed out. Try a smaller model."
        except Exception as e:
            return False, f"LLM request failed: {e}"

    def analyze_gitignore(self, file_tree: str, project_type_hint: str = "") -> Tuple[bool, List[str], str]:
        """
        프로젝트 구조를 분석하여 .gitignore 패턴 추천
        Returns: (success, patterns_list, raw_explanation)
        """
        system = (
            "You are a senior developer expert in Git and project configuration. "
            "Analyze the project structure and recommend .gitignore patterns. "
            "You MUST respond in this exact JSON format only, no other text:\n"
            '{"patterns": ["pattern1", "pattern2"], "reason": "brief explanation"}'
        )

        prompt = f"""Analyze this project file/folder structure and recommend .gitignore patterns.

Consider:
- Build artifacts and compiled files
- IDE/editor configs (.vscode, .idea, etc.)
- OS files (.DS_Store, Thumbs.db)
- Dependencies (node_modules, venv, __pycache__)
- Environment files (.env, .env.local)
- Log files and temp files
- Secrets, API keys, credentials
- Large binary files
- Package lock files that shouldn't be committed
{f'- Project type hint: {project_type_hint}' if project_type_hint else ''}

PROJECT STRUCTURE:
{file_tree}

Respond with JSON only: {{"patterns": [...], "reason": "..."}}"""

        ok, response = self._generate(prompt, system)
        if not ok:
            return False, self._fallback_gitignore_patterns(), response

        # JSON 파싱 시도
        patterns = self._parse_patterns_response(response)
        if patterns:
            return True, patterns, response
        else:
            # 파싱 실패 시 텍스트에서 패턴 추출 시도
            extracted = self._extract_patterns_from_text(response)
            if extracted:
                return True, extracted, response
            return False, self._fallback_gitignore_patterns(), "Failed to parse LLM response"

    def generate_commit_message(self, diff_summary: str, file_list: str,
                                 project_name: str = "", version: str = "") -> Tuple[bool, str]:
        """변경사항 기반 커밋 메시지 자동 생성"""
        system = (
            "You are a Git commit message expert. "
            "Generate a clear, concise commit message following Conventional Commits format. "
            "Respond with ONLY the commit message, nothing else."
        )

        prompt = f"""Generate a Git commit message for these changes:

Project: {project_name or 'Unknown'}
Version: {version or 'N/A'}

Changed files:
{file_list}

Diff summary:
{diff_summary}

Rules:
- Use Conventional Commits format: type(scope): description
- Types: feat, fix, docs, style, refactor, test, chore, build
- Keep subject line under 72 characters
- Add a brief body if many files changed
- Write in English

Respond with ONLY the commit message."""

        ok, response = self._generate(prompt, system)
        if ok:
            # 불필요한 마크다운 제거
            msg = response.strip().strip("`").strip()
            if msg.startswith("```"):
                msg = msg.split("\n", 1)[-1]
            if msg.endswith("```"):
                msg = msg.rsplit("```", 1)[0]
            return True, msg.strip()
        return False, response

    def detect_sensitive_files(self, file_list: str) -> Tuple[bool, List[str], str]:
        """민감한 파일 감지 (보안 분석)"""
        system = (
            "You are a security analyst. "
            "Identify files that may contain sensitive information. "
            "Respond in JSON: {\"sensitive\": [\"file1\", \"file2\"], \"reason\": \"...\"}"
        )

        prompt = f"""Scan these files for potential security risks:

{file_list}

Flag files that might contain:
- API keys or tokens
- Passwords or credentials  
- Private keys or certificates
- Database connection strings
- Environment variables with secrets
- Personal data

Respond with JSON: {{"sensitive": [...], "reason": "..."}}"""

        ok, response = self._generate(prompt, system)
        if not ok:
            return False, [], response

        try:
            # JSON 추출
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(response[start:end])
                return True, data.get("sensitive", []), data.get("reason", "")
        except:
            pass
        return False, [], "Failed to parse security analysis"

    def _parse_patterns_response(self, response: str) -> Optional[List[str]]:
        """LLM 응답에서 JSON 패턴 추출"""
        try:
            # JSON 블록 찾기
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(response[start:end])
                patterns = data.get("patterns", [])
                if isinstance(patterns, list) and patterns:
                    return [str(p).strip() for p in patterns if p]
        except json.JSONDecodeError:
            pass
        return None

    def _extract_patterns_from_text(self, text: str) -> List[str]:
        """텍스트에서 gitignore 패턴 추출 (fallback)"""
        patterns = []
        for line in text.split("\n"):
            line = line.strip().lstrip("- •*").strip()
            line = line.strip("`").strip()
            if line and not line.startswith("#") and len(line) < 100:
                # 패턴처럼 보이는 것만 추출
                if any(c in line for c in [".", "/", "*", "_"]):
                    # 설명 텍스트 제거
                    if " - " in line:
                        line = line.split(" - ")[0].strip()
                    if " #" in line:
                        line = line.split(" #")[0].strip()
                    if line and not " " in line:
                        patterns.append(line)
        return patterns

    def _fallback_gitignore_patterns(self) -> List[str]:
        """LLM 실패 시 기본 .gitignore 패턴"""
        return [
            # Python
            "__pycache__/", "*.py[cod]", "*.pyo", "*.egg-info/",
            "dist/", "build/", "*.egg", "venv/", ".venv/", "env/",
            # Node.js
            "node_modules/", "npm-debug.log*", "yarn-error.log*",
            # IDE
            ".vscode/", ".idea/", "*.swp", "*.swo", "*~",
            # OS
            ".DS_Store", "Thumbs.db", "desktop.ini",
            # Environment
            ".env", ".env.local", ".env.*.local",
            # Logs
            "*.log", "logs/",
            # Build
            "*.o", "*.so", "*.dylib",
            # Temp
            "tmp/", "temp/", ".tmp/",
        ]

    def scan_project_tree(self, project_path: str, max_depth: int = 3,
                          max_items: int = 200) -> str:
        """프로젝트 디렉토리 트리를 문자열로 생성"""
        tree_lines = []
        item_count = 0

        # 기본적으로 무시할 대형 디렉토리
        always_skip = {
            "node_modules", ".git", "__pycache__", "venv", ".venv",
            "env", ".env", ".tox", ".pytest_cache", ".mypy_cache",
            "dist", "build", ".next", ".nuxt", "coverage",
            ".gradle", ".m2", "target"
        }

        for root, dirs, files in os.walk(project_path):
            # 깊이 제한
            depth = root.replace(project_path, "").count(os.sep)
            if depth >= max_depth:
                dirs[:] = []
                continue

            # 대형 디렉토리 건너뛰기
            dirs[:] = [d for d in dirs if d not in always_skip and not d.startswith(".")]

            indent = "  " * depth
            folder_name = os.path.basename(root) or os.path.basename(project_path)
            tree_lines.append(f"{indent}📁 {folder_name}/")
            item_count += 1

            for f in sorted(files)[:50]:  # 폴더당 최대 50파일
                if item_count >= max_items:
                    tree_lines.append(f"{indent}  ... (truncated)")
                    return "\n".join(tree_lines)
                tree_lines.append(f"{indent}  📄 {f}")
                item_count += 1

        return "\n".join(tree_lines)
