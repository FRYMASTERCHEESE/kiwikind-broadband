"""No SDK, payment or customer access: metadata parsing regression for signed releases."""
from pathlib import Path
from django.test import SimpleTestCase
from scripts.android_release_metadata import expected_version


class AndroidReleaseMetadataTests(SimpleTestCase):
    def test_actual_version_code_and_name_are_read_from_gradle(self):
        gradle = Path('android/app/build.gradle').read_text()
        code, name = expected_version(gradle)
        self.assertEqual(code, '15')
        self.assertEqual(name, '0.2.13-closed-test')

    def test_distinct_valid_versions_work_without_changing_verifier(self):
        self.assertEqual(expected_version("versionCode 15\nversionName '0.2.13-closed-test'\n"),
                         ('15','0.2.13-closed-test'))
        self.assertEqual(expected_version("  versionCode 101\n  versionName \"1.0\"\n"),
                         ('101','1.0'))

    def test_rejects_missing_dynamic_and_conflicting_metadata(self):
        for snippet in (
            "", "versionCode 0\nversionName 'x'\n",
            "versionCode secret\nversionName 'x'\n",
            "versionCode 15\nversionName System.getenv('NAME')\n",
            "versionCode 14\nversionCode 13\nversionName 'x'\n",
            "versionCode 14\nversionName 'x'\nversionName 'y'\n",
        ):
            with self.subTest(snippet=snippet), self.assertRaises(ValueError):
                expected_version(snippet)
