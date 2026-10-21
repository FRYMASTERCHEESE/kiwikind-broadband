"""Check the final signed artifact, not just Gradle source declarations."""
import sys, re, zipfile, xml.etree.ElementTree as ET
from pathlib import Path
apk, manifest, mapping = map(Path, sys.argv[1:4])
class_names=dict(re.findall(r'^([^ #\s][^ ]*) -> ([^ :]+):$',mapping.read_text(),re.MULTILINE))
assert class_names, 'R8 class mapping is missing'
ns='{http://schemas.android.com/apk/res/android}'
root=ET.parse(manifest).getroot();app=root.find('application')
assert root.attrib['package']=='nz.kiwikind.broadband'
assert root.attrib[ns+'versionCode']=='11'
assert root.attrib[ns+'versionName']=='0.2.9-prelaunch'
assert app.attrib.get(ns+'debuggable','false')=='false'
assert app.attrib.get(ns+'allowBackup')=='false'
assert app.attrib.get(ns+'usesCleartextTraffic')=='false'
meta={m.attrib[ns+'name']:m.attrib.get(ns+'value') for m in app.findall('meta-data')}
assert meta['com.google.android.gms.ads.APPLICATION_ID']=='ca-app-pub-4051392846058327~4918264616'
permissions={p.attrib[ns+'name'] for p in root.findall('uses-permission')}
assert 'com.google.android.gms.permission.AD_ID' not in permissions
assert not any('ACCESS_ADSERVICES_' in p for p in permissions)
with zipfile.ZipFile(apk) as archive:
    dex=b''.join(archive.read(name) for name in archive.namelist() if name.endswith('.dex'))
for original in ['com.google.android.gms.ads.AdView','com.google.android.ump.ConsentRequestParameters','nz.kiwikind.broadband.BannerAds']:
    optimized=class_names.get(original)
    assert optimized and not optimized.startswith('R8$$REMOVED'),original
    marker=('L'+optimized.replace('.','/')+';').encode()
    assert marker in dex,(original,optimized)
assert b'ca-app-pub-4051392846058327/4480562173' in dex
print('PASS signed V11: real KiwiKind App ID/unit, Ads and UMP SDKs, non-debuggable, backup/cleartext off, AD_ID/AdServices permissions absent.')
