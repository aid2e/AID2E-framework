"""Extract objective from a file

Defines small function to extract
a specified value from a JSON file.

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
"""
import json

def ExtractObjective(*, extra_args, **_):
    """Extract objective

       Extracts a metric based from the JSON file
       written by CalculateHitAngReso. The key
       of the value to extract and the path to
       the JSON file must be provided through
       the `extra_args` block.

       Args:
           extra_args: dictionary of extra arugments
                       must contain `key` and `file`
       Returns:
           extracted metric formatted as a dictionary
    """
    if 'key' not in extra_args:
        raise KeyError(f"'key' not found in extra_args! extra_args = {extra_args}")

    if 'file' not in extra_args:
        raise KeyError(f"'file' not found in extra_args! extra_args = {extra_args}")
    key  = extra_args['key']
    file = extra_args['file']

    metrics = {}
    with open(file, 'r') as f:
        data         = json.load(f)
        value        = data[key]
        metrics[key] = value
    return metrics
