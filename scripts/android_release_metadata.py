"""Parse Android Gradle release metadata without hard-coded old version numbers.

The signed artifact verifier compares the final merged APK manifest against
the reviewed versionCode/versionName in the same source commit.
"""
import re


def expected_version(gradle):
    if not isinstance(gradle, str):
        raise ValueError("Gradle version metadata must be source text.")
    code = re.findall(r"^\s*versionCode\s+([1-9][0-9]*)\s*$", gradle, re.MULTILINE)
    name = re.findall(r"^\s*versionName\s+['\"]([^'\"]+)['\"]\s*$", gradle, re.MULTILINE)
    if len(code) != 1 or len(name) != 1 or len(name[0]) > 64:
        raise ValueError("Android release version must be a unique Gradle constant.")
    return code[0], name[0]
