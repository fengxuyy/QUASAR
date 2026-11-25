"""
Documentation downloader for QUASAR-CHEM.

Downloads documentation repositories (ASE, pymatgen, MACE, RASPA3, Q-E, LAMMPS, RDKit)
to the workspace for reference and example access.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

# Documentation folder name
DOCS_FOLDER_NAME = "docs"

# Import debug logger
try:
    from ..debug_logger import log_custom
    _HAS_DEBUG_LOGGER = True
except ImportError:
    _HAS_DEBUG_LOGGER = False


def _log(message: str, data: dict = None):
    """Log a message to debug log."""
    if _HAS_DEBUG_LOGGER:
        log_custom("RAG", message, data or {})


# Repository configurations.
# required_paths: relative to the cloned target; used to detect incomplete sparse clones.
REPO_CONFIGS = [
    {
        "name": "ASE",
        "url": "https://gitlab.com/ase/ase.git",
        "target": "ase",
        "sparse_paths": ["doc", "ase", "examples"],
        "required_paths": ["ase", "doc"],
        "timeout": 300,
    },
    {
        "name": "pymatgen",
        "url": "https://github.com/materialsproject/pymatgen.git",
        "target": "pymatgen",
        "sparse_paths": ["src", "docs", "README.md"],
        "required_paths": ["src", "docs"],
        "timeout": 300,
    },
    {
        "name": "MACE",
        "url": "https://github.com/ACEsuit/mace.git",
        "target": "mace",
        "sparse_paths": ["mace", "README.md"],
        "required_paths": ["mace"],
        "timeout": 300,
    },
    {
        "name": "RASPA3",
        "url": "https://github.com/iRASPA/RASPA3.git",
        "target": "RASPA3",
        "sparse_paths": ["docs", "examples"],
        "required_paths": ["docs", "examples"],
        "timeout": 300,
    },
    {
        "name": "Quantum ESPRESSO",
        "url": "https://gitlab.com/QEF/q-e.git",
        "alt_url": "https://gitlab.com/QEF/q-e",
        "target": "q-e",
        "sparse_paths": [
            "Doc",
            "PW/Doc",
            "PW/examples",
            "PP/Doc",
            "PP/examples",
            "PHonon/Doc",
            "PHonon/examples",
            "README.md",
        ],
        "required_paths": ["Doc", "PP"],
        "timeout": 600,
    },
    {
        "name": "LAMMPS",
        "url": "https://github.com/lammps/lammps.git",
        "target": "lammps",
        # Prefer top-level cones so git sparse-checkout (cone mode) is reliable.
        "sparse_paths": ["doc", "examples", "README", "LICENSE"],
        "required_paths": ["doc/src", "examples"],
        "timeout": 900,
    },
    {
        "name": "RDKit",
        "url": "https://github.com/rdkit/rdkit.git",
        "target": "rdkit",
        "sparse_paths": ["Docs/Book", "Docs/Notebooks", "rdkit"],
        "required_paths": ["Docs", "rdkit"],
        "timeout": 600,
    },
]

# Pseudopotential packs for Quantum ESPRESSO.
# Materials Cloud answers 302 → rgw.cscs.ch; downloads must follow redirects and
# tolerate slow object-store links. Optional local mirror via QUASAR_PSEUDO_MIRROR.
QE_PSEUDO_PACKS = [
    {
        "name": "SSSP_1.3.0_PBE_efficiency",
        "family": "SSSP",
        "filename": "SSSP_1.3.0_PBE_efficiency.tar.gz",
        "urls": [
            "https://archive.materialscloud.org/api/records/rcyfm-68h65/files/SSSP_1.3.0_PBE_efficiency.tar.gz/content",
            "https://archive.materialscloud.org/records/rcyfm-68h65/files/SSSP_1.3.0_PBE_efficiency.tar.gz",
        ],
        "min_upf": 80,
        "min_bytes": 20_000_000,
    },
    {
        "name": "SSSP_1.3.0_PBE_precision",
        "family": "SSSP",
        "filename": "SSSP_1.3.0_PBE_precision.tar.gz",
        "urls": [
            "https://archive.materialscloud.org/api/records/rcyfm-68h65/files/SSSP_1.3.0_PBE_precision.tar.gz/content",
            "https://archive.materialscloud.org/records/rcyfm-68h65/files/SSSP_1.3.0_PBE_precision.tar.gz",
        ],
        "min_upf": 80,
        "min_bytes": 20_000_000,
    },
    {
        "name": "nc-sr-05_pbe_standard_upf",
        "family": "PseudoDojo",
        "filename": "nc-sr-05_pbe_standard_upf.tgz",
        "urls": ["https://www.pseudo-dojo.org/pseudos/nc-sr-05_pbe_standard_upf.tgz"],
        "min_upf": 50,
        "min_bytes": 1_000_000,
    },
    {
        "name": "nc-fr-04_pbe_standard_upf",
        "family": "PseudoDojo",
        "filename": "nc-fr-04_pbe_standard_upf.tgz",
        "urls": ["https://www.pseudo-dojo.org/pseudos/nc-fr-04_pbe_standard_upf.tgz"],
        "min_upf": 50,
        "min_bytes": 1_000_000,
    },
    {
        "name": "nc-sr-04_pbesol_standard_upf",
        "family": "PseudoDojo",
        "filename": "nc-sr-04_pbesol_standard_upf.tgz",
        "urls": ["https://www.pseudo-dojo.org/pseudos/nc-sr-04_pbesol_standard_upf.tgz"],
        "min_upf": 50,
        "min_bytes": 1_000_000,
    },
    {
        "name": "nc-fr-04_pbesol_standard_upf",
        "family": "PseudoDojo",
        "filename": "nc-fr-04_pbesol_standard_upf.tgz",
        "urls": ["https://www.pseudo-dojo.org/pseudos/nc-fr-04_pbesol_standard_upf.tgz"],
        "min_upf": 50,
        "min_bytes": 1_000_000,
    },
]

# Back-compat alias (older scripts may import the bare URL list).
QE_PSEUDO_URLS = [pack["urls"][0] for pack in QE_PSEUDO_PACKS]

# MACE Models URLs mapping
MACE_MODELS = [
    {
        "url": "https://github.com/ACEsuit/mace-foundations/releases/download/mace_mp_0b3/mace-mp-0b3-medium.model",
        "filename": "mace-mp-0b3-medium.model",
    },
    {
        "url": "https://github.com/ACEsuit/mace-foundations/releases/download/mace_mp_0/2024-01-07-mace-128-L2_epoch-199.model",
        "filename": "mace-mp-0-large.model",
    },
]


def get_docs_path(workspace_dir: Path) -> Path:
    """Get the path to the docs folder."""
    return workspace_dir / DOCS_FOLDER_NAME


def _dir_has_entries(path: Path) -> bool:
    if not path.is_dir():
        return False
    try:
        return any(path.iterdir())
    except OSError:
        return False


def _has_pseudopotential_files(path: Path) -> bool:
    """True when a pseudo tree contains real potential files (not just empty dirs)."""
    if not path.is_dir():
        return False
    try:
        for item in path.rglob("*"):
            if not item.is_file():
                continue
            name = item.name.lower()
            if name.endswith((".upf", ".psp8", ".psml", ".cpi")) or "pseudo" in name:
                return True
            # SSSP packs also include LICENSE / JSON metadata — require UPF-like weight
            if item.suffix == "" and item.stat().st_size > 10_000:
                return True
    except OSError:
        return False
    return False


def is_repo_complete(docs_dir: Path, config: dict) -> bool:
    """Return True when a cloned repo has the expected sparse content."""
    target = docs_dir / config["target"]
    if not _dir_has_entries(target):
        return False
    for rel in config.get("required_paths") or []:
        candidate = target / rel
        if candidate.is_file():
            continue
        if candidate.is_dir() and _dir_has_entries(candidate):
            continue
        return False
    return True


def is_qe_pseudos_complete(docs_dir: Path) -> bool:
    """True when both SSSP packs and PseudoDojo packs contain real potentials."""
    qe_dir = docs_dir / "q-e"
    # Efficiency + precision each ~100 UPF; require a solid majority present.
    # PseudoDojo four packs are smaller; require a clear non-empty install.
    return _count_upf_files(qe_dir / "SSSP") >= 160 and _count_upf_files(qe_dir / "PseudoDojo") >= 100


def is_mace_models_complete(docs_dir: Path) -> bool:
    models_dir = docs_dir / "mace" / "models"
    return all((models_dir / model["filename"]).is_file() for model in MACE_MODELS)


def is_docs_complete(workspace_dir: Path) -> bool:
    """True only when every bundled repo + QE pseudos + MACE models are present."""
    docs_dir = get_docs_path(workspace_dir)
    if not docs_dir.is_dir():
        return False
    for config in REPO_CONFIGS:
        if not is_repo_complete(docs_dir, config):
            return False
    if not is_qe_pseudos_complete(docs_dir):
        return False
    if not is_mace_models_complete(docs_dir):
        return False
    return True


def is_docs_available(workspace_dir: Path) -> bool:
    """Backward-compatible check used by runtime.

    Historically this returned True if *any* repo existed, which caused partial
    caches (e.g. missing LAMMPS or QE pseudopotentials) to skip repair. Prefer
    completeness so download/repair keeps filling gaps.
    """
    return is_docs_complete(workspace_dir)


def _cleanup_stale_temp_dirs(docs_dir: Path) -> None:
    """Remove leftover ``*_temp`` clone directories from failed runs."""
    if not docs_dir.is_dir():
        return
    for item in list(docs_dir.iterdir()):
        if item.is_dir() and item.name.endswith("_temp"):
            _log(f"Removing stale temp clone directory {item.name}")
            shutil.rmtree(item, ignore_errors=True)


def _run_git(args: list[str], timeout: int, cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _clone_with_sparse_checkout(
    url: str,
    temp_clone_dir: Path,
    sparse_paths: list,
    target_path: Path,
    name: str,
    alt_url: Optional[str] = None,
    timeout: int = 300,
) -> bool:
    """Clone repository with sparse checkout into target_path."""
    # Always start clean — a previous failed run often leaves an empty ``*_temp``.
    if temp_clone_dir.exists():
        shutil.rmtree(temp_clone_dir, ignore_errors=True)
    if target_path.exists():
        shutil.rmtree(target_path, ignore_errors=True)

    try:
        result = _run_git(
            ["git", "clone", "--depth", "1", "--filter=blob:none", "--no-checkout", url, str(temp_clone_dir)],
            timeout=timeout,
        )

        if result.returncode != 0 and alt_url:
            _log(f"Trying alternative URL for {name}")
            if temp_clone_dir.exists():
                shutil.rmtree(temp_clone_dir, ignore_errors=True)
            result = _run_git(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    "--filter=blob:none",
                    "--no-checkout",
                    alt_url,
                    str(temp_clone_dir),
                ],
                timeout=timeout,
            )

        if result.returncode != 0:
            _log(f"Failed to clone {name}", {"error": (result.stderr or "")[-500:]})
            shutil.rmtree(temp_clone_dir, ignore_errors=True)
            return False

        init = _run_git(
            ["git", "-C", str(temp_clone_dir), "sparse-checkout", "init", "--cone"],
            timeout=60,
        )
        if init.returncode != 0:
            _log(f"Failed sparse-checkout init for {name}", {"error": (init.stderr or "")[-500:]})
            shutil.rmtree(temp_clone_dir, ignore_errors=True)
            return False

        sparse = _run_git(
            ["git", "-C", str(temp_clone_dir), "sparse-checkout", "set", *sparse_paths],
            timeout=120,
        )
        if sparse.returncode != 0:
            _log(f"Failed sparse-checkout set for {name}", {"error": (sparse.stderr or "")[-500:]})
            shutil.rmtree(temp_clone_dir, ignore_errors=True)
            return False

        checkout = _run_git(
            ["git", "-C", str(temp_clone_dir), "checkout"],
            timeout=max(120, timeout // 2),
        )
        if checkout.returncode != 0:
            _log(f"Failed to checkout sparse paths for {name}", {"error": (checkout.stderr or "")[-500:]})
            shutil.rmtree(temp_clone_dir, ignore_errors=True)
            return False

        # Move material files into the stable target name (drop .git).
        target_path.mkdir(parents=True, exist_ok=True)
        moved = 0
        for item in list(temp_clone_dir.iterdir()):
            if item.name == ".git":
                continue
            dest = target_path / item.name
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            shutil.move(str(item), str(dest))
            moved += 1

        shutil.rmtree(temp_clone_dir, ignore_errors=True)

        if moved == 0:
            _log(f"Sparse clone for {name} produced no files")
            shutil.rmtree(target_path, ignore_errors=True)
            return False

        return True

    except subprocess.TimeoutExpired:
        _log(f"Timeout while cloning {name}")
        shutil.rmtree(temp_clone_dir, ignore_errors=True)
        shutil.rmtree(target_path, ignore_errors=True)
        return False
    except Exception as e:
        _log(f"Error cloning {name}", {"error": str(e)})
        shutil.rmtree(temp_clone_dir, ignore_errors=True)
        shutil.rmtree(target_path, ignore_errors=True)
        return False


def _count_upf_files(path: Path) -> int:
    if not path.is_dir():
        return 0
    try:
        return sum(
            1
            for item in path.rglob("*")
            if item.is_file() and item.name.lower().endswith((".upf", ".psp8", ".psml", ".cpi"))
        )
    except OSError:
        return 0


def _pseudo_mirror_urls(filename: str) -> list[str]:
    """Optional operator-hosted mirror (bypasses Materials Cloud → CSCS redirects)."""
    import os

    bases: list[str] = []
    for key in ("QUASAR_PSEUDO_MIRROR", "QUASAR_PSEUDO_MIRROR_BASE"):
        raw = (os.environ.get(key) or "").strip().rstrip("/")
        if raw:
            bases.append(raw)
    # Common Nectar layout if artifacts are published beside the worker image tar.
    public = (os.environ.get("PUBLIC_BASE_URL") or os.environ.get("QUASAR_REMOTE_CLOUD_URL") or "").strip().rstrip("/")
    if public:
        bases.append(f"{public}/quasar-artifacts/pseudos")
    urls = []
    for base in bases:
        urls.append(f"{base}/{filename}")
    return urls


def _download_file(url: str, dest: Path, timeout: int = 600, min_bytes: int = 1) -> bool:
    """Stream a URL to dest with retries. Returns True on success."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(dest) + ".partial")

    def _cleanup_tmp() -> None:
        try:
            tmp.unlink()
        except OSError:
            pass

    # Strategy 1: requests (follows Materials Cloud 302 → rgw.cscs.ch)
    try:
        import requests

        headers = {
            "User-Agent": "QUASAR-docs-downloader/1.0 (+https://github.com/fengxuyy/QUASAR)",
            "Accept": "*/*",
        }
        with requests.get(
            url,
            stream=True,
            timeout=(30, timeout),
            allow_redirects=True,
            headers=headers,
        ) as response:
            if response.status_code != 200:
                _log(f"HTTP {response.status_code} for {url}")
            else:
                with open(tmp, "wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            handle.write(chunk)
                size = tmp.stat().st_size if tmp.exists() else 0
                if size >= min_bytes:
                    tmp.replace(dest)
                    return True
                _log(f"Download too small for {url}", {"bytes": size, "min_bytes": min_bytes})
                _cleanup_tmp()
    except Exception as e:
        _log(f"requests download failed for {url}", {"error": str(e)})
        _cleanup_tmp()

    # Strategy 2: curl -L (more reliable with some flaky object stores)
    curl = shutil.which("curl")
    if curl:
        try:
            result = subprocess.run(
                [
                    curl,
                    "-fL",
                    "--retry",
                    "3",
                    "--retry-delay",
                    "2",
                    "--connect-timeout",
                    "30",
                    "--max-time",
                    str(max(timeout, 120)),
                    "-A",
                    "QUASAR-docs-downloader/1.0",
                    "-o",
                    str(tmp),
                    url,
                ],
                capture_output=True,
                text=True,
                timeout=max(timeout, 120) + 30,
            )
            size = tmp.stat().st_size if tmp.exists() else 0
            if result.returncode == 0 and size >= min_bytes:
                tmp.replace(dest)
                return True
            _log(
                f"curl download failed for {url}",
                {"code": result.returncode, "bytes": size, "err": (result.stderr or "")[-300:]},
            )
            _cleanup_tmp()
        except Exception as e:
            _log(f"curl download error for {url}", {"error": str(e)})
            _cleanup_tmp()

    return False


def _download_and_extract_pseudo_pack(
    pack: dict,
    qe_dir: Path,
    status_tracker: Optional[Callable] = None,
) -> bool:
    """Download one SSSP/PseudoDojo pack and extract it under q-e/."""
    import tarfile
    from src.utils.safe_tar import safe_extractall

    family = pack["family"]
    name = pack["name"]
    filename = pack["filename"]
    base_dir = qe_dir / family
    target_subdir = base_dir / name
    min_upf = int(pack.get("min_upf") or 1)
    min_bytes = int(pack.get("min_bytes") or 1)

    if _count_upf_files(target_subdir) >= min_upf:
        _log(f"Pseudopotential {name} already complete, skipping")
        return True

    if status_tracker:
        status_tracker(f"Downloading {filename}...")
    _log(f"Downloading pseudopotential pack {filename}")

    if target_subdir.exists():
        shutil.rmtree(target_subdir, ignore_errors=True)
    target_subdir.mkdir(parents=True, exist_ok=True)

    archive_path = base_dir / f".{name}.download"
    urls = list(_pseudo_mirror_urls(filename)) + list(pack.get("urls") or [])

    downloaded = False
    for url in urls:
        _log(f"Trying {url}")
        if _download_file(url, archive_path, timeout=900, min_bytes=min_bytes):
            # Basic gzip/tar magic check for SSSP (.tar.gz) packs
            try:
                head = archive_path.read_bytes()[:4]
            except OSError:
                head = b""
            if filename.endswith((".tar.gz", ".tgz")) and not (
                head[:2] == b"\x1f\x8b" or head[:5] == b"ustar" or head[257:262] == b"ustar"
            ):
                # gzip magic OR raw tar; reject HTML error pages
                if head[:1] == b"<" or head[:4] == b"HTTP":
                    _log(f"Download for {filename} looks like HTML/error, not an archive")
                    try:
                        archive_path.unlink()
                    except OSError:
                        pass
                    continue
            downloaded = True
            break

    if not downloaded:
        _log(f"All download URLs failed for {filename}")
        shutil.rmtree(target_subdir, ignore_errors=True)
        return False

    try:
        with tarfile.open(archive_path, mode="r:*") as tar:
            safe_extractall(tar, target_subdir)
    except Exception as e:
        _log(f"Failed to extract {filename}", {"error": str(e)})
        shutil.rmtree(target_subdir, ignore_errors=True)
        try:
            archive_path.unlink()
        except OSError:
            pass
        return False
    finally:
        try:
            archive_path.unlink()
        except OSError:
            pass

    upf_count = _count_upf_files(target_subdir)
    if upf_count < min_upf:
        _log(
            f"Pseudopotential extract incomplete for {name}",
            {"upf_count": upf_count, "min_upf": min_upf},
        )
        shutil.rmtree(target_subdir, ignore_errors=True)
        return False

    _log(f"Extracted {filename} → {family}/{name} ({upf_count} potentials)")
    return True


def _download_pseudopotentials(qe_dir: Path, status_tracker: Optional[Callable] = None) -> bool:
    """Download Quantum ESPRESSO pseudopotentials into SSSP and PseudoDojo directories."""
    sssp_dir = qe_dir / "SSSP"
    pseudodojo_dir = qe_dir / "PseudoDojo"

    if (
        _count_upf_files(sssp_dir) >= 160
        and _count_upf_files(pseudodojo_dir) >= 100
    ):
        _log("Pseudopotentials already complete (SSSP and PseudoDojo), skipping")
        return True

    ok = True
    for pack in QE_PSEUDO_PACKS:
        try:
            if not _download_and_extract_pseudo_pack(pack, qe_dir, status_tracker):
                ok = False
        except Exception as e:
            _log("Error downloading pseudopotential pack", {"pack": pack.get("name"), "error": str(e)})
            ok = False

    sssp_ok = _count_upf_files(sssp_dir) >= 160
    pdojo_ok = _count_upf_files(pseudodojo_dir) >= 100
    if not sssp_ok:
        _log(f"SSSP still incomplete ({_count_upf_files(sssp_dir)} potentials)")
    if not pdojo_ok:
        _log(f"PseudoDojo still incomplete ({_count_upf_files(pseudodojo_dir)} potentials)")
    return sssp_ok and pdojo_ok and ok


def _download_mace_models(mace_dir: Path, status_tracker: Optional[Callable] = None) -> bool:
    """Download MACE models into the models directory under docs/mace."""
    models_dir = mace_dir / "models"

    if all((models_dir / model["filename"]).is_file() for model in MACE_MODELS):
        _log("MACE models already exist, skipping")
        return True

    models_dir.mkdir(parents=True, exist_ok=True)
    ok = True
    for model in MACE_MODELS:
        target_path = models_dir / model["filename"]
        if target_path.is_file() and target_path.stat().st_size > 0:
            _log(f"MACE model {model['filename']} already exists, skipping")
            continue

        if status_tracker:
            status_tracker(f"Downloading {model['filename']}...")
        _log(f"Downloading MACE model {model['filename']}")

        if not _download_file(model["url"], target_path, timeout=600):
            ok = False
            try:
                target_path.unlink()
            except OSError:
                pass
        else:
            _log(f"Downloaded MACE model {model['filename']}")

    return all((models_dir / model["filename"]).is_file() for model in MACE_MODELS) and ok


def download_docs(
    workspace_dir: Path,
    status_tracker: Optional[Callable[[str], None]] = None,
    force: bool = False,
) -> bool:
    """Download or repair documentation repositories.

    Always fills missing/incomplete pieces (LAMMPS, QE pseudos, etc.) unless
    everything is already complete. Pass force=True to re-clone all repos.
    """
    docs_dir = get_docs_path(workspace_dir)

    if not force and is_docs_complete(workspace_dir):
        _log("Documentation already complete")
        return True

    try:
        result = subprocess.run(["git", "--version"], capture_output=True, timeout=5)
        if result.returncode != 0:
            _log("Git is not available")
            return False
    except (FileNotFoundError, subprocess.TimeoutExpired):
        _log("Git is not available")
        return False

    docs_dir.mkdir(parents=True, exist_ok=True)
    _cleanup_stale_temp_dirs(docs_dir)

    if status_tracker:
        status_tracker("Downloading documentation...")
    _log("Downloading / repairing documentation repositories")

    success_count = 0
    total = len(REPO_CONFIGS)

    for idx, config in enumerate(REPO_CONFIGS, 1):
        name = config["name"]
        target_name = config["target"]
        target_path = docs_dir / target_name

        if status_tracker:
            status_tracker(f"Cloning {name} ({idx}/{total})...")

        if not force and is_repo_complete(docs_dir, config):
            _log(f"{name} already complete, skipping")
            success_count += 1
            continue

        # Incomplete target (or leftover from a bad sparse clone) — rebuild.
        if target_path.exists() and (force or not is_repo_complete(docs_dir, config)):
            _log(f"Replacing incomplete {name} at {target_path}")
            shutil.rmtree(target_path, ignore_errors=True)

        _log(f"Cloning {name}...")
        temp_clone_dir = docs_dir / f"{target_name}_temp"

        if _clone_with_sparse_checkout(
            config["url"],
            temp_clone_dir,
            config["sparse_paths"],
            target_path,
            name,
            config.get("alt_url"),
            timeout=int(config.get("timeout") or 300),
        ) and is_repo_complete(docs_dir, config):
            _log(f"Successfully cloned {name}")
            success_count += 1
        else:
            _log(f"Failed to produce a complete {name} tree")
            # Ensure no empty lammps_temp / partial target is left behind.
            shutil.rmtree(temp_clone_dir, ignore_errors=True)
            if target_path.exists() and not is_repo_complete(docs_dir, config):
                shutil.rmtree(target_path, ignore_errors=True)

    # QE pseudopotentials (repair even if repos were already present)
    qe_dir = docs_dir / "q-e"
    if qe_dir.is_dir():
        if status_tracker:
            status_tracker("Downloading pseudopotentials...")
        if not _download_pseudopotentials(qe_dir, status_tracker):
            _log("Pseudopotential download incomplete")
    else:
        _log("Skipping pseudopotentials — q-e docs tree is missing")

    # MACE models
    mace_dir = docs_dir / "mace"
    if mace_dir.is_dir():
        if status_tracker:
            status_tracker("Downloading MACE models...")
        if not _download_mace_models(mace_dir, status_tracker):
            _log("MACE model download incomplete")

    _cleanup_stale_temp_dirs(docs_dir)

    complete = is_docs_complete(workspace_dir)
    _log(
        "Documentation download finished",
        {
            "repos_ok": success_count,
            "total": total,
            "complete": complete,
            "pseudos": is_qe_pseudos_complete(docs_dir),
            "mace": is_mace_models_complete(docs_dir),
        },
    )
    # Keep historical contract: True if anything usable landed; callers that need
    # a hard guarantee should also check is_docs_complete().
    return success_count > 0
