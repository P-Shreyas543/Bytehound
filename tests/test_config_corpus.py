"""Every configuration in the repository still loads and decodes exactly as
recorded in tests/fixtures/decode_golden (Plane.md Part C, step C0).

The fixtures were generated from the code before the canonical-JSON work
(tools/make_decode_golden.py). A difference here means a decoded value for
an existing customer configuration changed: fix the code, or — only for an
intended change — regenerate the fixtures and review the diff.
"""

from __future__ import annotations

import json

import pytest

from tools.make_decode_golden import CONFIGS, GOLDEN, corpus, decode_snapshot, tracked_ids

CORPUS = corpus()


def test_corpus_is_complete():
    """Every configuration present has a fixture (a new file must be added on
    purpose). The tracked configurations are always present; with the local
    ``configs/`` folder every fixture must have its configuration."""
    ids = {cid for cid, _ in CORPUS}
    fixtures = {p.stem for p in GOLDEN.glob("*.json")}
    assert ids <= fixtures, f"missing fixtures: {sorted(ids - fixtures)}"
    assert tracked_ids() <= ids
    if not CONFIGS.is_dir():
        pytest.skip("configs/ (local device configurations) not present: only the tracked ones were checked")
    assert ids == fixtures, f"orphaned fixtures: {sorted(fixtures - ids)}"
    assert len(CORPUS) >= 23


@pytest.mark.parametrize("cid, path", CORPUS, ids=[c for c, _ in CORPUS])
def test_configuration_decodes_as_recorded(cid, path):
    from app.decoder.config_loader import load_config

    expected = json.loads((GOLDEN / f"{cid}.json").read_text(encoding="utf-8"))
    actual = json.loads(json.dumps({"config": expected["config"], "frames": decode_snapshot(load_config(path))},
                                   sort_keys=True))
    assert actual == expected
