from pathlib import Path

from src.rag.docs_downloader import REPO_CONFIGS
from src.rag.query import LIBRARY_NAME_MAP, VALID_LIBRARIES_MSG


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_repo_file(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text()


def test_rag_configs_include_rdkit_and_exclude_orca_docs():
    repo_targets = {config["target"]: config for config in REPO_CONFIGS}

    assert "nwchem" not in repo_targets
    assert "orca" not in repo_targets

    assert "rdkit" in repo_targets
    assert repo_targets["rdkit"]["sparse_paths"] == ["Docs/Book", "Docs/Notebooks", "rdkit"]

    assert "nwchem" not in LIBRARY_NAME_MAP
    assert "orca" not in LIBRARY_NAME_MAP
    assert LIBRARY_NAME_MAP["rdkit"] == "rdkit"
    assert '"nwchem"' not in VALID_LIBRARIES_MSG
    assert '"orca"' not in VALID_LIBRARIES_MSG
    assert '"rdkit"' in VALID_LIBRARIES_MSG


def test_runtime_metadata_mentions_restored_chemistry_stack():
    requirements_lines = {
        line.strip()
        for line in _read_repo_file("requirements.txt").splitlines()
        if line.strip()
    }
    prompt_source = _read_repo_file("src/prompting/builders.py").lower()
    execution_source = _read_repo_file("src/tools/execution.py").lower()

    assert "rdkit" in requirements_lines

    for keyword in ("xtb", "orca", "rdkit"):
        assert keyword in prompt_source

    assert "rdkit" in execution_source
    assert "orca" in execution_source
    assert "xtb" in execution_source


def test_dockerfiles_install_xtb_and_local_orca_packages():
    amd64 = _read_repo_file("docker/Dockerfile.amd64").lower()
    arm64 = _read_repo_file("docker/Dockerfile.arm64").lower()
    cuda = _read_repo_file("docker/Dockerfile.cuda").lower()
    rocm = _read_repo_file("docker/Dockerfile.rocm").lower()

    for dockerfile in (amd64, arm64, cuda, rocm):
        assert "xtb" in dockerfile
        assert "/opt/orca" in dockerfile
        assert "apt-get install -y --no-install-recommends binutils nwchem" not in dockerfile

    for dockerfile in (amd64, cuda, rocm):
        assert "orca_6_1_1_linux_x86-64_shared_openmpi418_nodmrg.tar.xz" in dockerfile

    assert "orca_6_1_1_linux_arm64_shared_openmpi418.tar.xz" in arm64
