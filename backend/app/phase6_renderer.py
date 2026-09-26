"""V6-compatible, server-rendered CMS adapter.

Keeps the approved V6 shell and CSS; author-controlled content is never executed
as HTML or scripts. New sections use predefined, safe V6 classes. Publishing
remains a private staging release until a separate production readiness gate.
"""
from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path
from urllib.parse import urlparse
from bs4 import BeautifulSoup, NavigableString, Tag
from sqlalchemy.orm import Session
from .models import MediaAsset, NavigationItem, SiteSetting

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / 'seed' / 'v6_site'



def serialize_html(soup):
    """Keep exactly one HTML5 doctype across render, global chrome and bridge."""
    markup=re.sub(r'(?is)^\s*(?:<!doctype\s+html>\s*)+', '', str(soup))
    return '<!doctype html>\n'+markup

def site_setting(db: Session, key: str, fallback=''):
    row = db.get(SiteSetting, key)
    try: return json.loads(row.value_json) if row else fallback
    except (TypeError, json.JSONDecodeError): return fallback


def safe_local_url(url: str):
    if not isinstance(url, str): return None
    if re.fullmatch(r'/[a-zA-Z0-9/_.%-]*(?:\?[a-zA-Z0-9_=&%-]*)?', url) and not url.startswith('//') and '..' not in url:
        return url
    return None


def text_nodes(fragment):
    """Stable per-section text slots. Preserves <em>, SVG/icons and V6 classes."""
    return [n for n in fragment.descendants if isinstance(n, NavigableString)
            and n.strip() and n.parent and n.parent.name not in ('script','style','svg','title')]


def section_fields(source_html, content):
    soup = BeautifulSoup(source_html or '', 'html.parser')
    nodes = text_nodes(soup)
    text_map = content.get('text_overrides') or {}
    images = content.get('image_overrides') or {}
    result = [{'key':f'text_{i}', 'kind':'text', 'tag':n.parent.name,
               'value':str(text_map.get(f'text_{i}',n)), 'original':str(n),
               'context':n.parent.get('class',[])} for i,n in enumerate(nodes)]
    result += [{'key':f'image_{i}', 'kind':'image', 'alt':(content.get('alt_overrides') or {}).get(f'image_{i}',img.get('alt','')),
                'value':images.get(f'image_{i}',img.get('src','')), 'original':img.get('src','')}
               for i,img in enumerate(soup.find_all('img'))]
    result += [{'key':f'icon_{i}', 'kind':'icon', 'value':(content.get('icon_overrides') or {}).get(f'icon_{i}',''), 'original':'Original V6 line icon'} for i,_ in enumerate(soup.find_all('svg'))]
    result += [{'key':f'link_{i}', 'kind':'link', 'value':(content.get('link_overrides') or {}).get(f'link_{i}',a.get('href','')),
                'original':a.get('href',''), 'text':a.get_text(' ',strip=True)}
               for i,a in enumerate(soup.find_all('a',href=True))]
    return result


def clean_fragment(raw):
    """Narrow HTML sanitization for advanced source editing. No JS/style injection."""
    soup = BeautifulSoup(str(raw)[:200000], 'html.parser')
    for node in soup.find_all(['script','iframe','object','embed','form','style','base','meta','link','svg']): node.decompose()
    allowed={'section','div','article','header','footer','nav','figure','figcaption','p','h1','h2','h3','h4',
             'ul','ol','li','a','img','em','strong','span','small','br','blockquote','hr','b','i','time'}
    for tag in list(soup.find_all(True)):
        if tag.name not in allowed:
            tag.unwrap();continue
        safe={}
        for k,v in dict(tag.attrs).items():
            if k in ('class','id') and isinstance(v,(str,list)):
                value=' '.join(v) if isinstance(v,list) else v
                if re.fullmatch(r'[a-zA-Z0-9 _-]{1,200}',value):safe[k]=value
            elif k in ('width','height') and str(v).isdigit() and int(v)<=4096:safe[k]=str(v)
            elif k=='alt' and tag.name=='img':safe[k]=str(v)[:300]
            elif k=='loading' and tag.name=='img' and v in ('lazy','eager'):safe[k]=v
            elif k=='href' and tag.name=='a':
                val=safe_local_url(v)
                if val:safe[k]=val
            elif k=='src' and tag.name=='img':
                val=safe_local_url(v)
                if val and val.startswith('/assets/'):safe[k]=val
            elif k=='role' and str(v) in ('img','list','listitem'):safe[k]=str(v)
            elif k.startswith('aria-') and re.fullmatch(r'[a-z-]{1,45}',k):safe[k]=str(v)[:200]
        tag.attrs=safe
    return str(soup)


