from copy import deepcopy
import json
import hashlib


def normalize(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def sha_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha_visible(obj):
    normalized = normalize(obj)
    return normalized, sha_text(normalized)


def merge_fragments(*partials):
    merged = {}
    conflicts = []

    for part in partials:
        for key, value in part.items():
            if key not in merged:
                merged[key] = value
            elif merged[key] != value:
                entry = {
                    "field": key,
                    "left": merged[key],
                    "right": value,
                }
                if entry not in conflicts:
                    conflicts.append(entry)

    if conflicts:
        merged["_conflicts"] = conflicts

    return merged


EDGE_SPECS = {
    "A1": ("SOURCE", "A"),
    "A2": ("A", "B"),
    "A3": ("B", "DESTINATION"),
    "B1": ("SOURCE", "C"),
    "B2": ("C", "D"),
    "B3": ("D", "DESTINATION"),
}

PATH_SPECS = {
    "PATH_A": ("A1", "A2", "A3"),
    "PATH_B": ("B1", "B2", "B3"),
}


def edge_valid(state, prefix, expected_from, expected_to):
    return (
        state.get(f"{prefix}_from") == expected_from
        and state.get(f"{prefix}_to") == expected_to
        and state.get(f"{prefix}_gate") == "OPEN"
        and state.get(f"{prefix}_basis") == "CONSISTENT"
    )


def edge_status(state, prefix):
    expected_from, expected_to = EDGE_SPECS[prefix]

    if state.get("_conflicts"):
        return "CONFLICT"

    has_any = any(
        f"{prefix}_{field}" in state
        for field in ("from", "to", "gate", "basis")
    )

    if not has_any:
        return "ABSENT"

    if edge_valid(state, prefix, expected_from, expected_to):
        return "VALID"

    if (
        state.get(f"{prefix}_from") == expected_from
        and state.get(f"{prefix}_to") == expected_to
        and state.get(f"{prefix}_gate") == "OPEN"
        and f"{prefix}_basis" not in state
    ):
        return "INCOMPLETE"

    return "INVALID"


def path_valid(state, prefixes):
    return all(edge_valid(state, prefix, *EDGE_SPECS[prefix]) for prefix in prefixes)


def path_status(state, path_name):
    prefixes = PATH_SPECS[path_name]
    statuses = [edge_status(state, prefix) for prefix in prefixes]

    if state.get("_conflicts"):
        return "CONFLICT"

    if all(status == "VALID" for status in statuses):
        return "VALID"

    if any(status == "INVALID" for status in statuses):
        return "INVALID"

    if any(status == "INCOMPLETE" for status in statuses):
        return "INCOMPLETE"

    return "INCOMPLETE"


def render_graph(selected_path=None):
    lines = []
    lines.append("VISUAL GRAPH")
    lines.append("")
    lines.append("PATH A: SOURCE -> A -> B -> DESTINATION")
    lines.append("PATH B: SOURCE -> C -> D -> DESTINATION")
    lines.append("")

    if selected_path == "PATH_A":
        lines.append("SELECTED: PATH A")
    elif selected_path == "PATH_B":
        lines.append("SELECTED: PATH B")
    else:
        lines.append("SELECTED: NONE")

    return "\n".join(lines)


def build_visible_state(state):
    visible = {
        "resolution_state": state["resolution_state"],
        "path_a_status": path_status(state, "PATH_A"),
        "path_b_status": path_status(state, "PATH_B"),
    }

    if "selected_path" in state:
        visible["selected_path"] = state["selected_path"]
        visible["path_truth"] = state["path_truth"]
        visible["transition_state"] = state["transition_state"]
        visible["outcome"] = state["outcome"]

    if "_conflicts" in state:
        visible["conflict_count"] = len(state["_conflicts"])

    return visible


def resolve(structure):
    state = deepcopy(structure)

    changed = True
    while changed:
        changed = False

        has_conflict = bool(state.get("_conflicts"))
        valid_paths = []

        if not has_conflict:
            for path_name, prefixes in PATH_SPECS.items():
                if path_valid(state, prefixes):
                    valid_paths.append(path_name)

        for prefix, (expected_from, expected_to) in EDGE_SPECS.items():
            key = f"{prefix}_state"
            is_valid = edge_valid(state, prefix, expected_from, expected_to) if not has_conflict else False

            if is_valid:
                if state.get(key) != "VALID":
                    state[key] = "VALID"
                    changed = True
            else:
                if key in state:
                    del state[key]
                    changed = True

        if has_conflict:
            selected_path = None
            resolution_state = "CONFLICT"
        elif len(valid_paths) == 1:
            selected_path = valid_paths[0]
            resolution_state = "RESOLVED"
        elif len(valid_paths) == 0:
            selected_path = None
            resolution_state = "ABSTAIN"
        else:
            selected_path = None
            resolution_state = "CONFLICT"

        if selected_path is None:
            for key in (
                "selected_path",
                "path_truth",
                "transition_state",
                "outcome",
                "visual_graph",
            ):
                if key in state:
                    del state[key]
                    changed = True
        else:
            target = {
                "selected_path": selected_path,
                "path_truth": "SOURCE_TO_DESTINATION",
                "transition_state": "VALID",
                "outcome": "ARRIVED",
            }

            for key, value in target.items():
                if state.get(key) != value:
                    state[key] = value
                    changed = True

            graph = render_graph(selected_path=selected_path)
            if state.get("visual_graph") != graph:
                state["visual_graph"] = graph
                changed = True

        if state.get("resolution_state") != resolution_state:
            state["resolution_state"] = resolution_state
            changed = True

    state["_visible"] = build_visible_state(state)
    state["_normalized_visible"] = normalize(state["_visible"])
    state["_certificate"] = sha_text(state["_normalized_visible"])
    state["_path_truth_visible"] = state["resolution_state"] == "RESOLVED"

    return state


def print_result(label, result):
    print("=" * 72)
    print(label)
    print(json.dumps(result["_visible"], indent=2, sort_keys=True))

    if "visual_graph" in result:
        print("")
        print(result["visual_graph"])

    print("")
    print("path_truth_visible =", result["_path_truth_visible"])
    print("normalized_visible_state =", result["_normalized_visible"])
    print("certificate =", result["_certificate"])


def main():
    print("\nSTRAL Visual Path Demo")
    print("Path Resolution Without Traversal")
    print("Machine evaluation may occur, but correctness is established by structural closure, not traversal.")
    print("Diagnostic state may remain visible even when no admissible path is visible.\n")

    path_a_complete = {
        "A1_from": "SOURCE",
        "A1_to": "A",
        "A1_gate": "OPEN",
        "A1_basis": "CONSISTENT",
        "A2_from": "A",
        "A2_to": "B",
        "A2_gate": "OPEN",
        "A2_basis": "CONSISTENT",
        "A3_from": "B",
        "A3_to": "DESTINATION",
        "A3_gate": "OPEN",
        "A3_basis": "CONSISTENT",
    }

    path_b_complete = {
        "B1_from": "SOURCE",
        "B1_to": "C",
        "B1_gate": "OPEN",
        "B1_basis": "CONSISTENT",
        "B2_from": "C",
        "B2_to": "D",
        "B2_gate": "OPEN",
        "B2_basis": "CONSISTENT",
        "B3_from": "D",
        "B3_to": "DESTINATION",
        "B3_gate": "OPEN",
        "B3_basis": "CONSISTENT",
    }

    path_b_incomplete = {
        "B1_from": "SOURCE",
        "B1_to": "C",
        "B1_gate": "OPEN",
        "B1_basis": "CONSISTENT",
        "B2_from": "C",
        "B2_to": "D",
        "B2_gate": "OPEN",
        "B2_basis": "CONSISTENT",
        "B3_from": "D",
        "B3_to": "DESTINATION",
        "B3_gate": "OPEN",
    }

    scenario_1 = resolve(
        merge_fragments(
            path_a_complete,
            path_b_incomplete,
        )
    )
    print_result("SCENARIO 1 - UNIQUE VALID PATH", scenario_1)

    scenario_2 = resolve(
        merge_fragments(
            {
                "A1_from": "SOURCE",
                "A1_to": "A",
                "A1_gate": "OPEN",
                "A1_basis": "CONSISTENT",
                "A2_from": "A",
                "A2_to": "B",
                "A2_gate": "OPEN",
                "A3_from": "B",
                "A3_to": "DESTINATION",
                "A3_gate": "OPEN",
                "A3_basis": "CONSISTENT",
            },
            path_b_incomplete,
        )
    )
    print_result("SCENARIO 2 - NO VALID PATH", scenario_2)

    scenario_3 = resolve(
        merge_fragments(
            path_a_complete,
            path_b_complete,
        )
    )
    print_result("SCENARIO 3 - MULTIPLE VALID PATHS", scenario_3)

    scenario_4 = resolve(
        merge_fragments(
            path_a_complete,
            {
                "B1_from": "SOURCE",
                "B1_to": "C",
                "B1_gate": "OPEN",
                "B1_basis": "CONSISTENT",
                "B2_from": "C",
                "B2_to": "D",
                "B2_gate": "OPEN",
                "B2_basis": "CONSISTENT",
                "B3_from": "D",
                "B3_to": "DESTINATION",
                "B3_gate": "OPEN",
                "B3_basis": "MISMATCH",
            },
        )
    )
    print_result("SCENARIO 4 - INVALID ALTERNATIVE DOES NOT OVERRIDE VALID PATH", scenario_4)

    scenario_5a = resolve(
        merge_fragments(
            {"B2_to": "D"},
            {"A1_gate": "OPEN"},
            {"A3_basis": "CONSISTENT"},
            {"B1_from": "SOURCE"},
            {"A2_from": "A"},
            {"B3_from": "D"},
            {"A2_gate": "OPEN"},
            {"A1_to": "A"},
            {"B1_basis": "CONSISTENT"},
            {"A1_from": "SOURCE"},
            {"A2_basis": "CONSISTENT"},
            {"B3_to": "DESTINATION"},
            {"A3_to": "DESTINATION"},
            {"B3_gate": "OPEN"},
            {"B2_basis": "CONSISTENT"},
            {"B1_gate": "OPEN"},
            {"A3_gate": "OPEN"},
            {"A2_to": "B"},
            {"A1_basis": "CONSISTENT"},
            {"B2_from": "C"},
            {"A3_from": "B"},
            {"B1_to": "C"},
            {"B2_gate": "OPEN"},
            {"B3_basis": "MISSING"},
        )
    )

    scenario_5b = resolve(
        merge_fragments(
            {"A1_basis": "CONSISTENT"},
            {"B3_basis": "MISSING"},
            {"B2_gate": "OPEN"},
            {"B1_to": "C"},
            {"A3_from": "B"},
            {"B2_from": "C"},
            {"A2_to": "B"},
            {"A3_gate": "OPEN"},
            {"B1_gate": "OPEN"},
            {"B2_basis": "CONSISTENT"},
            {"B3_gate": "OPEN"},
            {"A3_to": "DESTINATION"},
            {"B3_to": "DESTINATION"},
            {"A2_basis": "CONSISTENT"},
            {"A1_from": "SOURCE"},
            {"B1_basis": "CONSISTENT"},
            {"A1_to": "A"},
            {"A2_gate": "OPEN"},
            {"B3_from": "D"},
            {"A2_from": "A"},
            {"B1_from": "SOURCE"},
            {"A1_gate": "OPEN"},
            {"A3_basis": "CONSISTENT"},
            {"B2_to": "D"},
        )
    )

    print_result("SCENARIO 5A - ORDER TEST A", scenario_5a)
    print_result("SCENARIO 5B - ORDER TEST B", scenario_5b)

    assert scenario_1["_visible"]["resolution_state"] == "RESOLVED"
    assert scenario_1["_visible"]["selected_path"] == "PATH_A"
    assert scenario_1["_visible"]["path_truth"] == "SOURCE_TO_DESTINATION"
    assert scenario_1["_visible"]["outcome"] == "ARRIVED"
    assert scenario_1["_path_truth_visible"] is True

    assert scenario_2["_visible"]["resolution_state"] == "ABSTAIN"
    assert "selected_path" not in scenario_2["_visible"]
    assert "outcome" not in scenario_2["_visible"]
    assert scenario_2["_path_truth_visible"] is False

    assert scenario_3["_visible"]["resolution_state"] == "CONFLICT"
    assert "selected_path" not in scenario_3["_visible"]
    assert "outcome" not in scenario_3["_visible"]
    assert scenario_3["_path_truth_visible"] is False

    assert scenario_4["_visible"]["resolution_state"] == "RESOLVED"
    assert scenario_4["_visible"]["path_b_status"] == "INVALID"
    assert scenario_4["_visible"]["selected_path"] == "PATH_A"
    assert scenario_4["_path_truth_visible"] is True

    assert scenario_5a["_certificate"] == scenario_5b["_certificate"]
    assert scenario_5a["_visible"] == scenario_5b["_visible"]
    assert scenario_5a["_normalized_visible"] == scenario_5b["_normalized_visible"]

    normalized_1, certificate_1 = sha_visible(scenario_1["_visible"])
    assert normalized_1 == scenario_1["_normalized_visible"]
    assert certificate_1 == scenario_1["_certificate"]

    print("\n" + "=" * 72)
    print("FINAL RESULT")
    print("PASS: unique valid path -> resolved")
    print("PASS: no valid path -> no forced path truth")
    print("PASS: multiple valid paths -> conflict")
    print("PASS: invalid alternative does not override valid path")
    print("PASS: same structure -> same visible state and certificate")
    print("PASS: certificate = SHA256(normalize(visible_state))")
    print("PASS: diagnostic visibility != admissible path visibility")
    print("CHALLENGE: same structure -> different visible state or certificate")
    print("=" * 72)


if __name__ == "__main__":
    main()