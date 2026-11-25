#!/usr/bin/env python3
"""
Structure processor for CIF files using pymatgen.
Handles cell transformations, bonding strategies, and image atom calculations.

Usage:
    python structure_processor.py

Input (JSON on stdin):
    {
        "cif_content": "...",
        "cell_type": "input" | "primitive" | "conventional" | "reduced_niggli" | "reduced_lll",
        "bonding": "jmol" | "crystalnn",
        "draw_image_atoms": true | false,
        "bonded_sites_outside_unit_cell": true | false,
        "unit_cell_repeats": [1, 1, 1],
        "mof_mode": true | false
    }

Output (JSON on stdout):
    {
        "sites": [{"symbol": "Fe", "position": [x, y, z], "index": 0}, ...],
        "bonds": [[site_idx1, site_idx2], ...],
        "unit_cell": {"a": [...], "b": [...], "c": [...]},
        "error": null
    }
"""

import json
import shlex
import sys
import warnings
from itertools import combinations, product


MAX_UNIT_CELL_REPEAT = 4
MAX_SUPERCELL_SITES = 2000
MAX_DRAWN_SITES = 2500
MAX_RENDERED_BONDS = 6000
MAX_POLYHEDRA_SITES = 800


def infer_element_from_label(label):
    letters = "".join(ch for ch in label if ch.isalpha())
    if not letters:
        return None
    if len(letters) > 1 and letters[1].islower():
        return letters[:2]
    return letters[0]


def normalize_element_symbol(symbol):
    if symbol is None:
        return None
    cleaned = str(symbol).strip().strip("'\"")
    letters = "".join(ch for ch in cleaned if ch.isalpha())
    if not letters:
        return None
    if len(letters) > 1 and letters[1].islower():
        return letters[0].upper() + letters[1].lower()
    return letters[0].upper()


def normalize_unit_cell_repeats(unit_cell_repeats):
    if unit_cell_repeats is None:
        return (1, 1, 1)
    if not isinstance(unit_cell_repeats, (list, tuple)) or len(unit_cell_repeats) != 3:
        raise ValueError("Unit cell duplicate counts must be a list of three integers.")

    repeats = []
    for value in unit_cell_repeats:
        if isinstance(value, bool):
            raise ValueError("Unit cell duplicate counts must be integers.")
        try:
            repeat = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Unit cell duplicate counts must be integers.") from exc
        if repeat < 1 or repeat > MAX_UNIT_CELL_REPEAT:
            raise ValueError(f"Unit cell duplicate counts must be between 1 and {MAX_UNIT_CELL_REPEAT}.")
        repeats.append(repeat)

    return tuple(repeats)


def repeat_multiplier(unit_cell_repeats):
    return unit_cell_repeats[0] * unit_cell_repeats[1] * unit_cell_repeats[2]


def too_many_atoms_error(atom_count, limit, stage="render"):
    return {
        "error": (
            f"Too many atoms to {stage} safely ({atom_count} requested, limit is {limit}). "
            "Reduce the unit cell duplicate counts or disable image/outside-cell atoms."
        )
    }


def tokenize_cif_line(line):
    """Tokenize a simple CIF line while respecting quoted values."""
    try:
        return shlex.split(line, comments=True, posix=True)
    except ValueError:
        return line.split()


def iter_cif_loops(cif_content):
    """Yield CIF loop headers and rows for simple, table-shaped loops."""
    lines = cif_content.splitlines()
    i = 0

    while i < len(lines):
        tokens = tokenize_cif_line(lines[i].strip())
        if not tokens or tokens[0].lower() != "loop_":
            i += 1
            continue

        i += 1
        headers = []
        while i < len(lines):
            tokens = tokenize_cif_line(lines[i].strip())
            if not tokens:
                i += 1
                continue
            if not tokens[0].startswith("_"):
                break
            headers.append(tokens[0].lower())
            i += 1

        rows = []
        row_tokens = []
        while i < len(lines):
            tokens = tokenize_cif_line(lines[i].strip())
            if not tokens:
                i += 1
                continue

            first = tokens[0].lower()
            if first == "loop_" or first.startswith("_") or first.startswith("data_") or first.startswith("save_"):
                break

            row_tokens.extend(tokens)
            while headers and len(row_tokens) >= len(headers):
                rows.append(row_tokens[:len(headers)])
                row_tokens = row_tokens[len(headers):]
            i += 1

        if headers and rows:
            yield headers, rows


