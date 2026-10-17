from html.parser import HTMLParser
from pathlib import Path
import json, hashlib, argparse

args=argparse.ArgumentParser(description='Bundle approved website copy for native rendering')
args.add_argument('website', type=Path, help='Approved website index.html')
source_path=args.parse_args().website

class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []
    def text(self):
        return ' '.join(' '.join(c.text() if isinstance(c, Node) else c for c in self.children).split())
    def find(self, tag):
        return [c for c in self.children if isinstance(c, Node) and c.tag == tag] + [n for c in self.children if isinstance(c, Node) for n in c.find(tag)]

class Parser(HTMLParser):
    def __init__(self):
        super().__init__(); self.root=Node(); self.stack=[self.root]
    def handle_starttag(self, tag, attrs):
        n=Node(tag,attrs); self.stack[-1].children.append(n)
        if tag not in ('meta','link','br','input','img','hr'): self.stack.append(n)
    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag==tag: self.stack=self.stack[:i]; break
    def handle_data(self, data): self.stack[-1].children.append(data)

source=source_path.read_bytes()
p=Parser(); p.feed(source.decode('utf-8'))
sections=[]
def blocks(n):
    out=[]
    for c in n.children:
        if not isinstance(c,Node): continue
        if c.tag in ('p','h1','h2','h3','strong','b','summary'):
            out.append({'kind':c.tag,'text':c.text()})
        elif c.tag=='details':
            out.append({'kind':'faq','text':c.find('summary')[0].text(),'answer':'\n\n'.join(x.text() for x in c.find('p'))})
        elif c.attrs.get('class') not in ('illustration','account-actions'):
            out.extend(blocks(c))
    return out
for n in p.root.find('section'):
    sections.append({'id':n.attrs.get('id'),'blocks':blocks(n)})
notice=next(n for n in p.root.find('div') if n.attrs.get('class')=='notice')
sections[0]['blocks'].extend(blocks(notice))
out={'source':'https://frymastercheese.github.io/kiwikind-broadband-website/','sha256':hashlib.sha256(source).hexdigest(),'sections':sections}
(Path(__file__).resolve().parents[1]/'android/app/src/main/assets/website-content.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
