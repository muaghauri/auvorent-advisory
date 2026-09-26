"use strict";

const $ = (id) => document.getElementById(id);
const state = { csrf: null, user: null, currentView: "dashboard", moduleData: [], toastTimer: null, pages: [], selectedPage: null, navigation: [], settings: {} };

const TITLES = { dashboard: "Overview", roadmap: "Development modules", pages: "Pages & sections", navigation: "Navigation", settings: "Site settings", collections: "Collections & insights", media: "Media library", leads: "Leads & assessments", publishing: "SEO & publishing", users: "Team & access", audit: "Security & audit", profile: "My account" };

function show(el, visible = true) { el?.classList.toggle("hidden", !visible); }
function toast(message, error = false) {
  const el = $("toast");
  el.textContent = message;
  el.classList.toggle("error", error);
  show(el, true);
  if (state.toastTimer) window.clearTimeout(state.toastTimer);
  state.toastTimer = window.setTimeout(() => show(el, false), 5000);
}
function messageOf(error) { return error?.message || "An unexpected error occurred"; }

async function csrfRefresh() {
  const response = await fetch("/api/v1/auth/csrf", { credentials: "same-origin", cache: "no-store" });
  if (!response.ok) throw new Error("Unable to initialize security token");
  const payload = await response.json();
  state.csrf = payload.csrf_token;
}

async function api(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const headers = { Accept: "application/json", ...((options.body && !(options.body instanceof FormData)) ? {"Content-Type":"application/json"} : {}), ...(options.headers || {}) };
  if (!["GET", "HEAD"].includes(method)) {
    if (!state.csrf) await csrfRefresh();
    headers["X-CSRF-Token"] = state.csrf;
  }
  const response = await fetch("/api/v1" + path, { ...options, method, headers, credentials: "same-origin", cache: "no-store" });
  let data = {};
  try { data = await response.json(); } catch { /* non-JSON error */ }
  if (!response.ok) {
    const detail = data.detail;
    const explanation = Array.isArray(detail) ? detail.map((x) => x.msg).join("; ") : typeof detail === "string" ? detail : "Request failed";
    if (response.status === 401 && !path.endsWith("/login")) sessionLost();
    throw new Error(explanation);
  }
  return data;
}

function sessionLost() {
  state.user = null;
  show($("shell"), false);
  show($("login-view"), true);
  $("login-password").value = "";
}

function applyUser(user) {
  state.user = user;
  show($("login-view"), false);
  show($("shell"), true);
  $("topbar-username").textContent = user.full_name;
  $("profile-name").textContent = user.full_name;
  $("profile-email").textContent = user.email;
  $("profile-role").textContent = user.role.replaceAll("_", " ");
  const canEdit = ["super_admin","admin","editor"].includes(user.role) && !user.must_change_password;
  show($("pages-tab"), canEdit);
  show($("navigation-tab"), canEdit);
  show($("settings-tab"), ["super_admin","admin"].includes(user.role) && !user.must_change_password);
  show($("collections-tab"), !user.must_change_password);
  show($("media-tab"), !user.must_change_password);
  if (window.p3) window.p3.applyUser(user);
  if (window.p4) window.p4.applyUser(user);
  if (window.p5) window.p5.applyUser(user);
  show($("users-tab"), user.role === "super_admin" && !user.must_change_password);
  show($("audit-tab"), user.role === "super_admin" && !user.must_change_password);
}

