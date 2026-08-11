from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_NAMES = [
    "verification-before-completion",
    "context-completeness-audit",
    "test-driven-development",
    "systematic-debugging",
    "receiving-code-review",
    "kb-lookup",
    "code-documentation",
    "requesting-code-review",
    "coding-principles",
    "session-report",
]


def _write_skill_stubs(root: Path) -> None:
    for name in SKILL_NAMES:
        skill_dir = root / ".pi" / "skills" / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: stub for tests\n---\n\nStub content for {name}.\n",
            encoding="utf-8",
        )


def _write_task_repo(root: Path) -> None:
    (root / "tasks").mkdir(parents=True, exist_ok=True)
    (root / "tasks" / "T-001.md").write_text(
        "---\n"
        "id: T-001\n"
        "title: Resume after checkpoint\n"
        "status: todo\n"
        "trace_exempt: true\n"
        "trace_exempt_reason: tooling task\n"
        "dod:\n"
        "  - passes\n"
        "---\n"
        "Body\n",
        encoding="utf-8",
    )
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "answer.py").write_text("ANSWER = 41\n", encoding="utf-8")
    (root / ".factory").mkdir(parents=True, exist_ok=True)
    (root / ".factory" / "factory.yaml").write_text(
        "gates:\n"
        "  unit:\n"
        "    - { cmd: \"{python} -c \\\"pass\\\"\" }\n"
        "  sim:\n"
        "    - { cmd: \"{python} scripts/gate.py sim\" }\n"
        "  integration:\n"
        "    - { cmd: \"{python} -c \\\"pass\\\"\" }\n"
        "  full:\n"
        "    - { cmd: \"{python} -c \\\"pass\\\"\" }\n",
        encoding="utf-8",
    )
    (root / ".gitignore").write_text("sessions/\n", encoding="utf-8")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _write_tools(root: Path) -> tuple[Path, Path, Path, Path]:
    tools = root / "tools"
    bin_dir = tools / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    log_dir = tools / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    release_file = tools / "release-gate"

    pi_impl = tools / "pi_impl.py"
    pi_impl.write_text(
        "from __future__ import annotations\n"
        "import json\n"
        "import os\n"
        "import re\n"
        "import sys\n"
        "import time\n"
        "from pathlib import Path\n"
        "\n"
        "def _prompt(argv):\n"
        "    idx = argv.index('-p')\n"
        "    raw = argv[idx + 1]\n"
        "    if raw.startswith('@'):\n"
        "        return Path(raw[1:]).read_text(encoding='utf-8')\n"
        "    return raw\n"
        "\n"
        "def _append(path: Path, record: dict) -> None:\n"
        "    path.parent.mkdir(parents=True, exist_ok=True)\n"
        "    with path.open('a', encoding='utf-8') as handle:\n"
        "        handle.write(json.dumps(record, sort_keys=True) + '\\n')\n"
        "\n"
        "def _role(prompt: str) -> str:\n"
        "    match = re.search(r'^# Role: (.+)$', prompt, re.MULTILINE)\n"
        "    return match.group(1) if match else 'unknown'\n"
        "\n"
        "def _task_id(prompt: str) -> str:\n"
        "    match = re.search(r'^## Task (\\S+):', prompt, re.MULTILINE)\n"
        "    return match.group(1) if match else 'T-001'\n"
        "\n"
        "def _emit(payload: dict) -> None:\n"
        "    text = '```json\\n' + json.dumps(payload, sort_keys=True) + '\\n```'\n"
        "    print(json.dumps({'type': 'message_end', 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': text}]}}))\n"
        "\n"
        "def main(argv: list[str]) -> int:\n"
        "    prompt = _prompt(argv)\n"
        "    role = _role(prompt)\n"
        "    phase = os.environ.get('FAKE_PI_PHASE', 'initial')\n"
        "    log_path = Path(os.environ['FAKE_PI_LOG'])\n"
        "    session_id = f'{role}-{time.time_ns()}'\n"
        "    _append(log_path, {'role': role, 'phase': phase, 'session_id': session_id})\n"
        "    print(json.dumps({'type': 'session', 'id': session_id}))\n"
        "    sys.stdout.flush()\n"
        "    if role == 'context-gatherer':\n"
        "        _emit({'task_id': _task_id(prompt), 'generated_by': 'context-gatherer', 'generated_at': '2026-08-07T12:00:00Z', 'coherence': {'checks': []}, 'context': {'task': 'tasks/T-001.md', 'source_files': [], 'skills': []}, 'reject': None})\n"
        "    elif role == 'dev':\n"
        "        _emit({'done': True})\n"
        "    elif role == 'review':\n"
        "        _emit({'dod_met': True, 'findings': [], 'confidence': 'good', 'verify': []})\n"
        "    elif role == 'session-review':\n"
        "        _emit({'summary': 'ok'})\n"
        "    else:\n"
        "        _emit({})\n"
        "    return 0\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main(sys.argv))\n",
        encoding="utf-8",
    )
    (bin_dir / "pi").write_text(
        "#!/usr/bin/env sh\nexec \"${PYTHON:-python3}\" \"$(dirname \"$0\")/../pi_impl.py\" \"$@\"\n",
        encoding="utf-8",
    )
    os.chmod(bin_dir / "pi", 0o755)
    (bin_dir / "pi.cmd").write_text(
        "@echo off\r\npython \"%~dp0\\..\\pi_impl.py\" %*\r\n",
        encoding="utf-8",
    )
    gate_impl = tools / "scripts"
    gate_impl.mkdir(parents=True, exist_ok=True)
    (gate_impl / "gate.py").write_text(
        "from __future__ import annotations\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "import time\n"
        "from pathlib import Path\n"
        "\n"
        "def _append(path: Path, record: dict) -> None:\n"
        "    path.parent.mkdir(parents=True, exist_ok=True)\n"
        "    with path.open('a', encoding='utf-8') as handle:\n"
        "        handle.write(json.dumps(record, sort_keys=True) + '\\n')\n"
        "\n"
        "def main(argv: list[str]) -> int:\n"
        "    gate = argv[1] if len(argv) > 1 else 'unknown'\n"
        "    phase = os.environ.get('FAKE_GATE_PHASE', 'initial')\n"
        "    log_path = Path(os.environ['FAKE_GATE_LOG'])\n"
        "    _append(log_path, {'gate': gate, 'phase': phase})\n"
        "    if gate == 'sim' and phase == 'initial':\n"
        "        release = Path(os.environ['FAKE_GATE_RELEASE_FILE'])\n"
        "        while not release.exists():\n"
        "            time.sleep(0.1)\n"
        "    return 0\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main(sys.argv))\n",
        encoding="utf-8",
    )
    return bin_dir, log_dir, release_file, gate_impl