def extract_cif_atom_records_and_bonds(cif_content):
    atom_records = []
    bond_label_pairs = []

    for headers, rows in iter_cif_loops(cif_content):
        if "_atom_site_label" in headers:
            label_idx = headers.index("_atom_site_label")
            symbol_idx = headers.index("_atom_site_type_symbol") if "_atom_site_type_symbol" in headers else None
            fract_indices = []
            for key in ("_atom_site_fract_x", "_atom_site_fract_y", "_atom_site_fract_z"):
                fract_indices.append(headers.index(key) if key in headers else None)

            for row in rows:
                if label_idx >= len(row):
                    continue
                label = row[label_idx]
                symbol = None
                if symbol_idx is not None and symbol_idx < len(row):
                    symbol = normalize_element_symbol(row[symbol_idx])
                if symbol is None:
                    symbol = normalize_element_symbol(infer_element_from_label(label))

                frac = None
                if all(idx is not None and idx < len(row) for idx in fract_indices):
                    try:
                        frac = [float(row[idx].split("(")[0]) for idx in fract_indices]
                    except (TypeError, ValueError):
                        frac = None
                atom_records.append({"label": label, "symbol": symbol, "frac": frac})

        if "_geom_bond_atom_site_label_1" in headers and "_geom_bond_atom_site_label_2" in headers:
            label_1_idx = headers.index("_geom_bond_atom_site_label_1")
            label_2_idx = headers.index("_geom_bond_atom_site_label_2")
            for row in rows:
                if label_1_idx < len(row) and label_2_idx < len(row):
                    bond_label_pairs.append((row[label_1_idx], row[label_2_idx]))

    return atom_records, bond_label_pairs


def periodic_frac_distance(frac_a, frac_b):
    import numpy as np

    delta = np.mod(np.subtract(frac_a, frac_b) + 0.5, 1.0) - 0.5
    return float(np.max(np.abs(delta)))


def get_nearest_jimage(structure, from_idx, to_idx):
    import numpy as np

    from_frac = structure[from_idx].frac_coords
    to_frac = structure[to_idx].frac_coords
    best_jimage = (0, 0, 0)
    best_distance = float("inf")

    for jimage in product((-1, 0, 1), repeat=3):
        if from_idx == to_idx and jimage == (0, 0, 0):
            continue
        delta_frac = np.add(to_frac, jimage) - from_frac
        delta_cart = structure.lattice.get_cartesian_coords(delta_frac)
        distance = float(np.linalg.norm(delta_cart))
        if distance < best_distance:
            best_distance = distance
            best_jimage = tuple(int(x) for x in jimage)

    return best_jimage


def structure_graph_from_empty(structure_graph_cls, structure):
    factory = getattr(structure_graph_cls, "from_empty_graph", None)
    if factory is None:
        factory = structure_graph_cls.with_empty_graph
    return factory(structure)


def structure_graph_from_local_env_strategy(structure_graph_cls, structure, nn_strategy):
    factory = getattr(structure_graph_cls, "from_local_env_strategy", None)
    if factory is None:
        factory = structure_graph_cls.with_local_env_strategy
    return factory(structure, nn_strategy)


