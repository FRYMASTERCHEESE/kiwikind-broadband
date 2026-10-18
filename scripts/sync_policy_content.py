"""Bundle the existing public policy prose for offline native rendering."""
from html.parser import HTMLParser
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]
class Policy(HTMLParser):
    def __init__(self, section=None):
        super().__init__(); self.section=section; self.inside=False; self.depth=0; self.tag=None; self.parts=[]; self.blocks=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if (self.section and tag=='section' and attrs.get('id')==self.section) or (not self.section and tag=='main'):
            self.inside=True
        if self.inside and tag in ('h1','h2','h3','p'):
            self.tag=tag;self.parts=[]
    def handle_data(self,text):
        if self.inside and self.tag:self.parts.append(text)
    def handle_endtag(self,tag):
        if self.inside and self.tag==tag:
            self.blocks.append({'kind':tag,'text':' '.join(''.join(self.parts).split())});self.tag=None
        if self.inside and tag==('section' if self.section else 'main'):self.inside=False

out={}
for key,file,section in [('privacy','privacy.html',None),('deletion','account-deletion.html',None),('terms','index.html','terms')]:
    p=Policy(section);p.feed((ROOT/'site/dist'/file).read_text(encoding='utf-8'));out[key]=p.blocks
(ROOT/'android/app/src/main/assets/policy-content.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
