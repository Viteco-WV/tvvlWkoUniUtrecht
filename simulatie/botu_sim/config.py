from pathlib import Path
import copy
import yaml

PROJECT = Path(__file__).resolve().parents[2]


def laad_config(pad, overrides=None):
    """Lees een YAML-configuratie; `overrides` is een dict met geneste waarden die voorrang krijgen."""
    with open(pad) as f:
        cfg = yaml.safe_load(f)
    if overrides:
        cfg = _merge(copy.deepcopy(cfg), overrides)
    return cfg


def _merge(basis, extra):
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(basis.get(k), dict):
            _merge(basis[k], v)
        else:
            basis[k] = v
    return basis


def pad(rel):
    return PROJECT / rel