def map_cif_atoms_to_structure(atom_records, structure, tolerance=0.005):
    label_to_idx = {}
    site_metadata = {}
    unmatched_indices = set(range(len(structure)))

    for record in atom_records:
        frac = record.get("frac")
        if frac is None:
            continue

        best_idx = None
        best_distance = float("inf")
        for idx in unmatched_indices:
            distance = periodic_frac_distance(frac, structure[idx].frac_coords)
            if distance < best_distance:
                best_idx = idx
                best_distance = distance

        if best_idx is not None and best_distance <= tolerance:
            label_to_idx[record["label"]] = best_idx
            site_metadata[best_idx] = {
                "label": record["label"],
                "symbol": record.get("symbol"),
            }
            unmatched_indices.remove(best_idx)

    if not label_to_idx and len(atom_records) == len(structure):
        for idx, record in enumerate(atom_records):
            label_to_idx[record["label"]] = idx
            site_metadata[idx] = {
                "label": record["label"],
                "symbol": record.get("symbol"),
            }

    return label_to_idx, site_metadata


def build_cif_bond_graph(atom_records, bond_label_pairs, structure, structure_graph_cls):
    if not atom_records or not bond_label_pairs:
        return None

    label_to_idx, _site_metadata = map_cif_atoms_to_structure(atom_records, structure)

    if not label_to_idx:
        return None

    graph = structure_graph_from_empty(structure_graph_cls, structure)
    edge_count = 0
    for label_1, label_2 in bond_label_pairs:
        idx_1 = label_to_idx.get(label_1)
        idx_2 = label_to_idx.get(label_2)
        if idx_1 is None or idx_2 is None:
            continue

        try:
            graph.add_edge(
                idx_1,
                idx_2,
                to_jimage=get_nearest_jimage(structure, idx_1, idx_2),
                warn_duplicates=False,
            )
            edge_count += 1
        except Exception:
            continue

    return graph if edge_count else None


def graph_has_edges(graph):
    if graph is None:
        return False
    try:
        return graph.graph.number_of_edges() > 0
    except Exception:
        return True


def get_site_element_symbol(site):
    specie = getattr(site, "specie", None)
    element = getattr(specie, "element", specie)
    symbol = getattr(element, "symbol", element)
    return normalize_element_symbol(symbol)


def is_metal_symbol(symbol):
    if not symbol:
        return False
    try:
        from pymatgen.core.periodic_table import Element

        return bool(Element(symbol).is_metal)
    except Exception:
        return False


def remove_homonuclear_metal_bonds(graph):
    edges_to_remove = []
    for edge in graph.graph.edges(keys=True):
        from_idx, to_idx, edge_key = edge
        from_symbol = get_site_element_symbol(graph.structure[from_idx])
        to_symbol = get_site_element_symbol(graph.structure[to_idx])
        if from_symbol == to_symbol and is_metal_symbol(from_symbol):
            edges_to_remove.append((from_idx, to_idx, edge_key))

    if edges_to_remove:
        graph.graph.remove_edges_from(edges_to_remove)


def get_sites_to_draw(
    structure,
    graph,
    draw_image_atoms=True,
    bonded_sites_outside_unit_cell=False,
    boundary_tolerance=0.05,
):
    """
    Returns a list of (site_index, jimage) tuples for atoms to draw.
    Based on crystaltoolkit's _get_sites_to_draw function.
    """
    import numpy as np
    
    sites_to_draw = [(idx, (0, 0, 0)) for idx in range(len(structure))]
    
    if draw_image_atoms:
        for idx, site in enumerate(structure):
            # Find coordinates close to 0
            zero_elements = [
                i for i, f in enumerate(site.frac_coords)
                if np.allclose(f, 0, atol=boundary_tolerance)
            ]
            
            coord_permutations = [
                x
                for length in range(1, len(zero_elements) + 1)
                for x in combinations(zero_elements, length)
            ]
            
            sites_to_draw += [
                (idx, (int(0 in perm), int(1 in perm), int(2 in perm)))
                for perm in coord_permutations
            ]
            
            # Find coordinates close to 1
            one_elements = [
                i for i, f in enumerate(site.frac_coords)
                if np.allclose(f, 1, atol=boundary_tolerance)
            ]
            
            coord_permutations = [
                x
                for length in range(1, len(one_elements) + 1)
                for x in combinations(one_elements, length)
            ]
            
            sites_to_draw += [
                (idx, (-int(0 in perm), -int(1 in perm), -int(2 in perm)))
                for perm in coord_permutations
            ]
    
    if bonded_sites_outside_unit_cell and graph is not None:
        sites_to_append = []
        for n, jimage in sites_to_draw:
            try:
                connected_sites = graph.get_connected_sites(n, jimage=jimage)
                for connected_site in connected_sites:
                    # Convert jimage to tuple for consistent comparison
                    cs_jimage = tuple(connected_site.jimage)
                    if cs_jimage != (0, 0, 0):
                        sites_to_append.append(
                            (connected_site.index, cs_jimage)
                        )
            except Exception:
                continue
        sites_to_draw += sites_to_append
    
    # Remove duplicates while keeping output ordering deterministic across Python processes.
    return sorted(set(sites_to_draw), key=lambda item: (item[0], item[1]))


