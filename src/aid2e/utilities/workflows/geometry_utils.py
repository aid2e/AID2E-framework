"""Helpers for modifying detector geometry in workflows.

These utilities facilitate modifying detector geometries
based on design parameters.

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
Homepage: https://aid2e.github.io/aid2e-framework
Repository: https://github.com/aid2e/AID2E-framework.git

"""

from typing import Any, Dict, List, Tuple
import xml.etree.ElementTree as ET


def modify_xml_files(modifications: Dict[str, List[Tuple[str, str, str, Any]]]) -> None:
    """Edit XML files

    Helper function to apply a list of modifications to XML
    files (e.g. DD4hep compact files).

    Args:
      modifications: dictionary mapping file path -> list of
                     (xml_path, attribute, unit, new_value)
    """
    for file, parameters in modifications.items():

        tree = ET.parse(file)
        for parameter in parameters:

            path, attribute, units, value = parameter
            element = tree.getroot().find(path)
            print(f"CHECK CHECK element = {element}")

            if units != '':
                element.set(attribute, "{}*{}".format(value, units))
            else:
                element.set(attribute, "{}".format(value))

        # save edits and exit
        tree.write(file)
