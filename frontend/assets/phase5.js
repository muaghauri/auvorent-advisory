"use strict";
/* Phase 5: SEO, reviews, private preview, immutable local staging. */
window.p5=(()=>{
  const $5=id=>document.getElementById(id);
  const node=(tag,txt,cls)=>{const e=document.createElement(tag);if(txt!==undefined&&txt!==null)e.textContent=txt;if(cls)e.className=cls;return e;};
  const req=(path,method='GET',body)=>api(path,{method,...(body===undefined?{}:{body:JSON.stringify(body)})});
  const p5={tab:'seo',selected:null,entities:[],meta:null,canEdit:false,canApprove:false,canPublish:false};
  const error=e=>toast(messageOf(e),true);
  const short=s=>s?.length>45?s.slice(0,42)+'…':s;
  function applyUser(user){
    const valid=!user.must_change_password;
    p5.canEdit=valid&&['super_admin','admin','editor'].includes(user.role);
    p5.canApprove=valid&&['super_admin','admin','reviewer'].includes(user.role);
    p5.canPublish=valid&&['super_admin','admin'].includes(user.role);
    show($5('publishing-tab'),valid);
    ['p5-save-seo','p5-submit-review'].forEach(id=>{if($5(id))show($5(id),p5.canEdit);});
    ['p5-build','p5-run-due','p5-schedule'].forEach(id=>{if($5(id))$5(id).disabled=!p5.canPublish;});
    show($5('p5-redirect-form'),p5.canEdit);
  }
  async function load(){
    try{
      const [entries,issues,reviews,current]=await Promise.all([
        req('/publishing/entities'),req('/seo-issues'),req('/reviews'),req('/publishing/current')]);
      p5.entities=entries.items;p5.issues=issues;p5.reviews=reviews.items;
      $5('p5-total').textContent=issues.total;
      $5('p5-errors').textContent=issues.with_errors;
      $5('p5-pending').textContent=reviews.items.filter(x=>x.state==='in_review').length;
      $5('p5-current').textContent=current.release_id?current.release_id.slice(0,8):'Not built';
      fillSelect();drawEntities();switchTab(p5.tab);
      if(p5.selected)await select(p5.selected.type,p5.selected.id);
    }catch(e){error(e);}
  }
  function switchTab(tab){
    p5.tab=tab;
    for(const name of ['seo','reviews','publish','redirects']){
      show($5('p5-'+name),name===tab);
      const b=document.querySelector('[data-p5-tab="'+name+'"]');b.classList.toggle('active',name===tab);
      b.setAttribute('aria-selected',String(name===tab));
    }
    if(tab==='reviews')drawReviews();
    if(tab==='publish')loadDeployments().catch(error);
    if(tab==='redirects')loadRedirects().catch(error);
  }
  function fillSelect(){
    const select=$5('p5-review-target');const old=select.value;select.replaceChildren();
    for(const x of p5.entities){
      const o=node('option',x.title+' · '+x.type+' · '+x.status);o.value=x.type+':'+x.id;
      if(o.value===old)o.selected=true;select.append(o);
    }
  }
  function drawEntities(){
    const q=$5('p5-search').value.toLowerCase();const box=$5('p5-content-list');box.replaceChildren();
    for(const x of p5.entities.filter(x=>(x.title+' '+x.route+' '+x.type).toLowerCase().includes(q))){
      const btn=node('button',null,'p5-entry'+(p5.selected?.id===x.id?' selected':''));btn.type='button';
      btn.append(node('strong',x.title),node('small',x.route+' · '+x.type+' · '+x.status));
      btn.addEventListener('click',()=>select(x.type,x.id).catch(error));box.append(btn);
    }
  }
  function drawIssues(report){
    const box=$5('p5-issues');box.replaceChildren();
    box.append(node('h3','SEO validation · '+report.errors+' blocking · '+report.warnings+' advisory'));
    if(!report.issues.length)box.append(node('p','No SEO issues reported.'));
    for(const x of report.issues){const e=node('p',x.message,'p5-issue '+x.level);e.prepend(node('strong',x.level.toUpperCase()+': '));box.append(e);}
  }
  async function select(type,id){
    const x=p5.entities.find(x=>x.type===type&&x.id===id);if(!x)return;
    p5.selected=x;drawEntities();
    const d=await req('/seo/'+type+'/'+id);p5.meta=d.seo;
    $5('p5-selection').textContent=x.title;
    $5('p5-seo-title').value=d.seo.seo_title||'';
    $5('p5-meta-description').value=d.seo.meta_description||'';
    $5('p5-canonical').value=d.seo.canonical_override||'';
    $5('p5-index').checked=!!d.seo.robots_index;
    $5('p5-follow').checked=!!d.seo.robots_follow;
    $5('p5-og-title').value=d.seo.og_title||'';
    $5('p5-og-description').value=d.seo.og_description||'';
    $5('p5-schema').value=d.seo.schema_type||'WebPage';
    $5('p5-breadcrumb').value=d.seo.breadcrumb_title||'';
    const images=await req('/media?limit=150');const sel=$5('p5-og-image');sel.replaceChildren(node('option','None'));
    sel.firstChild.value='';
    for(const file of images.items.filter(f=>['image','brand'].includes(f.kind))){const option=node('option',file.original_name);option.value=file.id;sel.append(option);}
    sel.value=d.seo.og_image_media_id||'';
    drawIssues(d.validation);previewSearch();show($5('p5-seo-form'),true);
    await loadVersions(type,id);
    Array.from($5('p5-seo-form').querySelectorAll('input,textarea,select')).forEach(el=>{el.disabled=!p5.canEdit;});
    $5('p5-preview').disabled=false;
  }
  function previewSearch(){
    if(!p5.selected)return;
    const m=$5('p5-seo-title').value||p5.selected.title;
    $5('p5-preview-title').textContent=short(m);
    $5('p5-preview-description').textContent=$5('p5-meta-description').value||'Write a specific description of this page.';
    $5('p5-preview-url').textContent='https://auvorent.com'+p5.selected.route;
  }
  async function loadVersions(type,id){
    const box=$5('p5-versions');box.replaceChildren();
    const d=await req('/publishing/versions/'+type+'/'+id);
    if(!d.items.length){box.append(node('p','No earlier versions recorded.','helper'));return;}
    for(const v of d.items){
      const row=node('div',null,'p5-version');row.append(node('small',v.type+' · '+v.created_at.slice(0,16)+' UTC'));
      if(p5.canEdit){const b=node('button','Restore','button secondary small');b.type='button';
        b.addEventListener('click',async()=>{if(!confirm('Restore this content version? A new approval will be required.'))return;
          try{await req('/publishing/versions/'+v.id+'/restore','POST');toast('Revision restored as draft');await load();}
          catch(e){error(e);}});row.append(b);}
      box.append(row);
    }
  }
  async function saveSeo(e){
    e.preventDefault();if(!p5.selected||!p5.canEdit)return;
    const data={seo_title:$5('p5-seo-title').value,meta_description:$5('p5-meta-description').value,
      canonical_override:$5('p5-canonical').value,robots_index:$5('p5-index').checked,robots_follow:$5('p5-follow').checked,
      og_title:$5('p5-og-title').value,og_description:$5('p5-og-description').value,
      og_image_media_id:$5('p5-og-image').value||null,schema_type:$5('p5-schema').value,breadcrumb_title:$5('p5-breadcrumb').value};
    try{const result=await req('/seo/'+p5.selected.type+'/'+p5.selected.id,'PUT',data);drawIssues(result.validation);toast('SEO draft saved. Approval is required before staging publication.');await load();}catch(e){error(e);}
  }
  async function privatePreview(){
    if(!p5.selected)return;
    const popup=window.open('about:blank','_blank');
    try{const d=await req('/preview/'+p5.selected.type+'/'+p5.selected.id,'POST');
      const url=new URL(d.preview_url,location.origin);
      if(popup)popup.location.href=url.href;else window.open(url.href,'_blank');
    }catch(e){if(popup)popup.close();error(e);}
  }
  async function submit(){
    if(!p5.canEdit)return;
    const [kind,id]=$5('p5-review-target').value.split(':');
    try{await req('/reviews/'+kind+'/'+id+'/submit','POST',{note:$5('p5-review-note').value});toast('Review requested. A separate reviewer must approve.');await load();switchTab('reviews');}catch(e){error(e);}
  }
  function drawReviews(){
    const box=$5('p5-review-list');box.replaceChildren();
    if(!p5.reviews?.length){box.append(node('p','No reviews yet.','empty-state'));return;}
    for(const review of p5.reviews){
      const x=p5.entities.find(x=>x.id===review.entity_id);
      const card=node('article',null,'p5-review');
      card.append(node('strong',x?.title||review.entity_type),node('small',review.state.replaceAll('_',' ')+' · '+review.requested_at.slice(0,16)+' UTC'));
      if(review.note)card.append(node('p',review.note));
      if(review.state==='in_review'&&p5.canApprove){
        const row=node('div',null,'p5-inline-actions');
        for(const decision of ['approve','reject']){
          const b=node('button',decision==='approve'?'Approve':'Request changes',decision==='approve'?'button primary small':'button secondary small');
          b.type='button';b.addEventListener('click',async()=>{
            const note=decision==='reject'?window.prompt('What changes are needed?','')||'Revisions requested':'Approved after editorial and accuracy review';
            try{await req('/reviews/'+review.id+'/decision','POST',{decision,note});toast('Editorial decision recorded');await load();switchTab('reviews');}catch(e){error(e);}
          });row.append(b);
        }card.append(row);
      }
      box.append(card);
    }
  }
  async function loadDeployments(){
    const data=await req('/publishing/deployments');const box=$5('p5-deployments');box.replaceChildren();
    if(!data.items.length){box.append(node('p','No staging builds yet.','empty-state'));return;}
    for(const d of data.items){
      const card=node('article',null,'p5-review');card.append(node('strong',d.release_id?.slice(0,8)||'Scheduled / rollback'),
        node('small',d.status+' · '+d.created_at.slice(0,16)+' UTC'));
      if(d.error_message)card.append(node('p',d.error_message,'p5-issue error'));
      if(d.report?.published_count)card.append(node('p',d.report.published_count+' content items · '+d.report.sitemap_url_count+' sitemap URLs'));
      if(d.status==='completed'&&d.release_id&&p5.canPublish){
        const b=node('button','Restore this release','button secondary small');b.type='button';
        b.addEventListener('click',async()=>{if(!window.confirm('Restore this local staging release?'))return;
          try{await req('/publishing/rollback/'+d.release_id,'POST');toast('Local staging release restored');await load();switchTab('publish');}catch(e){error(e);}});card.append(b);
      }box.append(card);
    }
  }
  async function build(){
    if(!p5.canPublish)return;
    let body={};const date=$5('p5-schedule').value;
    if(date){const parsed=new Date(date);if(Number.isNaN(parsed.getTime())){toast('Invalid scheduled date',true);return;}body.scheduled_for=parsed.toISOString();}
    $5('p5-build').disabled=true;
    try{const result=await req('/publishing/build','POST',body);
      $5('p5-build-result').textContent=result.deployment.status==='failed'?result.deployment.error_message:result.deployment.status;
      toast(result.deployment.status==='completed'?'Staging release created':'Publish job '+result.deployment.status,result.deployment.status==='failed');
      await load();switchTab('publish');
    }catch(e){error(e);}finally{$5('p5-build').disabled=!p5.canPublish;}
  }
  async function loadRedirects(){
    const d=await req('/redirects');const box=$5('p5-redirects-list');box.replaceChildren();
    if(!d.items.length){box.append(node('p','No redirect rules configured.','empty-state'));return;}
    for(const r of d.items){const card=node('article',null,'p5-review');card.append(node('strong',r.old_path+' → '+r.new_path),node('small',String(r.status_code)));
      if(p5.canEdit){const b=node('button','Remove','button secondary small');b.type='button';b.addEventListener('click',async()=>{
        if(!confirm('Delete redirect?'))return;try{await req('/redirects/'+r.id,'DELETE');await loadRedirects();}catch(e){error(e);}});card.append(b);}
      box.append(card);
    }
  }
  async function addRedirect(e){e.preventDefault();
    try{await req('/redirects','POST',{old_path:$5('p5-redirect-old').value,new_path:$5('p5-redirect-new').value,
      status_code:Number($5('p5-redirect-status').value),note:$5('p5-redirect-note').value,is_active:true});
      e.target.reset();toast('Redirect added to local staging configuration');await loadRedirects();}catch(e){error(e);}
  }
  function attach(){
    document.querySelectorAll('[data-p5-tab]').forEach(b=>b.addEventListener('click',()=>switchTab(b.dataset.p5Tab)));
    $5('p5-search').addEventListener('input',drawEntities);
    $5('p5-seo-form').addEventListener('submit',saveSeo);
    ['p5-seo-title','p5-meta-description'].forEach(id=>$5(id).addEventListener('input',previewSearch));
    $5('p5-preview').addEventListener('click',privatePreview);
    $5('p5-submit-review').addEventListener('click',submit);
    $5('p5-refresh-reviews').addEventListener('click',load);
    $5('p5-build').addEventListener('click',build);
    $5('p5-view-staging').addEventListener('click',()=>window.open('/api/v1/publishing/site/','_blank')); 
    $5('p5-run-due').addEventListener('click',async()=>{try{const d=await req('/publishing/run-due','POST');toast(d.items.length+' scheduled job(s) processed');await load();switchTab('publish');}catch(e){error(e);}});
    $5('p5-redirect-form').addEventListener('submit',addRedirect);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',attach);else attach();
  return {applyUser,load};
})();
