import math
import sys
from pathlib import Path

import pytest


pytest.importorskip("pymatgen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = PROJECT_ROOT / "web" / "server" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from structure_processor import process_structure  # noqa: E402


TWELVE_COORDINATE_ZN_CIF = """data_test
_symmetry_space_group_name_H-M 'P 1'
_cell_length_a 10
_cell_length_b 10
_cell_length_c 10
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_symmetry_Int_Tables_number 1
loop_
_symmetry_equiv_pos_as_xyz
'x, y, z'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Zn1 Zn 0.5 0.5 0.5
O1 O 0.70 0.5 0.5
O2 O 0.30 0.5 0.5
O3 O 0.5 0.70 0.5
O4 O 0.5 0.30 0.5
O5 O 0.5 0.5 0.70
O6 O 0.5 0.5 0.30
Zn2 Zn 0.78 0.5 0.5
Zn3 Zn 0.22 0.5 0.5
Zn4 Zn 0.5 0.78 0.5
Zn5 Zn 0.5 0.22 0.5
Zn6 Zn 0.5 0.5 0.78
Zn7 Zn 0.5 0.5 0.22
loop_
_geom_bond_atom_site_label_1
_geom_bond_atom_site_label_2
Zn1 O1
"""


BOUNDARY_CROSSING_ZN_CIF = """data_boundary12
_symmetry_space_group_name_H-M 'P 1'
_cell_length_a 10
_cell_length_b 10
_cell_length_c 10
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_symmetry_Int_Tables_number 1
loop_
_symmetry_equiv_pos_as_xyz
'x, y, z'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Zn1 Zn 0.95 0.95 0.95
Oxp O 0.15 0.95 0.95
Oxm O 0.75 0.95 0.95
Oyp O 0.95 0.15 0.95
Oym O 0.95 0.75 0.95
Ozp O 0.95 0.95 0.15
Ozm O 0.95 0.95 0.75
Znxp Zn 0.23 0.95 0.95
Znxm Zn 0.67 0.95 0.95
Znyp Zn 0.95 0.23 0.95
Znym Zn 0.95 0.67 0.95
Znzp Zn 0.95 0.95 0.23
Znzm Zn 0.95 0.95 0.67
"""


SIMPLE_TWO_ATOM_CIF = """data_simple
_symmetry_space_group_name_H-M 'P 1'
_cell_length_a 10
_cell_length_b 10
_cell_length_c 10
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_symmetry_Int_Tables_number 1
loop_
_symmetry_equiv_pos_as_xyz
'x, y, z'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
C1 C 0.25 0.25 0.25
O1 O 0.75 0.75 0.75
"""


def _make_large_cif(atom_count):
    rows = []
    for idx in range(atom_count):
        x = ((idx % 5) + 0.1) / 5
        y = (((idx // 5) % 4) + 0.1) / 4
        z = (((idx // 20) % 2) + 0.1) / 2
        rows.append(f"C{idx} C {x:.4f} {y:.4f} {z:.4f}")

    return (
        "data_large\n"
        "_symmetry_space_group_name_H-M 'P 1'\n"
        "_cell_length_a 20\n"
        "_cell_length_b 20\n"
        "_cell_length_c 20\n"
        "_cell_angle_alpha 90\n"
        "_cell_angle_beta 90\n"
        "_cell_angle_gamma 90\n"
        "_symmetry_Int_Tables_number 1\n"
        "loop_\n"
        "_symmetry_equiv_pos_as_xyz\n"
        "'x, y, z'\n"
        "loop_\n"
        "_atom_site_label\n"
        "_atom_site_type_symbol\n"
        "_atom_site_fract_x\n"
        "_atom_site_fract_y\n"
        "_atom_site_fract_z\n"
        + "\n".join(rows)
        + "\n"
    )


def _degree_for_central_zinc(result):
    sites = result["sites"]

    for idx, site in enumerate(sites):
        if site.get("label") == "Zn1" and site.get("jimage") == [0, 0, 0]:
            break
    else:
        for idx, site in enumerate(sites):
            if site.get("label") == "Zn1":
                break
        else:
            idx = min(
                range(len(sites)),
                key=lambda i: math.dist(sites[i]["position"], [5.0, 5.0, 5.0]),
            )

    return sum(1 for first, second in result["bonds"] if idx in (first, second))


def _degree_for_site_at_position(result, position):
    sites = result["sites"]

    for idx, site in enumerate(sites):
        if site.get("jimage") == [0, 0, 0] and all(
            math.isclose(site["position"][axis], position[axis], abs_tol=1e-6)
            for axis in range(3)
        ):
            break
    else:
        idx = min(
            range(len(sites)),
            key=lambda i: math.dist(sites[i]["position"], position),
        )

    return sum(1 for first, second in result["bonds"] if idx in (first, second))


@pytest.mark.parametrize("mof_mode", [False, True])
@pytest.mark.parametrize("bonded_sites_outside", [False, True])
def test_jmol_filters_homonuclear_metal_overbonding_in_and_out_of_mof_mode(
    mof_mode,
    bonded_sites_outside,
):
    result = process_structure(
        TWELVE_COORDINATE_ZN_CIF,
        cell_type="input",
        bonding="jmol",
        draw_image_atoms=False,
        bonded_sites_outside_unit_cell=bonded_sites_outside,
        mof_mode=mof_mode,
    )

    assert result["error"] is None
    assert _degree_for_central_zinc(result) == 6


@pytest.mark.parametrize("draw_image_atoms", [False, True])
@pytest.mark.parametrize("mof_mode", [False, True])
def test_bonded_sites_outside_cell_completes_boundary_coordination_without_metal_overbonding(
    draw_image_atoms,
    mof_mode,
):
    result = process_structure(
        BOUNDARY_CROSSING_ZN_CIF,
        cell_type="input",
        bonding="jmol",
        draw_image_atoms=draw_image_atoms,
        bonded_sites_outside_unit_cell=True,
        mof_mode=mof_mode,
    )

    assert result["error"] is None
    assert _degree_for_site_at_position(result, [9.5, 9.5, 9.5]) == 6


def test_unit_cell_repeats_expand_sites_and_lattice_vectors():
    result = process_structure(
        SIMPLE_TWO_ATOM_CIF,
        cell_type="input",
        bonding="jmol",
        draw_image_atoms=False,
        bonded_sites_outside_unit_cell=False,
        unit_cell_repeats=[2, 3, 1],
    )

    assert result["error"] is None
    assert len(result["sites"]) == 12
    assert result["unit_cell"]["a"] == pytest.approx([20.0, 0.0, 0.0])
    assert result["unit_cell"]["b"] == pytest.approx([0.0, 30.0, 0.0])
    assert result["unit_cell"]["c"] == pytest.approx([0.0, 0.0, 10.0])


def test_unit_cell_repeats_reject_too_many_atoms_before_duplication():
    result = process_structure(
        _make_large_cif(40),
        cell_type="input",
        bonding="jmol",
        draw_image_atoms=False,
        bonded_sites_outside_unit_cell=False,
        unit_cell_repeats=[4, 4, 4],
    )

    assert "Too many atoms" in result["error"]
