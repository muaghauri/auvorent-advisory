"use strict";
(function(){
  function node(tag, attrs={}, text=null){
    const element=document.createElement(tag);
    for(const [key,value] of Object.entries(attrs)){
      if(key==='className') element.className=value;
      else if(key==='dataset') Object.assign(element.dataset,value);
      else if(key==='type') element.type=value;
      else element.setAttribute(key,String(value));
    }
    if(text!==null) element.textContent=text;
    return element;
  }

  const pane=node('dialog',{id:'phase6-visual-dialog',className:'phase6-modal'});
  const form=node('form',{method:'dialog',className:'visual-shell'});
  const header=node('header');
  const headerCopy=node('div');
  headerCopy.append(
    node('span',{className:'eyebrow'},'PHASE 6 / V6 VISUAL EDITOR'),
    node('h2',{},'Update this section'),
    node('p',{},'Change approved V6 copy, images and links while preserving its responsive layout. Save as draft before review.')
  );
  const close=node('button',{className:'button secondary small',value:'cancel','aria-label':'Close visual editor'},'Close');
  header.append(headerCopy,close);
  const visualFields=node('div',{id:'phase6-fields',className:'visual-fields'});
  const footer=node('footer');
  footer.append(node('button',{type:'button',id:'phase6-save',className:'button primary'},'Save as draft'));
  form.append(header,visualFields,footer);
  pane.append(form);
  document.body.append(pane);

  let current=null,fieldValues=[];
  const parent=document.getElementById('view-publishing');
  if(parent){
    const target=node('section',{className:'table-panel phase6-readiness'});
    const tableHead=node('div',{className:'table-head'});
    const copy=node('div');
    copy.append(
      node('span',{className:'eyebrow'},'PHASE 06 · SITE INTEGRATION'),
      node('h2',{},'Production readiness gates'),
      node('p',{},'Publishing continues to generate private staging releases. Public export requires all external checks below.')
    );
    const refresh=node('button',{type:'button',id:'phase6-refresh',className:'button secondary small'},'Refresh readiness');
    tableHead.append(copy,refresh);
    target.append(
      tableHead,
      node('div',{id:'phase6-checks',className:'phase6-checks'}),
      node('p',{id:'phase6-status',className:'helper'}),
      node('button',{type:'button',id:'phase6-export',className:'button secondary small'},'Export production-ready build')
    );
    parent.append(target);
    refresh.addEventListener('click',load);
    target.querySelector('#phase6-export').addEventListener('click',async()=>{
      if(!confirm('Create a production export only if trademark, legal, SMTP and hosting have been verified?'))return;
      try{
        const result=await api('/integration/export-production',{method:'POST',body:'{}'});
        toast('Production deployment completed: '+(result.export_id||result.source_release||'release'));
        await load();
      }catch(e){toast(messageOf(e),true);}
    });
  }

  const fields=()=>document.getElementById('phase6-fields');
  const heading=(title)=>{const x=document.createElement('h3');x.textContent=title;fields().append(x);};
  function addField(field, media){
    const label=document.createElement('label');const name=document.createElement('span');name.textContent=(field.kind==='text'?`${field.tag.toUpperCase()} · `:field.kind==='image'?'Image · ':field.kind==='icon'?'Icon · ':'Link · ')+(field.text||field.original||field.key).slice(0,125);
    label.append(name);let input;
    if(field.kind==='image'||field.kind==='icon'){
      input=document.createElement('select');input.append(new Option('Keep existing image',field.value));
      media.filter(m=>field.kind==='image'?m.kind!=='icon':m.kind==='icon').forEach(m=>input.append(new Option(m.name+' ('+m.kind+')',m.id)));
      label.append(input);
      if(field.kind==='image'){
        const alt=document.createElement('input');alt.className='phase6-alt';alt.value=field.alt||'';alt.placeholder='Describe this image for accessibility and SEO';alt.maxLength=300;alt.setAttribute('aria-label','Image alt text');
        label.append(alt);label._alt=alt;
      }
    }else{
      input=field.kind==='text'&&field.value.length>90?document.createElement('textarea'):document.createElement('input');
      input.value=field.value;input.maxLength=field.kind==='text'?12000:240;
      if(input.nodeName==='TEXTAREA')input.rows=2;
      label.append(input);
    }
    fields().append(label);
    fieldValues.push({field,input,original:field.value});
  }

  async function open(section){
    current=section;fieldValues=[];fields().replaceChildren();
    try{
      const result=await api(`/integration/sections/${section.id}/fields`);
      if(!result.fields.length){fields().textContent='This section uses a basic content block. Edit its structured JSON in Page Studio.';}
      for(const kind of ['text','image','icon','link']){
        const matching=result.fields.filter(x=>x.kind===kind);if(!matching.length)continue;
        heading(kind==='text'?'Text & headings':kind==='image'?'Images':kind==='icon'?'Custom line/filled icons':'Navigation and CTA links');
        matching.forEach(f=>addField(f,result.media));
      }
      pane.showModal();
    }catch(e){toast(messageOf(e),true);}
  }

  pane.querySelector('#phase6-save').addEventListener('click',async()=>{
    if(!current)return;
    const data={text_overrides:{},image_overrides:{},icon_overrides:{},alt_overrides:{},link_overrides:{}};
    for(const row of fieldValues){
      const value=row.input.value;
      if(value!==row.original)data[row.field.kind+'_overrides'][row.field.key]=value;
      if(row.field.kind==='image'&&row.input.parentNode._alt&&row.input.parentNode._alt.value!==row.field.alt){data.alt_overrides[row.field.key]=row.input.parentNode._alt.value;}
    }
    try{
      await api(`/integration/sections/${current.id}/visual`,{method:'PATCH',body:JSON.stringify(data)});
      pane.close();toast('Visual changes saved as draft. Obtain independent approval before publishing.');
      if(window.state?.selectedPage)await selectPage(window.state.selectedPage.id);
      else if(typeof state!=='undefined'&&state.selectedPage)await selectPage(state.selectedPage.id);
    }catch(e){toast(messageOf(e),true);}
  });

  async function load(){const box=document.getElementById('phase6-checks');if(!box)return;
    try{const report=await api('/integration/readiness');box.replaceChildren();
      Object.entries(report.checks).forEach(([key,value])=>{const span=document.createElement('div');span.className='phase6-check '+(value?'passed':'pending');const badge=document.createElement('span');badge.textContent=value?'✓':'!';const text=document.createElement('span');text.textContent=key.replaceAll('_',' ');span.append(badge,text);box.append(span);});
      document.getElementById('phase6-status').textContent=report.ready?'Ready for guarded production export; verify the resulting files before hosting.':'Public export is intentionally disabled until all readiness checks pass.';
    }catch(e){toast(messageOf(e),true);}
  }
  window.p6={open,load};
})();
