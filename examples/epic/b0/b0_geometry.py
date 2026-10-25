"""Geometry utilities for the ePIC B0 tracker AID2E example."""

from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
from typing import Any, Dict


B0_CONSTANTS = {
    "B0TrackerLayer1_zstart",
    "B0TrackerLayer2_zstart",
    "B0TrackerLayer3_zstart",
    "B0TrackerLayer4_zstart",
}


def geometry_expressions(design_point: Dict[str, Any]) -> Dict[str, str]:
    """
    Convert the AID2E B0 design point into the XML expressions used by ePIC.

    z1 is the first-layer offset and dz2/dz3/dz4 are successive
    longitudinal offsets, matching the original B0 optimization.
    """
    z1 = float(design_point["b0_tracker.z1"])
    dz2 = float(design_point["b0_tracker.dz2"])
    dz3 = float(design_point["b0_tracker.dz3"])
    dz4 = float(design_point["b0_tracker.dz4"])

    return {
        "B0TrackerLayer1_zstart":
            f"B0Tracker_length/2.0+({z1})",
        "B0TrackerLayer2_zstart":
            f"B0Tracker_length/2.0+({z1})+({dz2})",
        "B0TrackerLayer3_zstart":
            f"B0Tracker_length/2.0+({z1})+({dz2})+({dz3})",
        "B0TrackerLayer4_zstart":
            f"B0Tracker_length/2.0+({z1})+({dz2})+({dz3})+({dz4})",
    }


def edit_b0_geometry(
    xml_path: str | Path,
    design_point: Dict[str, Any],
) -> Path:
    """
    Modify the four B0 tracker layer z-start constants in an XML file.
    """
    xml_path = Path(xml_path)

    tree = ET.parse(xml_path)
    root = tree.getroot()

    expressions = geometry_expressions(design_point)
    found = set()

    for constant in root.findall(".//constant"):
        name = constant.get("name")

        if name in expressions:
            constant.set("value", expressions[name])
            found.add(name)

    missing = B0_CONSTANTS - found

    if missing:
        raise RuntimeError(
            "B0 constants not found in XML: "
            + ", ".join(sorted(missing))
        )

    tree.write(
        xml_path,
        encoding="utf-8",
        xml_declaration=True,
    )

    return xml_path


def create_b0_geometry(
    *,
    design_point: Dict[str, Any],
    source_xml: str | Path,
    output_xml: str | Path,
) -> Path:
    """
    Copy the nominal ePIC B0 tracker XML and apply one AID2E design point.
    """
    source_xml = Path(source_xml)
    output_xml = Path(output_xml)

    if not source_xml.exists():
        raise FileNotFoundError(
            f"Nominal B0 XML does not exist: {source_xml}"
        )

    output_xml.parent.mkdir(parents=True, exist_ok=True)

    shutil.copy2(source_xml, output_xml)

    return edit_b0_geometry(
        xml_path=output_xml,
        design_point=design_point,
    )


def read_b0_geometry(xml_path: str | Path) -> Dict[str, str]:
    """
    Read back the four optimized B0 constants.

    Useful for validation/tests.
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    values = {}

    for constant in root.findall(".//constant"):
        name = constant.get("name")

        if name in B0_CONSTANTS:
            values[name] = constant.get("value")

    missing = B0_CONSTANTS - set(values)

    if missing:
        raise RuntimeError(
            "B0 constants not found in XML: "
            + ", ".join(sorted(missing))
        )

    return values