async function view(name) {
  if (!state.user) return;
  if (state.user.must_change_password && name !== "profile") {
    name = "profile";
    toast("Change your initial password before using the admin panel", true);
  }
  if (["users", "audit"].includes(name) && state.user.role !== "super_admin") { toast("This section requires Super Admin access", true); return; }
  if (["pages","navigation"].includes(name) && !["super_admin","admin","editor"].includes(state.user.role)) { toast("This section requires content-edit access", true); return; }
  if (name === "settings" && !["super_admin","admin"].includes(state.user.role)) { toast("Global settings require Admin access", true); return; }
  state.currentView = name;
  document.querySelectorAll(".view").forEach((section) => show(section, section.id === `view-${name}`));
  document.querySelectorAll(".nav-link[data-view]").forEach((button) => {
    const active = button.dataset.view === name;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  $("topbar-title").textContent = TITLES[name] || "Overview";
  $("sidebar").classList.remove("open");
  $("mobile-menu").setAttribute("aria-expanded", "false");
  if (name === "dashboard" || name === "roadmap") await loadDashboard();
  if (name === "pages") await loadPages();
  if (name === "navigation") await loadNavigation();
  if (name === "settings") await loadSettings();
  if (name === "users") await loadUsers();
  if (name === "audit") await loadAudit();
  if (["collections", "media"].includes(name)) await window.p3?.load(name);
  if (name === "leads") await window.p4?.load();
  if (name === "publishing") { await window.p5?.load(); await window.p6?.load(); }
}

async function loadDashboard() {
  try {
    const data = await api("/dashboard");
    state.moduleData = data.modules;
    $("metric-users").textContent = data.metrics.total_users;
    $("metric-active").textContent = data.metrics.active_users;
    $("metric-sessions").textContent = data.metrics.active_sessions;
    $("metric-audit").textContent = data.metrics.audit_events;
    drawRoadmap(data.modules);
  } catch (error) { if (state.user) toast(messageOf(error), true); }
}

function drawRoadmap(modules) {
  const target = $("roadmap-cards"); target.replaceChildren();
  for (const module of modules) {
    const card = document.createElement("article"); card.className = "module-row" + (module.status === "implemented" ? " active" : "");
    const number = document.createElement("div"); number.className = "module-index"; number.textContent = String(module.id).padStart(2, "0");
    const body = document.createElement("div"); const heading = document.createElement("h2"); heading.textContent = module.name;
    const description = document.createElement("p"); description.textContent = module.description;
    body.append(heading, description);
    const badge = document.createElement("span"); badge.className = "badge" + (module.status === "implemented" ? " done" : ""); badge.textContent = module.status === "implemented" ? "Implemented" : "Planned";
    card.append(number, body, badge); target.append(card);
  }
}

function makeCell(value, className = "") { const td = document.createElement("td"); td.textContent = String(value ?? "—"); if (className) td.className = className; return td; }
function roleLabel(role) { return role.replaceAll("_", " "); }

async function loadUsers() {
  try {
    const search = $("user-search").value.trim();
    const result = await api("/users" + (search ? "?search=" + encodeURIComponent(search) : ""));
    const body = $("users-body"); body.replaceChildren();
    show($("users-empty"), result.items.length === 0);
    for (const user of result.items) {
      const row = document.createElement("tr");
      row.append(makeCell(user.full_name, "user-main"), makeCell(user.email, "user-secondary"));
      const roleTd = document.createElement("td"); const role = document.createElement("span"); role.className = "role-pill"; role.textContent = roleLabel(user.role); roleTd.append(role); row.append(roleTd);
      row.append(makeCell(user.is_active ? "Active" : "Disabled", user.is_active ? "status-on" : "status-off"));
      const controls = document.createElement("td"); const actions = document.createElement("div"); actions.className = "row-actions";
      if (user.id !== state.user.id) {
        const select = document.createElement("select"); select.setAttribute("aria-label", `Change role for ${user.full_name}`);
        for (const name of ["super_admin", "admin", "editor", "reviewer", "viewer"]) {
          const option = document.createElement("option"); option.value = name; option.textContent = roleLabel(name); option.selected = user.role === name; select.append(option);
        }
        select.addEventListener("change", async () => {
          if (!window.confirm(`Change ${user.full_name}'s access to ${roleLabel(select.value)}?`)) { select.value = user.role; return; }
          try { await api(`/users/${user.id}`, {method:"PATCH", body:JSON.stringify({role:select.value})}); toast("User role updated"); await loadUsers(); }
          catch (error) { select.value = user.role; toast(messageOf(error), true); }
        });
        const toggle = document.createElement("button"); toggle.className = "text-action"; toggle.type = "button"; toggle.textContent = user.is_active ? "Disable" : "Enable";
        toggle.addEventListener("click", async () => {
          if (!window.confirm(`${user.is_active ? "Disable" : "Enable"} ${user.full_name}'s account?`)) return;
          try { await api(`/users/${user.id}`,{method:"PATCH",body:JSON.stringify({is_active:!user.is_active})}); toast("Account status updated"); await loadUsers(); }
          catch (error) { toast(messageOf(error), true); }
        });
        const reset = document.createElement("button"); reset.type="button"; reset.className="text-action"; reset.textContent="Reset password";
        reset.addEventListener("click", async () => {
          const password = window.prompt(`Set a new temporary password for ${user.full_name} (12+ characters). It will not be emailed.`);
          if (password === null) return;
          if (password.length < 12) {toast("A minimum of 12 characters is required",true);return;}
          try {await api(`/users/${user.id}/reset-password`,{method:"POST",body:JSON.stringify({new_password:password})}); toast("Password reset. User must change it at their next login.");}
          catch(error){toast(messageOf(error),true);}
        });
        actions.append(select, toggle, reset);
      } else {
        const note = document.createElement("span"); note.className="user-secondary"; note.textContent="Current account"; actions.append(note);
      }
      controls.append(actions); row.append(controls); body.append(row);
    }
  } catch (error) { if (state.user) toast(messageOf(error), true); }
}

async function loadAudit() {
  try {
    const result=await api("/audit?limit=40"); const body=$("audit-body"); body.replaceChildren();
    for (const item of result.items) {
      const row=document.createElement("tr");
      row.append(makeCell(new Date(item.created_at).toLocaleString(undefined,{timeZone:"UTC",dateStyle:"medium",timeStyle:"short"})),makeCell(item.action),makeCell(item.actor_user_id ? item.actor_user_id.slice(0,8)+"…" : "System"),makeCell(item.target_type+(item.target_id ? " · "+item.target_id.slice(0,10) : "")));
      body.append(row);
    }
  } catch (error) { if(state.user) toast(messageOf(error),true); }
}

async function bootstrap() {
  try {
    await csrfRefresh();
    try {const res=await api("/auth/me");applyUser(res.user);await view(res.user.must_change_password?"profile":"dashboard");}
    catch {sessionLost();}
  } catch(error){sessionLost();const notice=$("login-error");notice.textContent="The CMS server is unavailable. Please reload or contact your administrator.";show(notice,true);}
}

$("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();const button=$("login-submit");const alert=$("login-error");show(alert,false);button.disabled=true;
  try {
    const res=await api("/auth/login",{method:"POST",body:JSON.stringify({email:$("login-email").value,password:$("login-password").value})});
    $("login-password").value="";applyUser(res.user);await view(res.user.must_change_password?"profile":"dashboard");
  } catch(error){alert.textContent=messageOf(error);show(alert,true);}
  finally {button.disabled=false;}
});

$("logout").addEventListener("click",async()=>{try{await api("/auth/logout",{method:"POST"});}catch{/* still end local session */}sessionLost();});

document.querySelectorAll("button[data-view]").forEach(btn=>btn.addEventListener("click",()=>view(btn.dataset.view)));
$("mobile-menu").addEventListener("click",()=>{const open=$("sidebar").classList.toggle("open");$("mobile-menu").setAttribute("aria-expanded",String(open));});
$("add-user").addEventListener("click",()=>$("user-dialog").showModal());
$("close-user-dialog").addEventListener("click",()=>$("user-dialog").close());

$("new-user-form").addEventListener("submit",async(event)=>{
  event.preventDefault();const submit=event.submitter;submit.disabled=true;
  try{await api("/users",{method:"POST",body:JSON.stringify({full_name:$("new-user-name").value,email:$("new-user-email").value,role:$("new-user-role").value,initial_password:$("new-user-password").value})});
    $("user-dialog").close();$("new-user-form").reset();toast("CMS account created. Share the temporary password securely.");await loadUsers();}
  catch(error){toast(messageOf(error),true);}finally{submit.disabled=false;}
});

let searchDelay;$("user-search").addEventListener("input",()=>{clearTimeout(searchDelay);searchDelay=setTimeout(loadUsers,250);});
$("refresh-audit").addEventListener("click",loadAudit);
$("password-form").addEventListener("submit",async(event)=>{
  event.preventDefault();const current=$("old-password").value, newPassword=$("new-password").value;
  if(newPassword!==$("confirm-password").value){toast("New passwords do not match",true);return;}
  const button=event.submitter;button.disabled=true;
  try{const result=await api("/auth/change-password",{method:"POST",body:JSON.stringify({current_password:current,new_password:newPassword})});applyUser(result.user);$("password-form").reset();toast("Password changed and other sessions revoked");await view("dashboard");}
  catch(error){toast(messageOf(error),true);}finally{button.disabled=false;}
});


// ----- Phase 2: Page Studio -----
function badgeForStatus(status){ const span=document.createElement("span"); span.className="badge"+(status==="published"||status==="approved"?" done":""); span.textContent=(status||"draft").replaceAll("_"," "); return span; }

async function loadPages(){
  try{
    const q=$("page-search")?.value.trim()||"";
    const res=await api("/pages"+(q?"?search="+encodeURIComponent(q):"")); state.pages=res.items; renderPages();
    if(state.selectedPage){ const still=res.items.find(p=>p.id===state.selectedPage.id); if(still) await selectPage(still.id); }
  }catch(error){toast(messageOf(error),true);}
}
function renderPages(){ const list=$("pages-list"); if(!list)return; list.replaceChildren(); show($("pages-empty"),state.pages.length===0);
  for(const p of state.pages){ const b=document.createElement("button"); b.type="button"; b.className="page-record"+(state.selectedPage?.id===p.id?" active":"");
    const strong=document.createElement("strong"); strong.textContent=p.title; const small=document.createElement("small"); small.textContent=p.route; b.append(strong,small,badgeForStatus(p.status)); b.addEventListener("click",()=>selectPage(p.id)); list.append(b); }
}
async function selectPage(id){
  try{ const res=await api(`/pages/${id}`); state.selectedPage=res.page; renderPages(); show($("page-editor-empty"),false); show($("page-editor"),true); fillPageEditor(res.page); }
  catch(error){toast(messageOf(error),true);}
}
function fillPageEditor(p){
  $("editor-page-title").textContent=p.title; $("editor-page-route").textContent=p.route; const s=$("editor-status"); s.className=badgeForStatus(p.status).className; s.textContent=p.status.replaceAll("_"," ");
  $("edit-page-title").value=p.title; $("edit-page-route").value=p.route; $("edit-page-slug").value=p.slug; $("edit-page-template").value=p.template; $("edit-page-status").value=p.status; $("edit-page-nav").checked=p.show_in_navigation; $("edit-page-index").checked=p.is_indexable; $("edit-seo-title").value=p.seo_title||""; $("edit-meta-description").value=p.meta_description||""; renderSections(p.sections||[]);
}
function renderSections(sections){ const list=$("sections-list"); list.replaceChildren();
  for(const section of sections.sort((a,b)=>a.position-b.position)){ const card=document.createElement("article"); card.className="section-card"; card.dataset.id=section.id;
    const head=document.createElement("div"); head.className="section-card-head"; const drag=document.createElement("span"); drag.className="drag-handle"; drag.textContent="⋮⋮"; const info=document.createElement("div"); const h=document.createElement("h3"); h.textContent=section.content?.heading||section.section_key; const sm=document.createElement("small"); sm.textContent=`${section.section_type} · ${section.is_enabled?"enabled":"disabled"}`; info.append(h,sm); const actions=document.createElement("div"); actions.className="section-card-actions";
    const toggle=document.createElement("button"); toggle.className="text-action"; toggle.type="button"; toggle.textContent=section.is_enabled?"Disable":"Enable"; toggle.addEventListener("click",async()=>{try{await api(`/pages/${state.selectedPage.id}/sections/${section.id}`,{method:"PATCH",body:JSON.stringify({is_enabled:!section.is_enabled})});await selectPage(state.selectedPage.id);toast("Section updated");}catch(e){toast(messageOf(e),true);}});
    const del=document.createElement("button"); del.className="text-action"; del.type="button"; del.textContent="Delete"; del.addEventListener("click",async()=>{if(!confirm(`Delete section ${section.section_key}?`))return; try{await api(`/pages/${state.selectedPage.id}/sections/${section.id}`,{method:"DELETE"});await selectPage(state.selectedPage.id);toast("Section deleted");}catch(e){toast(messageOf(e),true);}}); actions.append(toggle,del); head.append(drag,info,actions);
    const details=document.createElement("details"); const summary=document.createElement("summary"); summary.textContent="Edit structured content"; const ta=document.createElement("textarea"); ta.className="section-json"; ta.value=JSON.stringify(section.content||{},null,2); const save=document.createElement("button"); save.className="button secondary small"; save.type="button"; save.textContent="Save section content"; save.addEventListener("click",async()=>{try{const content=JSON.parse(ta.value);await api(`/pages/${state.selectedPage.id}/sections/${section.id}`,{method:"PATCH",body:JSON.stringify({content})});await selectPage(state.selectedPage.id);toast("Section content saved");}catch(e){toast(e instanceof SyntaxError?"Section content must be valid JSON":messageOf(e),true);}}); details.append(summary,ta,save); const visual=document.createElement('button');visual.className='button secondary small';visual.type='button';visual.textContent='Visual editor';visual.addEventListener('click',()=>window.p6?.open(section));head.append(visual);card.append(head,details);list.append(card); }
  if(!sections.length){ const p=document.createElement("p"); p.className="empty-state"; p.textContent="No sections yet. Add the first structured section."; list.append(p); }
}

async function loadNavigation(){ try{const res=await api("/navigation");state.navigation=res.items;renderNavigation();}catch(e){toast(messageOf(e),true);} }
function renderNavigation(){const list=$("navigation-list"); list.replaceChildren(); for(const item of state.navigation){const row=document.createElement("div");row.className="nav-edit-row";row.dataset.id=item.id;
  const loc=document.createElement("select"); for(const v of ["header","footer","utility"]){const o=document.createElement("option");o.value=v;o.textContent=v;o.selected=item.location===v;loc.append(o);} loc.dataset.field="location";
  const label=document.createElement("input");label.value=item.label;label.dataset.field="label";const url=document.createElement("input");url.value=item.url;url.dataset.field="url";const pos=document.createElement("input");pos.type="number";pos.min="0";pos.value=item.position;pos.dataset.field="position";
  const visible=document.createElement("input");visible.type="checkbox";visible.checked=item.is_visible;visible.dataset.field="is_visible";const wrap=document.createElement("label");wrap.className="nav-check";wrap.title="Visible";wrap.append(visible);
  const remove=document.createElement("button");remove.className="text-action";remove.type="button";remove.textContent="Remove";remove.addEventListener("click",()=>{state.navigation=state.navigation.filter(x=>x.id!==item.id);renderNavigation();});row.append(loc,label,url,pos,wrap,remove);list.append(row);}}
function readNavigationEditor(){return [...document.querySelectorAll(".nav-edit-row")].map((row,i)=>({id:row.dataset.id||null,location:row.querySelector('[data-field="location"]').value,label:row.querySelector('[data-field="label"]').value.trim(),url:row.querySelector('[data-field="url"]').value.trim(),position:Number(row.querySelector('[data-field="position"]').value||i),is_visible:row.querySelector('[data-field="is_visible"]').checked,open_new_tab:false}));}

async function loadSettings(){try{const res=await api("/settings");state.settings=res.values; document.querySelectorAll("[data-setting]").forEach(el=>el.value=state.settings[el.dataset.setting]??"");}catch(e){toast(messageOf(e),true);}}

// Page Studio event handlers
$("page-form")?.addEventListener("submit",async(e)=>{e.preventDefault();if(!state.selectedPage)return;const body={title:$("edit-page-title").value,route:$("edit-page-route").value,slug:$("edit-page-slug").value,template:$("edit-page-template").value,status:$("edit-page-status").value,show_in_navigation:$("edit-page-nav").checked,is_indexable:$("edit-page-index").checked,seo_title:$("edit-seo-title").value,meta_description:$("edit-meta-description").value};try{await api(`/pages/${state.selectedPage.id}`,{method:"PATCH",body:JSON.stringify(body)});toast("Page saved as CMS draft state");await loadPages();}catch(err){toast(messageOf(err),true);}});
$("refresh-page")?.addEventListener("click",()=>state.selectedPage&&selectPage(state.selectedPage.id));
$("add-page")?.addEventListener("click",()=>$("page-dialog").showModal());
document.querySelectorAll("[data-close]").forEach(btn=>btn.addEventListener("click",()=>$(btn.dataset.close).close()));
$("new-page-form")?.addEventListener("submit",async(e)=>{e.preventDefault();try{const res=await api("/pages",{method:"POST",body:JSON.stringify({title:$("new-page-title").value,route:$("new-page-route").value,slug:$("new-page-slug").value,template:$("new-page-template").value||"standard"})});$("page-dialog").close();e.target.reset();await loadPages();await selectPage(res.page.id);toast("Draft page created");}catch(err){toast(messageOf(err),true);}});
$("add-section")?.addEventListener("click",()=>{if(state.selectedPage)$("section-dialog").showModal();});
$("section-form")?.addEventListener("submit",async(e)=>{e.preventDefault();if(!state.selectedPage)return;try{const content={heading:$("section-heading-input").value,description:$("section-description").value};await api(`/pages/${state.selectedPage.id}/sections`,{method:"POST",body:JSON.stringify({section_key:$("section-key").value,section_type:$("section-type").value,position:(state.selectedPage.sections||[]).length,content})});$("section-dialog").close();e.target.reset();await selectPage(state.selectedPage.id);toast("Section added");}catch(err){toast(messageOf(err),true);}});
let pageSearchDelay;$("page-search")?.addEventListener("input",()=>{clearTimeout(pageSearchDelay);pageSearchDelay=setTimeout(loadPages,250);});
$("add-nav-item")?.addEventListener("click",()=>{state.navigation.push({id:null,location:"header",label:"New link",url:"/",position:state.navigation.length,is_visible:true,open_new_tab:false});renderNavigation();});
$("save-navigation")?.addEventListener("click",async()=>{try{const items=readNavigationEditor();await api("/navigation",{method:"PATCH",body:JSON.stringify({items})});toast("Navigation saved");await loadNavigation();}catch(e){toast(messageOf(e),true);}});
$("settings-form")?.addEventListener("submit",async(e)=>{e.preventDefault();const values={};document.querySelectorAll("[data-setting]").forEach(el=>values[el.dataset.setting]=el.value);try{await api("/settings",{method:"PATCH",body:JSON.stringify({values})});toast("Global settings saved");await loadSettings();}catch(err){toast(messageOf(err),true);}});

bootstrap();
