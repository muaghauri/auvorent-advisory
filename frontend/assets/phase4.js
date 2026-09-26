"use strict";
/* Phase 4. Static markup, safe DOM rendering; no raw user content injected via innerHTML. */
(() => {
  const p4 = { panel: "inbox", forms: [], currentForm: null, inquiries: [], selectedInquiry: null,
               assessments: [], currentAssessment: null, admins: [], canEdit: false, isAdmin: false };
  const $id = id => document.getElementById(id);
  const node = (tag, text = "", cls = "") => { const x = document.createElement(tag); if (cls) x.className = cls; if (text !== null) x.textContent = text; return x; };
  const option = (text, value, current) => { const x = node("option", text); x.value = value; x.selected = value === current; return x; };
  const call = (path, method, data) => api(path, {method, ...(data===undefined?{}:{body:JSON.stringify(data)})});
  const error = e => toast(messageOf(e), true);
  const uniqueKey = (base, items) => { let idx = 1, key=base; while (items.some(i => i.id === key)) key=base+ ++idx; return key; };
  const clone = x => JSON.parse(JSON.stringify(x));
  function applyUser(user) {
    p4.canEdit = ["super_admin", "admin", "editor"].includes(user.role) && !user.must_change_password;
    p4.isAdmin = ["super_admin", "admin"].includes(user.role) && !user.must_change_password;
    show($id("leads-tab"), !user.must_change_password);
    show(document.querySelector('[data-lead-panel="inbox"]'), p4.isAdmin);
    show(document.querySelector('[data-lead-panel="routing"]'), p4.isAdmin);
    show($id("lead-stats"), p4.isAdmin);
    ["lead-new-form", "lead-new-assessment", "lead-add-field", "lead-add-question", "lead-add-rule", "lead-delete-form"].forEach(id => {
      if ($id(id)) show($id(id), p4.canEdit);
    });
    if (!p4.isAdmin && ["inbox", "routing"].includes(p4.panel)) p4.panel = "forms";
  }
  async function load() {
    switchPanel(p4.panel);
    if (p4.isAdmin) await loadStats();
    await loadPanel(p4.panel);
  }
  function switchPanel(panel) {
    if (!p4.isAdmin && ["inbox", "routing"].includes(panel)) panel = "forms";
    p4.panel = panel;
    document.querySelectorAll("[data-lead-panel]").forEach(button => {
      const active = button.dataset.leadPanel === panel;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", String(active));
    });
    for (const name of ["inbox", "forms", "assessments", "routing"]) show($id("lead-"+name), name === panel);
  }
  async function loadPanel(panel) {
    try {
      if (panel === "inbox") await loadInbox();
      if (panel === "forms") await loadForms();
      if (panel === "assessments") await loadAssessments();
      if (panel === "routing") await loadRouting();
    } catch(e){error(e);}
  }
  async function loadStats(){
    try {
      const d = await api("/leads/summary");
      for (const [key, val] of [["lead-total",d.total],["lead-new",d.new],["lead-notified",d.sent],["lead-forms-count",d.active_forms]]) $id(key).textContent = val;
    } catch(e){error(e);}
  }
  async function loadInbox(){
    const search = $id("lead-search").value.trim(); const status = $id("lead-status-filter").value;
    const params = new URLSearchParams({limit:"100"}); if(search)params.set("search",search);if(status)params.set("status",status);
    const data = await api("/inquiries?"+params.toString()); p4.inquiries=data.items;
    const body = $id("lead-inbox-body");body.replaceChildren();show($id("lead-inbox-empty"), data.items.length===0);
    for (const entry of data.items){
      const row = node("tr"), contact=node("td"), name=node("strong",entry.name||"Unknown"), email=node("small",entry.email||"—");
      contact.append(name,email); row.append(contact,node("td",entry.company||"—"),node("td",entry.priority||"—"),node("td",entry.created_at?.slice(0,16).replace("T"," ")||"—"));
      const mail=node("td"), badge=node("span",entry.notification_status,"lead-badge "+(entry.notification_status==="sent"?"":"warn"));mail.append(badge);row.append(mail);
      const statusCell=node("td"), label=node("span",entry.status.replaceAll("_"," "),"lead-badge "+(entry.status==="new"?"warn":""));statusCell.append(label);row.append(statusCell);
      const open=node("td"),button=node("button","Open","button secondary small");button.type="button";button.addEventListener("click",()=>selectInquiry(entry.id));open.append(button);row.append(open);body.append(row);
    }
  }
  async function loadAssignees(){
    const data=await api("/inquiries/assignees");p4.admins=data.items;
    const select=$id("lead-detail-assignee"),current=select.value;
    select.replaceChildren(option("Unassigned","",current));for(const user of p4.admins)select.append(option(user.full_name,user.id,current));
  }
  async function selectInquiry(id){
    try {
      const data=await api("/inquiries/"+encodeURIComponent(id));p4.selectedInquiry=data.inquiry;
      await loadAssignees();
      $id("lead-detail-title").textContent=data.inquiry.name||"Website inquiry";
      $id("lead-detail-meta").textContent=`${data.inquiry.email||"No email"} · ${data.inquiry.company||"—"} · ${data.inquiry.created_at?.slice(0,16)||""} UTC`;
      $id("lead-detail-status").value=data.inquiry.status;
      $id("lead-detail-assignee").value=data.inquiry.assigned_user_id||"";
      $id("lead-mail-status").textContent=data.inquiry.notification_status.replaceAll("_"," ");
      show($id("lead-retry-email"),data.inquiry.notification_status!=="sent");
      const answerBox=$id("lead-answer-list");answerBox.replaceChildren();
      for(const [key,value] of Object.entries(data.inquiry.answers||{})){
        const item=node("div",null,"lead-answer");item.append(node("small",key.replaceAll("_"," ")),node("p",String(value)));answerBox.append(item);
      }
      const notes=$id("lead-notes");notes.replaceChildren();for(const note of data.notes){const item=node("div",null,"lead-note");item.append(node("p",note.text),node("small",note.created_at?.slice(0,16).replace("T"," ")+" UTC"));notes.append(item);}
      show($id("lead-detail"),true);
      $id("lead-detail").scrollIntoView({behavior:"smooth",block:"start"});
    }catch(e){error(e);}
  }
  async function loadForms(){
    const d=await api("/forms");p4.forms=d.items;renderFormList();
    if(p4.currentForm?.id && p4.forms.some(f=>f.id===p4.currentForm.id)) await selectForm(p4.currentForm.id);
  }
  function renderFormList(){
    const target=$id("lead-form-list");target.replaceChildren();for(const item of p4.forms){
      const b=node("button",null,"page-record"+(p4.currentForm?.id===item.id?" active":""));b.type="button";
      b.append(node("strong",item.title),node("small","/"+item.slug));b.append(node("span",item.is_active?"Active":"Inactive","badge "+(item.is_active?"done":"")));
      b.addEventListener("click",()=>selectForm(item.id));target.append(b);
    }
  }
  async function selectForm(id){
    try{const d=await api("/forms/"+id);p4.currentForm=clone(d.form);renderFormList();renderForm();}catch(e){error(e);}
  }
  function newForm(){
    p4.currentForm={id:null,slug:"new-form",title:"New business inquiry form",intro:"",success_message:"Thank you. We will review your inquiry.",fields:[{id:"name",label:"Your name",type:"text",required:true,placeholder:"",help_text:"",options:[],max_length:180}],is_active:false};
    renderFormList();renderForm();
  }
  function renderForm(){
    const f=p4.currentForm;if(!f)return;
    show($id("lead-form-empty"),false);show($id("lead-form-editor"),true);
    $id("lead-form-heading").textContent=f.title;
    for(const [id,value] of [["lead-form-title",f.title],["lead-form-slug",f.slug],["lead-form-intro",f.intro],["lead-form-success",f.success_message]])$id(id).value=value;
    $id("lead-form-slug").disabled=!!f.id||!p4.canEdit;
    $id("lead-form-active").checked=f.is_active;
    show($id("lead-delete-form"),!!f.id&&p4.canEdit);
    $id("lead-form-editor").querySelectorAll("input,textarea,button").forEach(el=>{if(el.id!=="lead-delete-form"&&el.id!=="lead-form-slug")el.disabled=!p4.canEdit;});
    renderFields();
  }
  function inputControl(labelText,value,change,kind="text",options=null){
    const label=node("label",labelText);
    let field;
    if(kind==="select") {field=node("select"); for(const o of options)field.append(option(o,o,value));}
    else if(kind==="textarea") {field=node("textarea");field.rows=2;field.value=value||"";}
    else {field=node("input");field.type=kind; if(kind==="checkbox")field.checked=!!value;else field.value=value??"";}
    field.disabled=!p4.canEdit;
    field.addEventListener(kind==="checkbox"||kind==="select"?"change":"input",()=>change(kind==="checkbox"?field.checked:field.value));
    label.append(field);return label;
  }
  function renderFields(){
    const parent=$id("lead-field-list");parent.replaceChildren();const f=p4.currentForm;
    f.fields.forEach((field,index)=>{
      const box=node("article",null,"lead-field");
      const head=node("div",null,"lead-field-head");head.append(node("strong",`Field ${String(index+1).padStart(2,"0")} · ${field.id}`));
      const actions=node("div",null,"lead-field-actions");
      for(const [label,delta] of [["↑",-1],["↓",1]]){
        const b=node("button",label);b.type="button";b.disabled=!p4.canEdit||index+delta<0||index+delta>=f.fields.length;
        b.setAttribute("aria-label",(delta<0?"Move up ":"Move down ")+field.label);
        b.addEventListener("click",()=>{const dest=index+delta;[f.fields[index],f.fields[dest]]=[f.fields[dest],f.fields[index]];renderFields();});actions.append(b);
      }
      const del=node("button","Remove");del.type="button";del.disabled=!p4.canEdit||f.fields.length===1;
      del.addEventListener("click",()=>{f.fields.splice(index,1);renderFields();});actions.append(del);head.append(actions);box.append(head);
      const grid=node("div",null,"field-grid");
      grid.append(inputControl("Field ID (API key)",field.id,v=>field.id=v),inputControl("Visible label",field.label,v=>field.label=v));
      grid.append(inputControl("Field type",field.type,v=>{field.type=v;field.options=v==="select"?["Option one"]:[];renderFields();},"select",["text","email","textarea","select","checkbox"]),
        inputControl("Maximum characters",field.max_length||400,v=>field.max_length=Number(v)||400,"number"));
      grid.append(inputControl("Placeholder",field.placeholder||"",v=>field.placeholder=v),inputControl("Help text",field.help_text||"",v=>field.help_text=v));
      if(field.type==="select")grid.append(inputControl("Dropdown options, one per line",(field.options||[]).join("\n"),v=>field.options=v.split("\n").map(x=>x.trim()).filter(Boolean),"textarea"));
      grid.append(inputControl("Required field",field.required,v=>field.required=v,"checkbox"));box.append(grid);parent.append(box);
    });
  }
  function readForm(){
    const f=p4.currentForm;return {title:$id("lead-form-title").value.trim(),slug:$id("lead-form-slug").value.trim(),intro:$id("lead-form-intro").value.trim(),
      success_message:$id("lead-form-success").value.trim(),is_active:$id("lead-form-active").checked,fields:f.fields};
  }
  async function saveForm(event){
    event.preventDefault();if(!p4.canEdit)return;
    try{const data=readForm(),old=p4.currentForm;
      const d=old.id?await call("/forms/"+old.id,"PATCH",((({slug,...patch})=>patch)(data))):await call("/forms","POST",data);
      p4.currentForm=clone(d.form);toast("Form saved successfully");await loadForms();
    }catch(e){error(e);}
  }
  async function deleteForm(){if(!p4.currentForm?.id||!confirm("Delete this inactive form? It cannot have any submissions."))return;
    try{await call("/forms/"+p4.currentForm.id,"DELETE");p4.currentForm=null;show($id("lead-form-editor"),false);show($id("lead-form-empty"),true);await loadForms();toast("Form deleted");}catch(e){error(e);}
  }
  async function loadRouting(){
    if(!p4.isAdmin)return;
    const d=await api("/forms/settings");const s=d.settings;
    $id("lead-recipient").value=s.recipient_email;$id("lead-cc").value=(s.cc||[]).join(", ");
    $id("lead-subject").value=s.subject_prefix;$id("lead-autoreply").checked=s.reply_enabled;
    const h=await api("/leads/email-health");
    $id("lead-email-ready").textContent=h.configured?"SMTP sender configured":"SMTP sender not configured";
    $id("lead-email-help").textContent=h.configured?"An inquiry notification will be attempted via the configured SMTP server. Verify inbox delivery before launch.":"Submissions are saved in the CMS. To deliver notifications, set CMS_SMTP_HOST and CMS_MAIL_FROM plus any required credentials in your private environment.";
  }
  async function saveRouting(event){event.preventDefault();if(!p4.isAdmin)return;
    const cc=$id("lead-cc").value.split(",").map(v=>v.trim()).filter(Boolean);
    try{await call("/forms/settings","PATCH",{recipient_email:$id("lead-recipient").value.trim(),cc,subject_prefix:$id("lead-subject").value.trim(),reply_enabled:$id("lead-autoreply").checked});toast("Email routing saved");await loadRouting();}catch(e){error(e);}
  }
  async function loadAssessments(){
    const d=await api("/assessments");p4.assessments=d.items;renderAssessmentList();
    if(p4.currentAssessment?.id&&p4.assessments.some(a=>a.id===p4.currentAssessment.id))await selectAssessment(p4.currentAssessment.id);
  }
  function renderAssessmentList(){
    const list=$id("lead-assessment-list");list.replaceChildren();for(const a of p4.assessments){
      const b=node("button",null,"page-record"+(p4.currentAssessment?.id===a.id?" active":""));b.type="button";
      b.append(node("strong",a.title),node("small","/"+a.slug));b.append(node("span",a.is_active?"Active":"Draft","badge "+(a.is_active?"done":"")));
      b.addEventListener("click",()=>selectAssessment(a.id));list.append(b);
    }
  }
  async function selectAssessment(id){try{const d=await api("/assessments/"+id);p4.currentAssessment=clone(d.assessment);renderAssessmentList();renderAssessment();}catch(e){error(e);}}
  function newAssessment(){p4.currentAssessment={id:null,slug:"new-assessment",title:"New optimization check",intro:"",disclaimer:"This is a preliminary screening, not a verified business diagnosis.",questions:[{id:"q1",prompt:"What is your priority?",required:true,options:[{id:"a",label:"Operational efficiency"},{id:"b",label:"Business growth"}]}],results:{},cta_label:"Request a strategy conversation",cta_url:"/contact/",is_active:false};renderAssessmentList();renderAssessment();}
  function renderAssessment(){
    const a=p4.currentAssessment;if(!a)return;
    show($id("lead-assessment-empty"),false);show($id("lead-assessment-editor"),true);$id("lead-assessment-heading").textContent=a.title;
    for(const [id,v] of [["lead-assessment-title",a.title],["lead-assessment-slug",a.slug],["lead-assessment-intro",a.intro],["lead-assessment-disclaimer",a.disclaimer],["lead-assessment-cta",a.cta_label],["lead-assessment-url",a.cta_url]])$id(id).value=v||"";
    $id("lead-assessment-slug").disabled=!!a.id||!p4.canEdit;$id("lead-assessment-active").checked=a.is_active;
    $id("lead-assessment-editor").querySelectorAll("input,textarea,button").forEach(el=>{if(el.id!=="lead-assessment-slug")el.disabled=!p4.canEdit;});
    renderQuestions();refreshRuleOptions();renderRules();
  }
  function renderQuestions(){
    const list=$id("lead-question-list");list.replaceChildren();const a=p4.currentAssessment;
    a.questions.forEach((q,index)=>{
      const card=node("article",null,"lead-question"), head=node("div",null,"lead-question-head");head.append(node("strong",`Question ${index+1} · ${q.id}`));
      const actions=node("div",null,"lead-field-actions");
      for(const [label,step] of [["↑",-1],["↓",1]]){const b=node("button",label);b.type="button";b.disabled=!p4.canEdit||index+step<0||index+step>=a.questions.length;b.addEventListener("click",()=>{[a.questions[index],a.questions[index+step]]=[a.questions[index+step],a.questions[index]];renderQuestions();});actions.append(b);}
      const remove=node("button","Remove question");remove.type="button";remove.disabled=!p4.canEdit||a.questions.length===1;remove.addEventListener("click",()=>{a.questions.splice(index,1);renderQuestions();refreshRuleOptions();});actions.append(remove);head.append(actions);card.append(head);
      const grid=node("div",null,"field-grid");grid.append(inputControl("Question ID",q.id,v=>{q.id=v;refreshRuleOptions();}),inputControl("Question",q.prompt,v=>q.prompt=v));grid.append(inputControl("Required",q.required,v=>q.required=v,"checkbox"));card.append(grid);
      const optTitle=node("strong","Answer choices","lead-subheading");card.append(optTitle);
      for(const [oi,o] of q.options.entries()){
        const row=node("div",null,"lead-option-row");const id=inputControl("Option ID",o.id,v=>{o.id=v;refreshRuleOptions();});const name=inputControl("Answer label",o.label,v=>o.label=v);row.append(id,name);
        const del=node("button","Remove","button secondary small");del.type="button";del.disabled=!p4.canEdit||q.options.length<=2;del.addEventListener("click",()=>{q.options.splice(oi,1);renderQuestions();refreshRuleOptions();});row.append(del);card.append(row);
      }
      const add=node("button","+ Add answer","button secondary small");add.type="button";add.disabled=!p4.canEdit;add.addEventListener("click",()=>{q.options.push({id:uniqueKey("option",q.options),label:"New answer"});renderQuestions();refreshRuleOptions();});card.append(add);list.append(card);
    });
  }
  function refreshRuleOptions(){
    const a=p4.currentAssessment;if(!a)return;const q=$id("lead-rule-question"),before=q.value;q.replaceChildren();
    for(const item of a.questions)q.append(option(item.prompt.slice(0,60),item.id,before));
    if(!a.questions.some(item=>item.id===before))q.selectedIndex=0;
    const o=$id("lead-rule-option"),old=o.value;o.replaceChildren();const selected=a.questions.find(item=>item.id===q.value);
    if(selected)for(const choice of selected.options)o.append(option(choice.label,choice.id,old));
  }
  function renderRules(){
    const list=$id("lead-rule-list");list.replaceChildren();for(const [key,val] of Object.entries(p4.currentAssessment?.results||{})){
      const row=node("div",null,"lead-rule-chip"),body=node("div");body.append(node("strong",`${key} · ${val.title}`),node("p",val.description));
      const controls=node("div",null,"lead-field-actions"),edit=node("button","Edit"),del=node("button","Remove");
      edit.disabled=del.disabled=!p4.canEdit;edit.type=del.type="button";
      edit.addEventListener("click",()=>{const[q,o]=key.split(".");$id("lead-rule-question").value=q;refreshRuleOptions();$id("lead-rule-option").value=o;$id("lead-rule-title").value=val.title;$id("lead-rule-description").value=val.description;});
      del.addEventListener("click",()=>{delete p4.currentAssessment.results[key];renderRules();});controls.append(edit,del);row.append(body,controls);list.append(row);
    }
  }
  function addRule(){if(!p4.canEdit)return;const q=$id("lead-rule-question").value,o=$id("lead-rule-option").value,title=$id("lead-rule-title").value.trim(),description=$id("lead-rule-description").value.trim();if(!q||!o||title.length<3||description.length<3){toast("Choose an answer and provide a title and explanation",true);return;}
    p4.currentAssessment.results[q+"."+o]={title,description};renderRules();toast("Rule added locally. Save assessment to persist.");
  }
  function readAssessment(){const a=p4.currentAssessment;return{slug:$id("lead-assessment-slug").value.trim(),title:$id("lead-assessment-title").value.trim(),intro:$id("lead-assessment-intro").value.trim(),disclaimer:$id("lead-assessment-disclaimer").value.trim(),questions:a.questions,results:a.results,cta_label:$id("lead-assessment-cta").value.trim(),cta_url:$id("lead-assessment-url").value.trim(),is_active:$id("lead-assessment-active").checked};}
  async function saveAssessment(event){event.preventDefault();if(!p4.canEdit)return;try{const item=p4.currentAssessment,all=readAssessment(),data=item.id?await call("/assessments/"+item.id,"PATCH",((({slug,...patch})=>patch)(all))):await call("/assessments","POST",all);p4.currentAssessment=clone(data.assessment);toast("Assessment saved");await loadAssessments();}catch(e){error(e);}}
  // Event handlers
  document.querySelectorAll("[data-lead-panel]").forEach(b=>b.addEventListener("click",async()=>{switchPanel(b.dataset.leadPanel);await loadPanel(p4.panel);}));
  let delay;$id("lead-search")?.addEventListener("input",()=>{clearTimeout(delay);delay=setTimeout(()=>loadInbox().catch(error),250);});
  $id("lead-status-filter")?.addEventListener("change",()=>loadInbox().catch(error));
  $id("leads-csv")?.addEventListener("click",()=>window.location.assign("/api/v1/inquiries/export"));
  $id("lead-detail-close")?.addEventListener("click",()=>show($id("lead-detail"),false));
  $id("lead-detail-save")?.addEventListener("click",async()=>{if(!p4.selectedInquiry)return;try{await call("/inquiries/"+p4.selectedInquiry.id,"PATCH",{status:$id("lead-detail-status").value,assigned_user_id:$id("lead-detail-assignee").value||null});toast("Inquiry updated");await loadInbox();await selectInquiry(p4.selectedInquiry.id);}catch(e){error(e);}});
  $id("lead-note-form")?.addEventListener("submit",async e=>{e.preventDefault();if(!p4.selectedInquiry)return;try{await call("/inquiries/"+p4.selectedInquiry.id+"/notes","POST",{text:$id("lead-note-text").value.trim()});$id("lead-note-text").value="";toast("Private note added");await selectInquiry(p4.selectedInquiry.id);}catch(err){error(err);}});
  $id("lead-retry-email")?.addEventListener("click",async()=>{if(!p4.selectedInquiry||!confirm("Retry the email notification for this inquiry?"))return;try{const res=await call("/inquiries/"+p4.selectedInquiry.id+"/resend","POST");toast("Notification status: "+res.notification_status);await selectInquiry(p4.selectedInquiry.id);await loadStats();}catch(e){error(e);}});
  $id("lead-new-form")?.addEventListener("click",newForm);$id("lead-add-field")?.addEventListener("click",()=>{p4.currentForm.fields.push({id:uniqueKey("field",p4.currentForm.fields),label:"New field",type:"text",required:false,placeholder:"",help_text:"",options:[],max_length:400});renderFields();});
  $id("lead-form-editor")?.addEventListener("submit",saveForm);$id("lead-delete-form")?.addEventListener("click",deleteForm);
  $id("lead-routing-form")?.addEventListener("submit",saveRouting);
  $id("lead-new-assessment")?.addEventListener("click",newAssessment);
  $id("lead-add-question")?.addEventListener("click",()=>{const a=p4.currentAssessment;a.questions.push({id:uniqueKey("q",a.questions),prompt:"New question",required:true,options:[{id:"a",label:"First option"},{id:"b",label:"Second option"}]});renderQuestions();refreshRuleOptions();});
  $id("lead-rule-question")?.addEventListener("change",refreshRuleOptions);
  $id("lead-add-rule")?.addEventListener("click",addRule);
  $id("lead-assessment-editor")?.addEventListener("submit",saveAssessment);
  window.p4={applyUser,load};
})();
