import builtins

from src.rag.embeddings import _detect_device


def test_detect_device_defaults_to_cpu_without_importing_torch(monkeypatch):
    """Default behavior should stay on CPU and avoid touching torch/CUDA."""
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "torch":
            raise AssertionError("torch should not be imported for the default CPU path")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    assert _detect_device() == "cpu"
