from pathlib import Path


def test_docker_compose_does_not_require_local_env_file():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "env_file:" not in compose
    assert "${SECRET_KEY:-" in compose
    assert "${LLM_API_KEY:-}" in compose
    assert 'LOAD_EMOTION_MODEL_ON_STARTUP: "${LOAD_EMOTION_MODEL_ON_STARTUP:-false}"' in compose


def test_readme_has_no_repository_placeholder_badges():
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "YOUR_ORG" not in readme
    assert "YOUR_REPO" not in readme
    assert "github.com/YOUR" not in readme


def test_demo_asset_documentation_exists():
    asset_doc = Path("docs/assets/README.md")

    assert asset_doc.exists()

    text = asset_doc.read_text(encoding="utf-8")
    for asset_name in [
        "chat.png",
        "admin-chat.png",
        "dashboard.png",
        "demo.gif",
        "architecture.png",
    ]:
        assert asset_name in text