def render_section_fragment(section:dict, *, known_route:bool=True):
    content=section.get('content') or {}
    if not section.get('enabled',True):return ''
    raw=content.get('html','')
    if raw:
        # Original approved V6 HTML and edited HTML both sanitized to safe tag/attr
        # sets. The existing SVG artwork is permitted ONLY from the original seed.
        source=raw if known_route else clean_fragment(raw)
        soup=BeautifulSoup(source,'html.parser')
        if known_route:
            # Content is not assumed to be trusted even if originally imported.
            # Strictly reject new dangerous elements/attributes while preserving
            # the original V6 inline icon SVG and background gradients.
            for danger in soup.select('script,iframe,object,embed,form,style'):
                danger.decompose()
            for tag in soup.find_all(True):
                for attr in list(tag.attrs):
                    if attr.lower().startswith('on') or attr.lower() in ('srcdoc','formaction'):del tag.attrs[attr]
                for attr in ('src','href'):
                    if tag.has_attr(attr) and isinstance(tag[attr],str):
                        val=tag[attr]
                        if not (safe_local_url(val) or val.startswith('#')): del tag.attrs[attr]
        for i,node in enumerate(text_nodes(soup)):
            key=f'text_{i}'
            if key in (content.get('text_overrides') or {}):
                text=str(content['text_overrides'][key])[:12000]
                node.replace_with(NavigableString(text))
        # Structured editor headings/intro are editable as well as every text slot.
        if isinstance(content.get('heading'),str) and content.get('heading')!=content.get('original_heading',content.get('heading')):
            headline=soup.find(['h1','h2'])
            if headline:headline.string=content['heading'][:500]
        if isinstance(content.get('description'),str):
            intro=soup.select_one('.hero-lead, .lead, .sublead')
            if intro:intro.string=content['description'][:3000]
        if isinstance(content.get('eyebrow'),str):
            eyebrow=soup.select_one('.eyebrow')
            if eyebrow:eyebrow.string=content['eyebrow'][:160]
        for i,img in enumerate(soup.find_all('img')):
            entry=(content.get('image_overrides') or {}).get(f'image_{i}')
            if isinstance(entry,str) and entry.startswith('/assets/') and safe_local_url(entry):img['src']=entry
            alt=(content.get('alt_overrides') or {}).get(f'image_{i}')
            if isinstance(alt,str):img['alt']=alt[:300]
        for i,svg in enumerate(list(soup.find_all('svg'))):
            value=(content.get('icon_overrides') or {}).get(f'icon_{i}')
            if isinstance(value,str) and value.startswith('/assets/media/') and safe_local_url(value):
                icon=soup.new_tag('img',src=value,alt='',role='presentation',width='48',height='48')
                icon['class']='cms-custom-icon';svg.replace_with(icon)
        for i,a in enumerate(soup.find_all('a',href=True)):
            entry=(content.get('link_overrides') or {}).get(f'link_{i}')
            if entry and safe_local_url(entry):a['href']=entry
        if soup.find('section'):
            soup.find('section')['data-cms-section']=section['key']
        return str(soup)
    tag='h1' if section.get('type')=='hero' else 'h2'
    heading=html.escape(str(content.get('heading','')))
    desc=html.escape(str(content.get('description',content.get('text',''))))
    return f'<section class="section"><div class="wrap"><div class="section-head"><{tag}>{heading}</{tag}><p class="lead">{desc}</p></div></div></section>'


