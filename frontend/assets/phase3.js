"use strict";
/* Phase 3: controlled collections and secure media operations. No HTML injection. */
(() => {
  const KIND_LABELS = {service:"Services",industry:"Industries",insight:"Insights",author:"Authors",case_study:"Case studies",team_member:"Team members"};
  const kinds = Object.keys(KIND_LABELS);
  const p3state = {kind:"service",items:[],selected:null,media:[],selectedMedia:null,mediaFilter:"",targetEntries:[],pages:[],editable:false};
  const option = (label,value,selected=false) => {const item=document.createElement("option");item.textContent=label;item.value=value;item.selected=selected;return item;};
  const formatted = (value) => String(value||"").replaceAll("_"," ");
  const setText = (id,content) => {const node=$(id);if(node)node.textContent=content;};

  function applyUser(user){
    p3state.editable=["super_admin","admin","editor"].includes(user.role)&&!user.must_change_password;
    document.querySelectorAll("[data-edit-only]").forEach(node=>show(node,p3state.editable));
    // Fields remain visible for reviewers; read-only except toggling collection filters.
    $("collection-form")?.querySelectorAll("input,textarea,select").forEach(field=>field.disabled=!p3state.editable);
    $("media-upload-form")?.querySelectorAll("input,textarea,select").forEach(field=>field.disabled=!p3state.editable);
    $("media-edit-form")?.querySelectorAll("input,textarea,select").forEach(field=>field.disabled=!p3state.editable);
  }
  async function load(name){
    try {
      if(name==="collections"){
        renderKindTabs();
        await Promise.all([refreshCollections(),refreshMediaCache()]);
        renderAssetOptions();
      }
      if(name==="media")await refreshMedia();
    }catch(error){toast(messageOf(error),true);}
  }
  function renderKindTabs(){
    const parent=$("collection-tabs");parent.replaceChildren();
    for(const [kind,label] of Object.entries(KIND_LABELS)){
      const button=document.createElement("button");button.type="button";button.className="collection-tab"+(kind===p3state.kind?" active":"");
      button.setAttribute("role","tab");button.setAttribute("aria-selected",kind===p3state.kind?"true":"false");
      button.textContent=label;button.addEventListener("click",async()=>{
        p3state.kind=kind;p3state.selected=null;setEditorVisible(false);renderKindTabs();await refreshCollections();
      });parent.append(button);
    }
    setText("collection-list-title",KIND_LABELS[p3state.kind]);
  }
  async function refreshCollections(){
    const search=$("collection-search")?.value?.trim()||"";
    const data=await api(`/collections/${p3state.kind}?limit=150${search?"&search="+encodeURIComponent(search):""}`);
    p3state.items=data.items;renderCollectionList();
  }
  function renderCollectionList(){
    const parent=$("collection-list");parent.replaceChildren();show($("collection-empty"),p3state.items.length===0);
    for(const item of p3state.items){
      const b=document.createElement("button");b.type="button";b.className="page-record"+(p3state.selected?.id===item.id?" active":"");
      const main=document.createElement("strong");main.textContent=item.title;
      const detail=document.createElement("small");detail.textContent=item.slug;
      const status=document.createElement("span");status.className="badge"+(item.status==="approved"?" done":"");status.textContent=formatted(item.status);
      b.append(main,detail,status);b.addEventListener("click",()=>selectCollection(item.id));parent.append(b);
    }
  }
  function setEditorVisible(visible){show($("collection-editor"),visible);show($("collection-editor-empty"),!visible);}
  async function selectCollection(id){
    try{
      const data=await api(`/collections/${p3state.kind}/${id}`);p3state.selected=data.item;
      fillCollectionEditor(data.item);renderCollectionList();
      await loadRelatedOptions();
    }catch(error){toast(messageOf(error),true);}
  }
  function renderAssetOptions(){
    for(const [id,kind,blank] of [["collection-hero-media","image","No hero image"],["collection-icon-media","icon","No custom icon"]]){
      const el=$(id);if(!el)return;const current=el.value;el.replaceChildren(option(blank,""));
      for(const asset of p3state.media.filter(x=>kind==="image"?x.kind==="image"||x.kind==="brand":x.kind==="icon"))el.append(option(asset.original_name,asset.id,asset.id===current));
    }
  }
  function fillCollectionEditor(item){
    setEditorVisible(true);
    setText("collection-editor-type",`${KIND_LABELS[p3state.kind].toUpperCase()} / ${item?"EDIT":"NEW DRAFT"}`);
    setText("collection-editor-name",item?.title||"New "+KIND_LABELS[p3state.kind].slice(0,-1));
    setText("collection-editor-route",item?`${p3state.kind} / ${item.slug}`:"Unpublished CMS record");
    setText("collection-editor-status",formatted(item?.status||"draft"));
    $("collection-title").value=item?.title||"";
    $("collection-slug").value=item?.slug||"";
    $("collection-summary").value=item?.summary||"";
    $("collection-body").value=item?.body_markdown||"";
    $("collection-status").value=item?.status||"draft";
    $("collection-order").value=item?.sort_order??0;
    $("collection-featured").checked=item?.is_featured||false;
    $("collection-json").value=JSON.stringify(item?.content||{},null,2);
    $("collection-seo-title").value=item?.seo_title||"";
    $("collection-meta").value=item?.meta_description||"";
    renderAssetOptions();
    $("collection-hero-media").value=item?.hero_media_id||"";
    $("collection-icon-media").value=item?.icon_media_id||"";
    show($("collection-delete"),!!item&&p3state.editable);
    show($("collection-relations-panel"),!!item);
    renderRelationships(item?.relationships||[]);
  }
  function renderRelationships(relations){
    const el=$("collection-relations");el.replaceChildren();
    if(!relations.length){const p=document.createElement("p");p.className="helper";p.textContent="No related records yet.";el.append(p);}
    for(const row of relations){
      const item=document.createElement("div");item.className="relation-chip";
      const target=p3state.targetEntries.find(x=>x.id===row.target_id);
      const label=document.createElement("span");label.textContent=`${formatted(row.relation)} · ${target?.title||row.target_id} (${row.target_kind})`;
      item.append(label);
      if(p3state.editable){const del=document.createElement("button");del.type="button";del.className="text-action";del.textContent="Remove";
        del.addEventListener("click",async()=>{try{await api(`/collections/${p3state.kind}/${p3state.selected.id}/relationships/${row.id}`,{method:"DELETE"});await selectCollection(p3state.selected.id);toast("Relationship removed");}catch(e){toast(messageOf(e),true);}});item.append(del);}
      el.append(item);
    }
  }
  async function loadRelatedOptions(){
    const lists=await Promise.all(kinds.map(kind=>api(`/collections/${kind}?limit=150`)));
    p3state.targetEntries=lists.flatMap(x=>x.items).filter(x=>x.id!==p3state.selected?.id);
    const select=$("relation-target");select.replaceChildren(option("Choose content…",""));
    for(const item of p3state.targetEntries)select.append(option(`${KIND_LABELS[item.kind]} / ${item.title}`,item.id));
    renderRelationships(p3state.selected?.relationships||[]);
  }
  $("collection-new")?.addEventListener("click",()=>{if(!p3state.editable)return;p3state.selected=null;fillCollectionEditor(null);});
  let collectionSearchDelay;
  $("collection-search")?.addEventListener("input",()=>{clearTimeout(collectionSearchDelay);collectionSearchDelay=setTimeout(()=>refreshCollections().catch(e=>toast(messageOf(e),true)),200);});
  $("collection-form")?.addEventListener("submit",async event=>{
    event.preventDefault();if(!p3state.editable)return;
    try{
      const content=JSON.parse($("collection-json").value||"{}");
      if(!content||typeof content!=="object"||Array.isArray(content))throw new Error("Structured content must be a JSON object");
      const body={title:$("collection-title").value.trim(),slug:$("collection-slug").value.trim(),
        summary:$("collection-summary").value.trim(),body_markdown:$("collection-body").value,content,
        status:$("collection-status").value,sort_order:Number($("collection-order").value||0),
        is_featured:$("collection-featured").checked,hero_media_id:$("collection-hero-media").value||null,
        icon_media_id:$("collection-icon-media").value||null,
        seo_title:$("collection-seo-title").value.trim(),meta_description:$("collection-meta").value.trim()};
      const editing=!!p3state.selected;
      const response=await api(editing?`/collections/${p3state.kind}/${p3state.selected.id}`:`/collections/${p3state.kind}`,
        {method:editing?"PATCH":"POST",body:JSON.stringify(body)});
      await refreshCollections();await selectCollection(response.item.id);toast(editing?"Draft saved":"Collection draft created");
    }catch(error){toast(error instanceof SyntaxError?"Structured content must be valid JSON":messageOf(error),true);}
  });
  $("collection-delete")?.addEventListener("click",async()=>{
    const item=p3state.selected;if(!item||!p3state.editable||!confirm(`Delete ${item.title}? This will remove its CMS draft record.`))return;
    try{await api(`/collections/${p3state.kind}/${item.id}`,{method:"DELETE"});p3state.selected=null;setEditorVisible(false);await refreshCollections();toast("Draft deleted");}catch(e){toast(messageOf(e),true);}
  });
  $("collection-reset")?.addEventListener("click",()=>p3state.selected?selectCollection(p3state.selected.id):fillCollectionEditor(null));
  $("relation-add")?.addEventListener("click",async()=>{
    if(!p3state.selected||!p3state.editable)return;
    const target=$("relation-target").value;if(!target){toast("Select related content",true);return;}
    try{await api(`/collections/${p3state.kind}/${p3state.selected.id}/relationships`,{method:"POST",body:JSON.stringify({target_id:target,relation:$("relation-type").value})});
      await selectCollection(p3state.selected.id);toast("Relationship added");}catch(e){toast(messageOf(e),true);}
  });

  async function refreshMediaCache(){const data=await api('/media?limit=150');p3state.media=data.items;}
  async function refreshMedia(){
    const search=$("media-search")?.value.trim()||"";
    const query=`?limit=150${search?"&search="+encodeURIComponent(search):""}${p3state.mediaFilter?"&kind="+p3state.mediaFilter:""}`;
    const data=await api('/media'+query);p3state.media=data.items;
    setText("media-count",`${data.total} assets${data.total>150?" (first 150 shown)":""}`);
    renderMediaGrid();
  }
  function renderMediaGrid(){
    const grid=$("media-grid");grid.replaceChildren();show($("media-empty"),p3state.media.length===0);
    for(const item of p3state.media){
      const b=document.createElement("button");b.type="button";b.className="media-tile"+(p3state.selectedMedia?.id===item.id?" active":"");
      const visual=document.createElement("div");visual.className="media-thumb";
      if(item.preview_url){const img=document.createElement("img");img.src=item.thumbnail_url||item.preview_url;img.alt=item.decorative?"":item.alt_text;img.loading="lazy";visual.append(img);}
      else{const ico=document.createElement("span");ico.textContent="PDF";ico.className="media-doc";visual.append(ico);}
      const heading=document.createElement("strong");heading.textContent=item.original_name;
      const detail=document.createElement("span");detail.textContent=`${formatted(item.kind)} · ${(item.byte_size/1024).toFixed(0)} KB · ${item.usage_count} uses`;
      b.append(visual,heading,detail);b.addEventListener("click",()=>selectMedia(item.id));grid.append(b);
    }
  }
  async function selectMedia(id){
    try{
      const data=await api(`/media/${id}`);p3state.selectedMedia=data.media;
      show($("media-detail"),true);setText("media-detail-title",data.media.original_name);
      const box=$("media-detail-preview");box.replaceChildren();
      if(data.media.preview_url){const img=document.createElement("img");img.src=data.media.preview_url;img.alt=data.media.decorative?"":data.media.alt_text;box.append(img);}
      else{const placeholder=document.createElement("p");placeholder.textContent="Document asset · PDF";box.append(placeholder);}
      $("media-edit-alt").value=data.media.alt_text||"";
      $("media-edit-caption").value=data.media.caption||"";
      $("media-edit-source").value=data.media.source_notes||"";
      $("media-edit-decorative").checked=data.media.decorative;
      await loadAssetUsages();
      if(p3state.editable)await populateSectionPages();
      renderMediaGrid();
    }catch(e){toast(messageOf(e),true);}
  }
  async function loadAssetUsages(){
    if(!p3state.selectedMedia)return;
    const data=await api(`/media/${p3state.selectedMedia.id}/usages`);
    const parent=$("media-usages");parent.replaceChildren();
    if(!data.items.length){const p=document.createElement("p");p.className="helper";p.textContent="Not used in any CMS content.";parent.append(p);}
    for(const usage of data.items){
      const row=document.createElement("div");row.className="relation-chip";
      const p=document.createElement("span");p.textContent=`${usage.owner_type.replaceAll('_',' ')} · ${usage.slot} · ${usage.owner_id.slice(0,8)}`;row.append(p);
      if(p3state.editable&&usage.owner_type==="page_section"){
        const remove=document.createElement("button");remove.type="button";remove.className="text-action";remove.textContent="Remove";
        remove.addEventListener("click",async()=>{try{await api(`/media/${p3state.selectedMedia.id}/usages/${usage.id}`,{method:"DELETE"});await selectMedia(p3state.selectedMedia.id);await refreshMedia();toast("Usage removed");}catch(e){toast(messageOf(e),true);}});row.append(remove);
      }parent.append(row);
    }
  }
  async function populateSectionPages(){
    const data=await api('/pages?limit=200');p3state.pages=data.items;
    const select=$("media-page");select.replaceChildren(option("Select page…",""));
    for(const page of data.items)select.append(option(page.title+" / "+page.route,page.id));
    $("media-slot").value=p3state.selectedMedia?.kind==="icon"?"icon":"image";
    await populateSections();
  }
  async function populateSections(){
    const select=$("media-section");select.replaceChildren(option("Select section…",""));
    if(!$("media-page").value)return;
    const data=await api(`/pages/${$("media-page").value}/sections`);
    for(const section of data.items)select.append(option(`${section.section_key} / ${section.section_type}`,section.id));
  }
  $("media-page")?.addEventListener("change",()=>populateSections().catch(e=>toast(messageOf(e),true)));
  $("media-attach")?.addEventListener("click",async()=>{
    if(!p3state.editable||!p3state.selectedMedia)return;
    const owner_id=$("media-section").value;if(!owner_id){toast("Select a page section",true);return;}
    try{await api(`/media/${p3state.selectedMedia.id}/usages`,{method:"POST",body:JSON.stringify({owner_type:"page_section",owner_id,slot:$("media-slot").value})});
      await selectMedia(p3state.selectedMedia.id);await refreshMedia();toast("Media assigned to section");}catch(e){toast(messageOf(e),true);}
  });
  $("media-kind")?.addEventListener("change",()=>show($("media-icon-style-wrap"),$("media-kind").value==="icon"));
  $("media-upload-form")?.addEventListener("submit",async(event)=>{
    event.preventDefault();if(!p3state.editable)return;
    try{
      const body=new FormData();body.append("file",$("media-file").files[0]);
      for(const [key,val] of Object.entries({kind:$("media-kind").value,icon_style:$("media-icon-style").value,
        alt_text:$("media-alt").value,caption:$("media-caption").value,
        source_notes:$("media-source").value,decorative:$("media-decorative").checked?"true":"false"}))body.append(key,val);
      const res=await api('/media',{method:"POST",body});event.target.reset();show($("media-icon-style-wrap"),false);
      await refreshMedia();await selectMedia(res.media.id);toast("Media uploaded to your private library");
    }catch(e){toast(messageOf(e),true);}
  });
  $("media-edit-form")?.addEventListener("submit",async(e)=>{
    e.preventDefault();if(!p3state.editable||!p3state.selectedMedia)return;
    try{await api(`/media/${p3state.selectedMedia.id}`,{method:"PATCH",body:JSON.stringify({alt_text:$("media-edit-alt").value,
      caption:$("media-edit-caption").value,source_notes:$("media-edit-source").value,decorative:$("media-edit-decorative").checked})});
      await refreshMedia();await selectMedia(p3state.selectedMedia.id);toast("Asset metadata saved");}catch(error){toast(messageOf(error),true);}
  });
  $("media-replace")?.addEventListener("change",async(event)=>{
    if(!p3state.editable||!p3state.selectedMedia||!event.target.files?.length)return;
    try{const body=new FormData();body.append("file",event.target.files[0]);
      await api(`/media/${p3state.selectedMedia.id}/replace`,{method:"POST",body});event.target.value="";
      await refreshMedia();await selectMedia(p3state.selectedMedia.id);toast("Asset replaced without breaking references");}catch(e){toast(messageOf(e),true);}
  });
  $("media-delete")?.addEventListener("click",async()=>{
    if(!p3state.editable||!p3state.selectedMedia||!confirm('Delete this asset? Items in use cannot be deleted.'))return;
    try{await api(`/media/${p3state.selectedMedia.id}`,{method:"DELETE"});p3state.selectedMedia=null;show($("media-detail"),false);await refreshMedia();toast("Unused asset deleted");}catch(e){toast(messageOf(e),true);}
  });
  $("media-search")?.addEventListener("input",()=>{clearTimeout(collectionSearchDelay);collectionSearchDelay=setTimeout(()=>refreshMedia().catch(e=>toast(messageOf(e),true)),200);});
  document.querySelectorAll("[data-media-filter]").forEach(b=>b.addEventListener("click",()=>{
    p3state.mediaFilter=b.dataset.mediaFilter;document.querySelectorAll("[data-media-filter]").forEach(x=>x.classList.toggle("active",x===b));
    refreshMedia().catch(e=>toast(messageOf(e),true));
  }));
  window.p3={load,applyUser};
})();
