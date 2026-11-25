"""Unit tests for documentation cache completeness / repair helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.rag.docs_downloader import (
    REPO_CONFIGS,
    is_docs_available,
    is_docs_complete,
    is_qe_pseudos_complete,
    is_repo_complete,
    _cleanup_stale_temp_dirs,
    _has_pseudopotential_files,
)


class DocsDownloaderCompletenessTests(unittest.TestCase):
    def test_partial_docs_are_not_considered_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = root / "docs"
            ase = docs / "ase"
            ase.mkdir(parents=True)
            (ase / "ase").mkdir()
            (ase / "ase" / "atoms.py").write_text("x")
            (ase / "doc").mkdir()
            (ase / "doc" / "index.rst").write_text("x")
            # Only ASE is present — historically this returned True and skipped repair.
            self.assertFalse(is_docs_available(root))
            self.assertFalse(is_docs_complete(root))
            self.assertTrue(is_repo_complete(docs, next(c for c in REPO_CONFIGS if c["target"] == "ase")))

    def test_lammps_requires_doc_src_and_examples(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            lammps = docs / "lammps"
            lammps.mkdir(parents=True)
            (lammps / "README").write_text("readme")
            # Incomplete: no doc/src or examples (the lammps_temp failure mode)
            config = next(c for c in REPO_CONFIGS if c["target"] == "lammps")
            self.assertFalse(is_repo_complete(docs, config))

            (lammps / "doc" / "src").mkdir(parents=True)
            (lammps / "doc" / "src" / "pair_style.rst").write_text("x")
            (lammps / "examples" / "melt").mkdir(parents=True)
            (lammps / "examples" / "melt" / "in.melt").write_text("x")
            self.assertTrue(is_repo_complete(docs, config))

    def test_empty_pseudo_dirs_do_not_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            qe = Path(tmp) / "q-e"
            sssp = qe / "SSSP" / "SSSP_1.3.0_PBE_efficiency"
            sssp.mkdir(parents=True)
            self.assertFalse(_has_pseudopotential_files(qe / "SSSP"))

            (sssp / "Si.UPF").write_text("pseudo")
            self.assertTrue(_has_pseudopotential_files(qe / "SSSP"))

    def test_cleanup_removes_stale_temp_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            docs.mkdir()
            stale = docs / "lammps_temp"
            stale.mkdir()
            (stale / ".gitkeep").write_text("")
            keep = docs / "lammps"
            keep.mkdir()
            (keep / "README").write_text("ok")

            _cleanup_stale_temp_dirs(docs)
            self.assertFalse(stale.exists())
            self.assertTrue(keep.exists())

    def test_qe_pseudos_need_many_upf_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            sssp = docs / "q-e" / "SSSP" / "eff"
            sssp.mkdir(parents=True)
            (sssp / "C.UPF").write_text("x")
            # A single file is not a complete SSSP install.
            self.assertFalse(is_qe_pseudos_complete(docs))

            for i in range(170):
                (sssp / f"el{i}.UPF").write_text("x")
            pdojo = docs / "q-e" / "PseudoDojo" / "nc"
            pdojo.mkdir(parents=True)
            for i in range(110):
                (pdojo / f"el{i}.upf").write_text("x")
            self.assertTrue(is_qe_pseudos_complete(docs))


if __name__ == "__main__":
    unittest.main()