def seo_update(soup, snap, base, *, staging=True):
    head=soup.head
    if not head:return
    route=snap['route']; seo=snap['seo']
    canonical=seo.get('canonical_override') or base+route
    if not (urlparse(canonical).scheme=='https' and urlparse(canonical).hostname):canonical=base+route
    robots=('index' if seo.get('robots_index') else 'noindex')+(',follow' if seo.get('robots_follow') else ',nofollow')
    intended=robots
    if staging:robots='noindex,nofollow'
    def meta(name,value,property=False):
        attrs={'property' if property else 'name':name}
        tag=head.find('meta',attrs=attrs)
        if not tag:tag=soup.new_tag('meta',attrs=attrs);head.append(tag)
        tag['content']=str(value or '')
        return tag
    title=seo.get('seo_title') or snap['title']
    if head.title:head.title.string=title
    else:tag=soup.new_tag('title');tag.string=title;head.append(tag)
    meta('description',seo.get('meta_description',''))
    robot=meta('robots',robots)
    if staging:robot['data-planned-robots']=intended
    else:robot.attrs.pop('data-planned-robots',None)
    link=head.find('link',rel='canonical')
    if not link:link=soup.new_tag('link',rel='canonical');head.append(link)
    link['href']=canonical
    meta('og:type','article' if snap.get('template')=='article' else 'website',True)
    meta('og:title',seo.get('og_title') or title,True)
    meta('og:description',seo.get('og_description') or seo.get('meta_description',''),True)
    meta('og:url',canonical,True)
    meta('twitter:card','summary_large_image')
    og=snap.get('og_image_url')
    if og:meta('og:image',og,True)
    schema={'@context':'https://schema.org','@type':seo.get('schema_type') or 'WebPage',
            'name':title,'description':seo.get('meta_description',''),'url':canonical}
    structured=head.find('script',attrs={'type':'application/ld+json'})
    if structured:structured.string=json.dumps(schema,ensure_ascii=False).replace('<','\\u003c')


def update_global_chrome(soup,db):
    nav=soup.select_one('nav.desktop-nav');mobile=soup.select_one('nav.mobile-nav')
    links=db.query(NavigationItem).filter_by(location='header',is_visible=True).order_by(NavigationItem.position).all()
    if nav and links:
        nav.clear()
        for item in links:
            link=soup.new_tag('a',href=safe_local_url(item.url) or '/');link.string=item.label
            if item.open_new_tab:link['target']='_blank';link['rel']='noopener noreferrer'
            nav.append(link)
    if mobile and links:
        mobile.clear()
        for item in links:
            link=soup.new_tag('a',href=safe_local_url(item.url) or '/');link.string=item.label;mobile.append(link)
        if not any(item.url=='/assessment/' for item in links):
            link=soup.new_tag('a',href='/assessment/');link.string='Business Optimization Check';mobile.append(link)
    label=site_setting(db,'contact.primary_cta_label','Request a strategy call')
    url=safe_local_url(site_setting(db,'contact.primary_cta_url','/contact/')) or '/contact/'
    for item in soup.select('.btn-nav'):
        item.clear();item.append(str(label)+' ↗');item['href']=url
    for img in soup.select('header .brand img, footer .footer-about img'):
        key='brand.logo_light' if img.find_parent('footer') else 'brand.logo_dark'
        image=safe_local_url(site_setting(db,key,'/assets/logo.svg'))
        if image and image.startswith('/assets/'):img['src']=image
        img['alt']=str(site_setting(db,'brand.display_name','Auvorent Advisory'))[:180]
    tagline=site_setting(db,'brand.tagline','')
    footer=soup.select_one('footer .footer-about p')
    if footer and isinstance(tagline,str):footer.string=tagline
    copyright_value=site_setting(db,'footer.copyright','')
    bottom=soup.select_one('footer .footer-bottom span')
    if bottom and isinstance(copyright_value,str):bottom.string=copyright_value
    footlinks=db.query(NavigationItem).filter_by(location='footer',is_visible=True).order_by(NavigationItem.position).all()
    if footlinks:
        company=next((x for x in soup.select('footer .footer-grid > div') if x.find('h3') and x.find('h3').get_text(strip=True).lower()=='company'),None)
        if company:
            for child in company.find_all('a'):child.decompose()
            for item in footlinks:
                a=soup.new_tag('a',href=safe_local_url(item.url) or '/');a.string=item.label;company.append(a)