def process_structure(cif_content: str, cell_type: str = "input", bonding: str = "jmol",
                      draw_image_atoms: bool = True, bonded_sites_outside_unit_cell: bool = False,
                      mof_mode: bool = False, unit_cell_repeats=None) -> dict:
    """Process CIF content with specified transformations."""
    try:
        from pymatgen.core import Structure
        from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
        from pymatgen.analysis.local_env import CrystalNN, JmolNN
        from pymatgen.analysis.graphs import StructureGraph
        import numpy as np
        
        # Parse CIF content
        structure = Structure.from_str(cif_content, fmt="cif")
        atom_records, bond_label_pairs = extract_cif_atom_records_and_bonds(cif_content)
        unit_cell_repeats = normalize_unit_cell_repeats(unit_cell_repeats)
        supercell_multiplier = repeat_multiplier(unit_cell_repeats)
        
        boundary_tolerance = 0.01 if mof_mode else 0.05
        if mof_mode:
            cell_type = "input"
            bonding = "jmol"

        # Apply cell transformation
        # Use higher symprec tolerance to detect symmetry in P1 structures
        if cell_type == "primitive":
            analyzer = SpacegroupAnalyzer(structure, symprec=0.1)
            structure = analyzer.get_primitive_standard_structure()
        elif cell_type == "conventional":
            analyzer = SpacegroupAnalyzer(structure, symprec=0.1)
            structure = analyzer.get_conventional_standard_structure()
        elif cell_type == "reduced_niggli":
            structure = structure.get_reduced_structure(reduction_algo="niggli")
        elif cell_type == "reduced_lll":
            structure = structure.get_reduced_structure(reduction_algo="LLL")
        
        # Normalize fractional coordinates to [0, 1)
        structure_dict = structure.as_dict(verbosity=0)
        for site in structure_dict["sites"]:
            site["abc"] = np.mod(site["abc"], 1).tolist()
        structure = Structure.from_dict(structure_dict)
        
        # Merge overlapping sites (can happen when coords at 1.0 get normalized to 0.0)
        structure.merge_sites(tol=0.01, mode="average")

        supercell_site_count = len(structure) * supercell_multiplier
        if supercell_site_count > MAX_SUPERCELL_SITES:
            return too_many_atoms_error(supercell_site_count, MAX_SUPERCELL_SITES, stage="duplicate")

        if supercell_multiplier > 1:
            structure.make_supercell([
                [unit_cell_repeats[0], 0, 0],
                [0, unit_cell_repeats[1], 0],
                [0, 0, unit_cell_repeats[2]],
            ])

        site_metadata = {}
        if mof_mode and supercell_multiplier == 1:
            _label_to_idx, site_metadata = map_cif_atoms_to_structure(atom_records, structure)
        
        # Build StructureGraph for bonding. In MOF mode we still force Jmol,
        # because CIF _geom_bond loops are often incomplete and should not cap
        # high metal coordination; use declared CIF bonds only as a fallback.
        graph = None

        if bonding in ("crystalnn", "jmol"):
            nn_strategy = CrystalNN() if bonding == "crystalnn" else JmolNN()
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                try:
                    graph = structure_graph_from_local_env_strategy(StructureGraph, structure, nn_strategy)
                except Exception:
                    graph = None

        if graph_has_edges(graph) and bonding == "jmol":
            remove_homonuclear_metal_bonds(graph)
        if not graph_has_edges(graph) and mof_mode and supercell_multiplier == 1:
            graph = build_cif_bond_graph(atom_records, bond_label_pairs, structure, StructureGraph) or graph
        if graph is None and bonding in ("crystalnn", "jmol"):
            graph = structure_graph_from_empty(StructureGraph, structure)
        
        # Get sites to draw (including image atoms if requested)
        sites_to_draw = get_sites_to_draw(
            structure, graph,
            draw_image_atoms=draw_image_atoms,
            bonded_sites_outside_unit_cell=bonded_sites_outside_unit_cell,
            boundary_tolerance=boundary_tolerance
        )
        if len(sites_to_draw) > MAX_DRAWN_SITES:
            return too_many_atoms_error(len(sites_to_draw), MAX_DRAWN_SITES)
        
        # Create a mapping from (idx, jimage) to output site index
        site_key_to_output_idx = {}
        output_sites = []
        
        for i, (idx, jimage) in enumerate(sites_to_draw):
            site = structure[idx]
            metadata = site_metadata.get(idx, {})
            symbol = metadata.get("symbol") or str(site.specie)
            # Calculate Cartesian position with jimage offset
            frac_with_image = np.add(site.frac_coords, jimage)
            cart_coords = structure.lattice.get_cartesian_coords(frac_with_image)
            
            output_sites.append({
                "symbol": symbol,
                "position": cart_coords.tolist(),
                "index": idx,  # Original site index
                "jimage": list(jimage),
                "label": metadata.get("label")
            })
            site_key_to_output_idx[(idx, tuple(jimage))] = i
        
        # Calculate bonds between drawn sites
        bonds = []
        if graph is not None:
            seen = set()
            for output_idx, (idx, jimage) in enumerate(sites_to_draw):
                try:
                    connected_sites = graph.get_connected_sites(idx, jimage=jimage)
                    for cs in connected_sites:
                        # Convert jimage to tuple for dictionary lookup
                        target_key = (cs.index, tuple(cs.jimage))
                        if target_key in site_key_to_output_idx:
                            target_output_idx = site_key_to_output_idx[target_key]
                            bond_key = tuple(sorted([output_idx, target_output_idx]))
                            if bond_key not in seen:
                                seen.add(bond_key)
                                bonds.append(list(bond_key))
                except Exception:
                    continue
        if len(bonds) > MAX_RENDERED_BONDS:
            return {
                "error": (
                    f"Too many bonds to render safely ({len(bonds)} requested, limit is {MAX_RENDERED_BONDS}). "
                    "Reduce the unit cell duplicate counts or disable image/outside-cell atoms."
                )
            }
        
        # Get unit cell vectors
        lattice = structure.lattice
        unit_cell = {
            "a": lattice.matrix[0].tolist(),
            "b": lattice.matrix[1].tolist(),
            "c": lattice.matrix[2].tolist()
        }
        
        # Calculate polyhedra for sites with >3 neighbors
        polyhedra = []
        if graph is not None and len(sites_to_draw) <= MAX_POLYHEDRA_SITES:
            try:
                from scipy.spatial import ConvexHull
                from pymatgen.core.periodic_table import Element
                
                # Calculate for ALL drawn sites (not just main cell)
                # This allows polyhedra for bonded_sites_outside_unit_cell
                for output_idx, (idx, jimage) in enumerate(sites_to_draw):
                    try:
                        connected_sites = graph.get_connected_sites(idx, jimage=jimage)
                        
                        if len(connected_sites) > 3:
                            # Get center site info
                            site = structure[idx]
                            center = output_sites[output_idx]["position"]
                            center_symbol = str(site.specie.element if hasattr(site.specie, 'element') else site.specie)
                            
                            # Electronegativity check: only draw polyhedra around more electronegative atom
                            # This prevents overlapping polyhedra (crystaltoolkit approach)
                            try:
                                center_en = Element(center_symbol).X  # Electronegativity
                            except Exception:
                                center_en = 0  # Fallback for unknown elements
                            
                            # Check if any neighbor is LESS electronegative or same species
                            # Polyhedra shown around LESS electronegative atoms (cations)
                            # surrounded by MORE electronegative atoms (anions)
                            should_skip = False
                            for cs in connected_sites:
                                neighbor_symbol = str(cs.site.specie.element if hasattr(cs.site.specie, 'element') else cs.site.specie)
                                try:
                                    neighbor_en = Element(neighbor_symbol).X
                                except Exception:
                                    neighbor_en = 0
                                
                                # Skip if neighbor is LESS electronegative OR same species
                                if neighbor_en < center_en or neighbor_symbol == center_symbol:
                                    should_skip = True
                                    break
                            
                            if should_skip:
                                continue
                            
                            # Only draw polyhedra if ALL neighbors are visible (in sites_to_draw)
                            # Following crystaltoolkit's approach: skip if incomplete coordination
                            neighbor_positions = []
                            all_neighbors_visible = True
                            
                            for cs in connected_sites:
                                target_key = (cs.index, tuple(cs.jimage))
                                if target_key in site_key_to_output_idx:
                                    neighbor_idx = site_key_to_output_idx[target_key]
                                    neighbor_positions.append(output_sites[neighbor_idx]["position"])
                                else:
                                    # This neighbor is not being drawn - incomplete coordination
                                    all_neighbors_visible = False
                                    break
                            
                            # Only create polyhedra if all neighbors are visible
                            if all_neighbors_visible and len(neighbor_positions) > 3:
                                # Include center in convex hull calculation
                                all_positions = [center] + neighbor_positions
                                
                                try:
                                    hull = ConvexHull(all_positions)
                                    
                                    symbol = output_sites[output_idx]["symbol"]
                                    
                                    polyhedra.append({
                                        "center_idx": output_idx,
                                        "vertices": all_positions,
                                        "faces": hull.simplices.tolist(),
                                        "symbol": symbol
                                    })
                                except Exception:
                                    # ConvexHull can fail for coplanar points
                                    pass
                    except Exception:
                        continue
            except ImportError:
                pass  # scipy not available
        
        return {
            "sites": output_sites,
            "bonds": bonds,
            "unit_cell": unit_cell,
            "polyhedra": polyhedra,
            "error": None
        }
        
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}


def main():
    """Main entry point - read JSON from stdin, write JSON to stdout."""
    try:
        input_data = json.load(sys.stdin)
        
        cif_content = input_data.get("cif_content", "")
        cell_type = input_data.get("cell_type", "input")
        bonding = input_data.get("bonding", "jmol")
        draw_image_atoms = input_data.get("draw_image_atoms", True)
        bonded_sites_outside = input_data.get("bonded_sites_outside_unit_cell", False)
        unit_cell_repeats = input_data.get("unit_cell_repeats", [1, 1, 1])
        mof_mode = input_data.get("mof_mode", False)
        
        if not cif_content:
            result = {"error": "No CIF content provided"}
        else:
            result = process_structure(
                cif_content, cell_type, bonding,
                draw_image_atoms, bonded_sites_outside, mof_mode, unit_cell_repeats
            )
        
        print(json.dumps(result))
        
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON input: {str(e)}"}))
    except Exception as e:
        print(json.dumps({"error": f"Unexpected error: {str(e)}"}))


if __name__ == "__main__":
    main()
