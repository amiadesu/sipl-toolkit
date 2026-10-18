import re
import sipl

def test_version_is_semver():
    # MAJOR.MINOR.PATCH with optional suffix (.dev0, rc1, etc.)
    assert re.fullmatch(r"\d+\.\d+\.\d+(\S*)", sipl.__version__)
