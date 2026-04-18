from scene.lookup import load_lookup, material_for, physics_for


def test_known_class():
    phys = physics_for("chair")
    assert phys["mass_kg"] > 0
    assert 0 <= phys["restitution"] <= 1
    assert phys["is_rigid"] is True


def test_unknown_class_falls_back_to_default():
    phys = physics_for("wombat")
    assert phys["mass_kg"] == 1.0
    assert material_for("wombat") == "unknown"


def test_default_entry_present():
    table = load_lookup()
    assert "__default__" in table
