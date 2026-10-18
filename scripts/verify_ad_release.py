"""Check the final signed artifact, not just Gradle source declarations."""
import sys, zipfile, xml.etree.ElementTree as ET
from pathlib import Path
apk, manifest = map(Path, sys.argv[1:3])
ns='{http://schemas.android.com/apk/res/android}'
root=ET.parse(manifest).getroot();app=root.find('application')
assert root.attrib['package']=='nz.kiwikind.broadband'
assert root.attrib[ns+'versionCode']=='9'
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
for marker in [b'Lcom/google/android/gms/ads/AdView;',b'Lcom/google/android/ump/UserMessagingPlatform;',b'ca-app-pub-4051392846058327/4480562173',b'Lnz/kiwikind/broadband/BannerAds;']:
    assert marker in dex,marker
print('PASS signed V9: real KiwiKind App ID/unit, Ads and UMP SDKs, non-debuggable, backup/cleartext off, AD_ID/AdServices permissions absent.')
