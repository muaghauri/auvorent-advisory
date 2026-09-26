"""Run after private staging build or a gated production export.
Usage: python scripts/verify_release.py /path/to/exported-site
"""
from __future__ import annotations
import argparse
from pathlib import Path
from bs4 import BeautifulSoup


def scan(root):
    errors=[];pages=sorted(root.rglob('index.html'));images=0
    if not pages:return ['No pages found'],0,0
    for file in pages:
        doc=BeautifulSoup(file.read_text(encoding='utf8'),'html.parser')
        route='/' + str(file.parent.relative_to(root)).strip('.')+'/' if file.parent!=root else '/'
        if not doc.title: errors.append(route+': missing page title')
        if not doc.find('link',rel='canonical'):errors.append(route+': canonical missing')
        if not doc.find('meta',attrs={'name':'description'}):errors.append(route+': description missing')
        if not doc.find('main'):errors.append(route+': no main region')
        for img in doc.select('img'):
            images+=1
            if not img.has_attr('alt'):errors.append(route+': image missing alt attribute')
            src=img.get('src','')
            if src.startswith('/assets/') and not (root/src.lstrip('/')).is_file():
                errors.append(route+': missing asset '+src)
        if doc.select_one('script:not([src]):not([type="application/ld+json"])'):
            errors.append(route+': unexpected inline script')
    for file in ['robots.txt','sitemap.xml','assets/style.css','assets/cms-public.js','assets/cms-config.js']:
        if not (root/file).is_file():errors.append('missing '+file)
    return errors,len(pages),images

if __name__=='__main__':
    arg=argparse.ArgumentParser();arg.add_argument('directory',type=Path);args=arg.parse_args()
    errors,pages,images=scan(args.directory)
    print(f'Checked {pages} pages and {images} image references')
    for error in errors:print('ERROR:',error)
    if not errors:print('PASS: structure, SEO and referenced local assets')
    raise SystemExit(bool(errors))
