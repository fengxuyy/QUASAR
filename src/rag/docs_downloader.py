"""
Documentation downloader for QUASAR-CHEM.

Downloads documentation repositories (ASE, pymatgen, MACE, RASPA3, Q-E, LAMMPS)
to the workspace for reference and example access.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Optional, Callable

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


# Repository configurations
REPO_CONFIGS = [
    {
        "name": "ASE",
        "url": "https://gitlab.com/ase/ase.git",
        "target": "ase",
        "sparse_paths": ["doc", "ase", "examples"],
    },
    {
        "name": "pymatgen",
        "url": "https://github.com/materialsproject/pymatgen.git",
        "target": "pymatgen",
        "sparse_paths": ["src", "docs", "README.md"],
    },
    {
        "name": "MACE",
        "url": "https://github.com/ACEsuit/mace.git",
        "target": "mace",
        "sparse_paths": ["mace", "README.md"],
    },
    {
        "name": "RASPA3",
        "url": "https://github.com/iRASPA/RASPA3.git",
        "target": "RASPA3",
        "sparse_paths": ["docs", "examples"],
    },
    {
        "name": "Quantum ESPRESSO",
        "url": "https://gitlab.com/QEF/q-e.git",
        "alt_url": "https://gitlab.com/QEF/q-e",
        "target": "q-e",
        "sparse_paths": ["Doc", "PW/Doc", "PW/examples", "PP/Doc", "PP/examples", 
                        "PHonon/Doc", "PHonon/examples", "README.md"],
    },
    {
        "name": "LAMMPS",
        "url": "https://github.com/lammps/lammps.git",
        "target": "lammps",
        "sparse_paths": ["doc/src", "examples", "README", "doc/README"],
    },
]

# Pseudopotential URLs for Quantum ESPRESSO
QE_PSEUDO_URLS = [
    # SSSP (Standard Solid-State Pseudopotentials)
    "https://archive.materialscloud.org/api/records/rcyfm-68h65/files/SSSP_1.3.0_PBE_efficiency.tar.gz/content",
    "https://archive.materialscloud.org/api/records/rcyfm-68h65/files/SSSP_1.3.0_PBE_precision.tar.gz/content",
    # PseudoDojo - Norm-conserving pseudopotentials
    "https://www.pseudo-dojo.org/pseudos/nc-sr-05_pbe_standard_upf.tgz",
    "https://www.pseudo-dojo.org/pseudos/nc-fr-04_pbe_standard_upf.tgz",
    "https://www.pseudo-dojo.org/pseudos/nc-sr-04_pbesol_standard_upf.tgz",
    "https://www.pseudo-dojo.org/pseudos/nc-fr-04_pbesol_standard_upf.tgz",
]


def get_docs_path(workspace_dir: Path) -> Path:
    """Get the path to the docs folder."""
    return workspace_dir / DOCS_FOLDER_NAME


def is_docs_available(workspace_dir: Path) -> bool:
    """Check if documentation is already downloaded."""
    docs_dir = get_docs_path(workspace_dir)
    if not docs_dir.exists():
        return False
    # Check if at least some repos exist
    for config in REPO_CONFIGS:
        target_path = docs_dir / config["target"]
        if target_path.exists() and any(target_path.iterdir()):
            return True
    return False


def _clone_with_sparse_checkout(
    url: str,
    temp_clone_dir: Path,
    sparse_paths: list,
    target_path: Path,
    name: str,
    alt_url: Optional[str] = None,
) -> bool:
    """Clone repository with sparse checkout."""
    try:
        # Clone with shallow depth and no checkout
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--no-checkout", url, str(temp_clone_dir)],
            capture_output=True, text=True, timeout=300
        )
        
        # Try alternative URL if main URL fails
        if result.returncode != 0 and alt_url:
            _log(f"Trying alternative URL for {name}")
            result = subprocess.run(
                ["git", "clone", "--depth", "1", "--no-checkout", alt_url, str(temp_clone_dir)],
                capture_output=True, text=True, timeout=300
            )
        
        if result.returncode != 0:
            _log(f"Failed to clone {name}", {"error": result.stderr})
            return False
        
        # Enable sparse checkout
        subprocess.run(
            ["git", "-C", str(temp_clone_dir), "sparse-checkout", "init", "--cone"],
            capture_output=True, text=True
        )
        
        # Set sparse checkout paths
        subprocess.run(
            ["git", "-C", str(temp_clone_dir), "sparse-checkout", "set"] + sparse_paths,
            capture_output=True, text=True
        )
        
        # Checkout the sparse paths
        checkout_result = subprocess.run(
            ["git", "-C", str(temp_clone_dir), "checkout"],
            capture_output=True, text=True, timeout=60
        )
        
        if checkout_result.returncode != 0:
            _log(f"Failed to checkout sparse paths for {name}")
            shutil.rmtree(temp_clone_dir, ignore_errors=True)
            return False
        
        # Move files to target
        target_path.mkdir(parents=True, exist_ok=True)
        for item in temp_clone_dir.iterdir():
            if item.name == ".git":
                continue
            dest = target_path / item.name
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            shutil.move(str(item), str(dest))
        
        shutil.rmtree(temp_clone_dir, ignore_errors=True)
        return True
        
    except subprocess.TimeoutExpired:
        _log(f"Timeout while cloning {name}")
        shutil.rmtree(temp_clone_dir, ignore_errors=True)
        return False
    except Exception as e:
        _log(f"Error cloning {name}", {"error": str(e)})
        shutil.rmtree(temp_clone_dir, ignore_errors=True)
        return False


def _download_pseudopotentials(qe_dir: Path, status_tracker: Optional[Callable] = None):
    """Download Quantum ESPRESSO pseudopotentials into separate SSSP and PseudoDojo directories."""
    sssp_dir = qe_dir / "SSSP"
    pseudodojo_dir = qe_dir / "PseudoDojo"
    
    # Check if both directories already have content
    sssp_exists = sssp_dir.exists() and any(sssp_dir.iterdir())
    pseudodojo_exists = pseudodojo_dir.exists() and any(pseudodojo_dir.iterdir())
    
    if sssp_exists and pseudodojo_exists:
        _log("Pseudopotentials already exist (SSSP and PseudoDojo), skipping")
        return
    
    try:
        import requests
        import tarfile
        import io
        
        for url in QE_PSEUDO_URLS:
            try:
                # Determine which directory to use based on URL
                if "materialscloud" in url:
                    # SSSP pseudopotentials from Materials Cloud
                    filename = url.split("files/")[1].split("/content")[0]
                    base_dir = sssp_dir
                else:
                    # PseudoDojo pseudopotentials
                    filename = url.split("/")[-1]
                    base_dir = pseudodojo_dir
                
                folder_name = filename.replace(".tar.gz", "").replace(".tar", "").replace(".tgz", "")
                target_subdir = base_dir / folder_name
                
                # Skip if this specific subfolder already exists
                if target_subdir.exists() and any(target_subdir.iterdir()):
                    _log(f"Pseudopotential {folder_name} already exists, skipping")
                    continue
                
                if status_tracker:
                    status_tracker(f"Downloading {filename}...")
                _log(f"Downloading {filename}")
                
                target_subdir.mkdir(parents=True, exist_ok=True)
                response = requests.get(url, stream=True, timeout=120)
                
                if response.status_code == 200:
                    with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as tar:
                        tar.extractall(path=target_subdir)
                    _log(f"Extracted {filename} to {base_dir.name}")
            except Exception as e:
                _log(f"Error downloading pseudopotential", {"url": url, "error": str(e)})
    except ImportError:
        _log("requests module not available, skipping pseudopotential download")


def download_docs(
    workspace_dir: Path,
    status_tracker: Optional[Callable[[str], None]] = None,
    force: bool = False
) -> bool:
    """Download documentation repositories.
    
    Args:
        workspace_dir: Workspace directory
        status_tracker: Optional callback for progress updates
        force: Force re-download even if docs exist
        
    Returns:
        True if successful, False otherwise
    """
    docs_dir = get_docs_path(workspace_dir)
    
    # Check if already exists
    if not force and is_docs_available(workspace_dir):
        _log("Documentation already exists")
        return True
    
    # Check if git is available
    try:
        result = subprocess.run(["git", "--version"], capture_output=True, timeout=5)
        if result.returncode != 0:
            _log("Git is not available")
            return False
    except (FileNotFoundError, subprocess.TimeoutExpired):
        _log("Git is not available")
        return False
    
    docs_dir.mkdir(parents=True, exist_ok=True)
    
    if status_tracker:
        status_tracker("Downloading documentation...")
    _log("Downloading documentation repositories")
    
    success_count = 0
    total = len(REPO_CONFIGS)
    
    for idx, config in enumerate(REPO_CONFIGS, 1):
        name = config["name"]
        target_name = config["target"]
        target_path = docs_dir / target_name
        
        if status_tracker:
            status_tracker(f"Cloning {name} ({idx}/{total})...")
        
        # Skip if already exists
        if target_path.exists() and any(target_path.iterdir()):
            _log(f"{name} already exists, skipping")
            success_count += 1
            continue
        
        _log(f"Cloning {name}...")
        temp_clone_dir = docs_dir / f"{target_name}_temp"
        
        if _clone_with_sparse_checkout(
            config["url"],
            temp_clone_dir,
            config["sparse_paths"],
            target_path,
            name,
            config.get("alt_url")
        ):
            _log(f"Successfully cloned {name}")
            success_count += 1
    
    # Download pseudopotentials for Q-E
    qe_dir = docs_dir / "q-e"
    if qe_dir.exists():
        if status_tracker:
            status_tracker("Downloading pseudopotentials...")
        _download_pseudopotentials(qe_dir, status_tracker)
    
    _log(f"Documentation download complete", {"success": success_count, "total": total})
    return success_count > 0