def _env_with_tools(bin_dir: Path, log_file: Path, gate_log: Path, release_file: Path, phase: str) -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env["PYTHONPATH"] = str(REPO_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env["FAKE_PI_LOG"] = str(log_file)
    env["FAKE_PI_PHASE"] = phase
    env["FAKE_GATE_LOG"] = str(gate_log)
    env["FAKE_GATE_PHASE"] = phase
    env["FAKE_GATE_RELEASE_FILE"] = str(release_file)
    return env


def _wait_for_checkpoint(repo: Path, timeout: float = 30.0) -> tuple[str, dict]:
    deadline = time.time() + timeout
    run_root = repo / "sessions" / ".factory-runs" / "by-session"
    while time.time() < deadline:
        for checkpoint_path in sorted(run_root.glob("*/checkpoint.json")):
            data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            if data.get("node") == "validation":
                return checkpoint_path.parent.name, data
        time.sleep(0.1)
    raise AssertionError("timed out waiting for a validation checkpoint")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _terminate_tree(proc: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, text=True, check=True)
        return
    os.killpg(proc.pid, signal.SIGKILL)


def test_kill_resume_discovery_and_resume_without_conversation_history(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_skill_stubs(repo)
    _write_task_repo(repo)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")

    bin_dir, log_dir, release_file, gate_scripts_dir = _write_tools(tmp_path)
    (repo / "scripts").mkdir(parents=True, exist_ok=True)
    (repo / "scripts" / "gate.py").write_text(
        (gate_scripts_dir / "gate.py").read_text(encoding="utf-8"), encoding="utf-8"
    )
    initial_pi_log = log_dir / "pi-initial.jsonl"
    initial_gate_log = log_dir / "gate-initial.jsonl"
    resume_pi_log = log_dir / "pi-resume.jsonl"
    resume_gate_log = log_dir / "gate-resume.jsonl"
    run_cmd = [
        "uv",
        "run",
        "--project",
        str(REPO_ROOT),
        "--directory",
        str(repo),
        "python",
        "-m",
        "factory.orchestrator",
        "run",
        "--repo",
        str(repo),
        "--task",
        "T-001",
        "--auto",
    ]

    initial_env = _env_with_tools(bin_dir, initial_pi_log, initial_gate_log, release_file, "initial")
    initial_env["PATH"] = str(gate_scripts_dir) + os.pathsep + initial_env["PATH"]
    popen_kwargs = {
        "cwd": repo,
        "env": initial_env,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True
    proc = subprocess.Popen(run_cmd, **popen_kwargs)
    run_id, checkpoint = _wait_for_checkpoint(repo)
    assert checkpoint["node"] == "validation"
    assert [item["node"] for item in checkpoint["completed"]] == ["context-gather", "dev"]

    inspect = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(REPO_ROOT),
            "--directory",
            str(repo),
            "python",
            "-m",
            "factory.orchestrator",
            "run-state",
            "inspect",
            run_id,
            "--repo",
            str(repo),
            "--json",
        ],
        cwd=repo,
        env=initial_env,
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(inspect.stdout)
    assert payload["checkpoint"]["node"] == "validation"
    assert payload["assessment"]["state"] == "resumable"

    _terminate_tree(proc)
    proc.wait(timeout=30)
    assert proc.returncode is not None

    resume_env = _env_with_tools(bin_dir, resume_pi_log, resume_gate_log, release_file, "resume")
    resume_env["PATH"] = str(gate_scripts_dir) + os.pathsep + resume_env["PATH"]
    resumed = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(REPO_ROOT),
            "--directory",
            str(repo),
            "python",
            "-m",
            "factory.orchestrator",
            "run-state",
            "resume",
            run_id,
            "--repo",
            str(repo),
        ],
        cwd=repo,
        env=resume_env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "resumed session written" in resumed.stderr

    complete = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(REPO_ROOT),
            "--directory",
            str(repo),
            "python",
            "-m",
            "factory.orchestrator",
            "run-state",
            "inspect",
            run_id,
            "--repo",
            str(repo),
            "--json",
        ],
        cwd=repo,
        env=resume_env,
        capture_output=True,
        text=True,
        check=True,
    )
    complete_payload = json.loads(complete.stdout)
    assert complete_payload["assessment"]["state"] == "complete"

    assert [entry["role"] for entry in _read_jsonl(initial_pi_log)] == ["context-gatherer", "dev"]
    assert [entry["role"] for entry in _read_jsonl(resume_pi_log)] == ["review", "session-review"]
    assert [entry["gate"] for entry in _read_jsonl(initial_gate_log)] == ["sim"]
    assert [entry["gate"] for entry in _read_jsonl(resume_gate_log)] == ["sim"]
