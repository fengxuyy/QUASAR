from pathlib import Path

from src.rag.docs_downloader import REPO_CONFIGS
from src.rag.query import LIBRARY_NAME_MAP, VALID_LIBRARIES_MSG


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_repo_file(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text()


def test_rag_excludes_removed_chemistry_tools():
    repo_targets = {config["target"] for config in REPO_CONFIGS}

    for removed in ("nwchem", "rdkit"):
        assert removed not in repo_targets

    for removed in ("nwchem", "rdkit"):
        assert removed not in LIBRARY_NAME_MAP
        assert f'"{removed}"' not in VALID_LIBRARIES_MSG


def test_runtime_metadata_excludes_removed_chemistry_stack():
    requirements_lines = {
        line.strip()
        for line in _read_repo_file("requirements.txt").splitlines()
        if line.strip()
    }
    operator_source = _read_repo_file("src/agents/operator.py").lower()
    strategist_source = _read_repo_file("src/agents/strategist.py").lower()
    execution_source = _read_repo_file("src/tools/execution.py").lower()

    assert "rdkit" not in requirements_lines

    for keyword in ("xtb", "nwchem", "rdkit"):
        assert keyword not in operator_source
        assert keyword not in strategist_source

    assert "rdkit" not in execution_source
    assert "nwchem" not in execution_source
    assert "xtb" not in execution_source


def test_dockerfiles_exclude_xtb_and_nwchem():
    amd64 = _read_repo_file("docker/Dockerfile.amd64").lower()
    arm64 = _read_repo_file("docker/Dockerfile.arm64").lower()
    cuda = _read_repo_file("docker/Dockerfile.cuda").lower()
    rocm = _read_repo_file("docker/Dockerfile.rocm").lower()

    for dockerfile in (amd64, arm64, cuda, rocm):
        assert "xtb" not in dockerfile

    for dockerfile in (amd64, arm64):
        assert "nwchem" not in dockerfile