def integrate_page(snap,db,*,base,staging=True):
    route=snap['route'];src=BASELINE/route.lstrip('/')/'index.html' if route!='/' else BASELINE/'index.html'
    if not src.is_file():
        from .phase5 import render_document
        return render_document(snap,base=base,staging=staging)
    soup=BeautifulSoup(src.read_text(encoding='utf-8'),'html.parser')
    main=soup.select_one('main')
    if not main:raise ValueError('V6 page lacks main region: '+route)
    main.clear()
    for section in sorted(snap.get('sections',[]),key=lambda s:s.get('position',0)):
        if not section.get('enabled',True):continue
        content=section.get('content') or {}
        # Existing V6 HTML safely renders in its exact V6 component layout;
        # new CMS section types fall back to the V6 section CSS system.
        original = next((s['content'].get('html') for p in json.loads((ROOT/'seed'/'v6_page_content.json').read_text(encoding='utf8'))['pages'] if p['route']==route for s in p['sections'] if s['section_key']==section['key']),None)
        trusted = original is not None and content.get('html') == original
        if original is not None:
            seed_info=next((s['content'] for p in json.loads((ROOT/'seed'/'v6_page_content.json').read_text(encoding='utf8'))['pages'] if p['route']==route for s in p['sections'] if s['section_key']==section['key']),{})
            section['content']['original_heading']=seed_info.get('heading','')
        fragment=render_section_fragment(section,known_route=trusted)
        for el in BeautifulSoup(fragment,'html.parser').contents:
            main.append(el)
    update_global_chrome(soup,db)
    seo_update(soup,snap,base,staging=staging)
    script=soup.new_tag('script',src='/assets/cms-public.js',defer='')
    soup.head.append(script)
    return serialize_html(soup)


def _safe_editorial_markdown(markdown):
    """Safe subset of article markdown: headings, paragraphs, lists; never raw HTML."""
    output=[]; list_open=False
    for block in re.split(r"\n\s*\n",str(markdown or '')[:45000]):
        block=block.strip()
        if not block:continue
        if block.startswith('### '):tag='h3';value=block[4:].replace('\n',' ')
        elif block.startswith('## '):tag='h2';value=block[3:].replace('\n',' ')
        else:tag='p';value=block.replace('\n',' ')
        output.append(f'<{tag}>{html.escape(value)}</{tag}>')
    return ''.join(output)


def integrate_collection(snap,db,*,base,staging=True):
    """Keep original V6 service/industry/insight templates on collection edits."""
    kind=snap['kind']
    route=('/insights/' if kind=='insight' else '/'+kind+'s/')+snap['slug']+'/'
    src=BASELINE/route.lstrip('/')/'index.html'
    if not src.is_file():
        from .phase5 import render_document
        return render_document({**snap,'route':route},base=base,staging=staging)
    soup=BeautifulSoup(src.read_text(encoding='utf-8'),'html.parser')
    main=soup.select_one('main');title=main.find('h1') if main else None
    if title:
        title.clear();title.append(NavigableString(str(snap['title'])[:250]))
        period=soup.new_tag('span',attrs={'class':'period'});period.string='.';title.append(period)
    lead=main.select_one('.sub-hero .lead') if main else None
    if lead and snap.get('summary'):lead.string=str(snap['summary'])[:1200]
    updated_body=_safe_editorial_markdown(snap.get('body',''))
    if kind=='insight':
        article=main.select_one('.article-body') if main else None
        if article and updated_body:
            # Reuse the original insight layout, header/footer and responsive rules.
            article.clear()
            for node in list(BeautifulSoup(updated_body,'html.parser').contents):article.append(node)
    elif updated_body:
        # Original imported collection body paraphrases original V6 sections.
        # Preserve the approved detailed visual layout until the editor changes
        # that body; only then use the deliberate editorial V6 section layout.
        from .seed_phase3 import markdown_from_html
        seed=json.loads((ROOT/'seed'/'v6_page_content.json').read_text(encoding='utf-8'))['pages']
        original=next((p for p in seed if p['route']==route),None)
        if original is None or snap['body'].strip()!=markdown_from_html(original,kind).strip():
            other=[x for x in main.find_all('section',recursive=False) if x.get('class') and 'sub-hero' not in x['class'] and 'cta-section' not in x['class']]
            for section in other:section.decompose()
            new=soup.new_tag('section',attrs={'class':'section'})
            wrap=soup.new_tag('div',attrs={'class':'wrap article-layout'})
            body=soup.new_tag('div',attrs={'class':'article-body'})
            for node in list(BeautifulSoup(updated_body,'html.parser').contents):body.append(node)
            wrap.append(body);new.append(wrap)
            cta=main.find('section',attrs={'class':'cta-section'},recursive=False)
            if cta:cta.insert_before(new)
            else:main.append(new)
    update_global_chrome(soup,db)
    seo_update(soup,{**snap,'route':route,'template':'article' if kind=='insight' else kind},base,staging=staging)
    return serialize_html(soup)


