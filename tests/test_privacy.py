from qprime.privacy import detect_pii


def test_tello_identities_are_pii(sample_records):
    tello = next(r for r in sample_records if r["contextAttribute"] == "tello_vision")
    pii, paths = detect_pii(tello)
    assert pii
    assert any("name" in p or "ssn" in p for p in paths)


def test_misty_person_is_pii(sample_records):
    misty = next(r for r in sample_records if r["contextAttribute"] == "misty_vision")
    pii, _ = detect_pii(misty)
    assert pii


def test_zed_person_label_is_pii(sample_records):
    zed = next(r for r in sample_records if r["contextAttribute"] == "zed_vision")
    pii, _ = detect_pii(zed)
    assert pii


def test_thp_and_door_are_not_pii(sample_records):
    for stream in ("thp", "door"):
        rec = next(r for r in sample_records if r["contextAttribute"] == stream)
        pii, paths = detect_pii(rec)
        assert not pii, f"{stream} wrongly flagged as PII: {paths}"