def copy_baseline(target:Path):
    if not BASELINE.is_dir():raise RuntimeError('Bundled V6 baseline is missing')
    shutil.copytree(BASELINE,target,dirs_exist_ok=True)


def apply_global_changes(target:Path,db,*,base,staging=True):
    """Keep shared navigation/settings consistent on all 19 V6 baseline pages."""
    for src in target.rglob('index.html'):
        if ('assets' in src.parts):continue
        soup=BeautifulSoup(src.read_text(encoding='utf-8'),'html.parser')
        if not soup.select_one('nav.desktop-nav'):continue
        update_global_chrome(soup,db)
        src.write_text(serialize_html(soup),encoding='utf-8')


def copy_media(db:Session, media_root:Path, target:Path):
    output=target/'assets'/'media'
    for media in db.query(MediaAsset).all():
        if '/' in media.storage_name or '\\' in media.storage_name or media.storage_name.startswith('.'):
            raise ValueError('Unsafe stored media name')
        source=media_root/media.storage_name
        if not source.exists():continue
        output.mkdir(exist_ok=True,parents=True)
        shutil.copy2(source,output/media.storage_name)


def write_site_bridge(target:Path,api_origin:str):
    assets=target/'assets';assets.mkdir(exist_ok=True,parents=True)
    script=Path(__file__).resolve().parents[2]/'seed'/'cms-public.js'
    shutil.copy2(script,assets/'cms-public.js')
    # Replace the previous V6 static assessment + contact handlers with the
    # CMS-managed API client; retain its existing mobile nav implementation.
    original=(BASELINE/'assets'/'app.js').read_text(encoding='utf-8')
    nav_only=original.split('  const questions = [')[0]+'})();\n'
    (assets/'app.js').write_text(nav_only,encoding='utf-8')
    parsed_api=urlparse(api_origin)
    if parsed_api.scheme not in ('http','https') or not parsed_api.hostname or parsed_api.username or parsed_api.password or parsed_api.path not in ('','/') or parsed_api.query or parsed_api.fragment:
        raise ValueError('CMS public API must be a validated HTTP(S) origin without credentials or path')
    api_origin=f'{parsed_api.scheme}://{parsed_api.netloc}'.rstrip('/')
    (assets/'cms-config.js').write_text('window.AUVORENT_CMS_API_BASE='+json.dumps(api_origin)+';\n',encoding='utf-8')
    # Cloudflare Pages honours `_headers`; the stock V6 connect-src 'self'
    # otherwise blocks requests to the separately hosted CMS API.
    header_path=target/'_headers'
    if header_path.is_file():
        headers=header_path.read_text(encoding='utf-8')
        headers=re.sub(r"connect-src 'self'(?: [^;]*)?;", f"connect-src 'self' {api_origin};", headers)
        header_path.write_text(headers,encoding='utf-8')
    for page in target.rglob('index.html'):
        soup=BeautifulSoup(page.read_text(encoding='utf-8'),'html.parser')
        if soup.head and soup.select_one('nav.desktop-nav') and not soup.find('script',src='/assets/cms-config.js'):
            tag=soup.new_tag('script',src='/assets/cms-config.js',defer='')
            # Must execute before cms-public.js but after app.js is okay.
            found=soup.find('script',src='/assets/cms-public.js')
            if found:found.insert_before(tag)
            else:soup.head.append(tag);soup.head.append(soup.new_tag('script',src='/assets/cms-public.js',defer=''))
            page.write_text(serialize_html(soup),encoding='utf-8')
