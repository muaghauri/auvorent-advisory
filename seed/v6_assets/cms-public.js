/* Auvorent public V6 -> CMS Phase 6 connector. No credentials in browser. */
(function () {
  'use strict';
  const api = String(window.AUVORENT_CMS_API_BASE || '').replace(/\/$/, '');
  function url(path) { return api + '/api/v1/public/' + path; }
  function el(tag, text, className) {
    const n = document.createElement(tag);
    if (text !== undefined && text !== null) n.textContent = text;
    if (className) n.className = className;
    return n;
  }
  async function jsonRequest(path, options) {
    if (!api) throw new Error('The online inquiry service is not configured yet.');
    const response = await fetch(url(path), { credentials: 'omit', mode: 'cors', ...options });
    let payload = null;
    try { payload = await response.json(); } catch (_) { /* transient upstream */ }
    if (!response.ok) throw new Error(typeof payload?.detail === 'string' ? payload.detail : 'Service unavailable. Please try later.');
    return payload;
  }
  async function setupContact() {
    const form = document.getElementById('contact-form');
    if (!form) return;
    const status = document.getElementById('contact-status');
    const button = form.querySelector('button[type="submit"]');
    try {
      const schema = await jsonRequest('forms/strategy-consultation');
      // Built by the CMS field schema. No arbitrary HTML inserted into the page.
      const fields = el('div', null, 'cms-form-fields');
      let paired = null;
      schema.fields.forEach((field, index) => {
        const pairable = ['name','email','company','size'].includes(field.id) && index < 4;
        if (pairable && index % 2 === 0) { paired = el('div', null, 'form-pair'); fields.append(paired); }
        const label = el('label');
        const caption = el('span', field.label, 'field-caption');
        if (field.required) { const star = el('sup', '*', 'required-marker'); star.setAttribute('aria-hidden','true'); caption.append(' ', star); }
        label.append(caption);
        const type = field.type;
        const input = type === 'textarea' ? el('textarea') : type === 'select' ? el('select') : el('input');
        if (type === 'select') {
          const empty = el('option', field.placeholder || 'Choose one'); empty.value='';input.append(empty);
          field.options.forEach(option => { const o=el('option',option); o.value=option;input.append(o); });
        } else if (type === 'textarea') input.rows = 5;
        else input.type=type==='email'?'email':type==='checkbox'?'checkbox':'text';
        input.name=field.id; input.required=!!field.required;
        if (field.placeholder) input.placeholder=field.placeholder;
        if (field.max_length) input.maxLength=field.max_length;
        if (field.id==='name') input.autocomplete='name';
        if (field.id==='email') input.autocomplete='email';
        if (field.id==='company') input.autocomplete='organization';
        label.append(input);
        if (field.help_text)label.append(el('span',field.help_text,'field-help'));
        if (pairable && paired)paired.append(label);else fields.append(label);
      });
      form.querySelectorAll('.form-pair').forEach(e => e.remove());
      for (const old of [...form.children]) if (old.tagName==='LABEL' && !old.classList.contains('consent'))old.remove();
      const anchor = form.querySelector('.hp') || form.querySelector('.consent');
      if (anchor)form.insertBefore(fields,anchor);else form.prepend(fields);
      if (button)button.textContent='Send inquiry ↗';
      if (status)status.textContent='';
      const prior = new URLSearchParams(window.location.search).get('from')==='assessment' ? sessionStorage.getItem('auvorentAssessment') : null;
      if (prior && form.elements.namedItem('message'))form.elements.namedItem('message').value=prior.slice(0,2500);
      form.addEventListener('submit', async event => {
        event.preventDefault();
        if (!form.reportValidity())return;
        if (status)status.textContent='';
        const data=Object.fromEntries(new FormData(form).entries());
        const payload={data:{},consent:!!data.consent,website:data.website||'',source_page:window.location.pathname,utm:{}};
        schema.fields.forEach(field=>{if(field.type==='checkbox')payload.data[field.id]=!!form.elements.namedItem(field.id)?.checked;else if(Object.hasOwn(data,field.id))payload.data[field.id]=data[field.id];});
        const params=new URLSearchParams(window.location.search);
        ['utm_source','utm_medium','utm_campaign','utm_content','utm_term'].forEach(k=>{if(params.has(k))payload.utm[k]=String(params.get(k)).slice(0,120);});
        if(button){button.disabled=true;button.textContent='Sending…';}
        try {
          const reply=await jsonRequest('forms/strategy-consultation/submit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
          if(status){status.classList.add('success');status.textContent=reply.message||schema.success_message||'Your inquiry has been received.';}
          form.reset();
          try{sessionStorage.removeItem('auvorentAssessment');}catch(_){}
        } catch(error) {
          if(status){status.classList.remove('success');status.textContent=error.message||'Unable to submit right now.';}
        } finally {if(button){button.disabled=false;button.textContent='Send inquiry ↗';}}
      });
    } catch(error) {
      if(status)status.textContent='The inquiry form is temporarily unavailable. Please try again later.';
      if(button)button.disabled=true;
    }
  }
  async function setupAssessment() {
    const root=document.getElementById('assessment-form');if(!root)return;
    const questionBox=document.getElementById('assessment-question'),resultsBox=document.getElementById('assessment-results');
    const next=document.getElementById('assessment-next'),back=document.getElementById('assessment-back');
    const progress=document.getElementById('assessment-progress'),stepText=document.getElementById('assessment-step'),percent=document.getElementById('assessment-percent');
    try {
      const schema=await jsonRequest('assessments/business-optimization-check');
      const questions=schema.questions||[];
      if(!questions.length)throw new Error('Assessment unavailable');
      const answers={};let step=0;
      function draw(){
        const q=questions[step];const pct=Math.round((step+1)/questions.length*100);
        stepText.textContent=`Question ${step+1} of ${questions.length}`;percent.textContent=pct+'%';progress.style.width=pct+'%';
        questionBox.hidden=false;resultsBox.hidden=true;next.hidden=false;back.hidden=false;
        next.textContent=step===questions.length-1?'See your summary ↗':'Continue ↗';
        next.disabled=!answers[q.id];back.disabled=step===0;questionBox.replaceChildren();
        const wrap=el('div',null,'assessment-q');wrap.append(el('h2',q.prompt));const group=el('div');group.setAttribute('role','radiogroup');group.setAttribute('aria-label',q.prompt);
        q.options.forEach(opt=>{
          const label=el('label',null,'option-row');const radio=el('input');radio.type='radio';radio.name='question-'+q.id;radio.value=opt.id;radio.checked=answers[q.id]===opt.id;
          radio.addEventListener('change',()=>{answers[q.id]=opt.id;next.disabled=false;});label.append(radio,el('span',opt.label));group.append(label);
        });wrap.append(group);questionBox.append(wrap);
      }
      async function finish(){
        next.disabled=true;next.textContent='Reviewing…';
        try {
          const result=await jsonRequest('assessments/business-optimization-check/evaluate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({answers})});
          questionBox.hidden=true;resultsBox.hidden=false;next.hidden=true;back.hidden=true;progress.style.width='100%';
          stepText.textContent='Your preliminary summary';percent.textContent='Complete';resultsBox.replaceChildren();
          const intro=el('div',null,'result-highlight');intro.append(el('p','SUGGESTED AREAS TO INVESTIGATE','eyebrow'),el('h3',result.title),el('p',result.note));resultsBox.append(intro);
          resultsBox.append(el('h3','Practical next steps'));
          const list=el('ol',null,'result-list');(result.recommendations||[]).forEach(r=>list.append(el('li',(r.title?r.title+': ':'')+r.description)));resultsBox.append(list);
          resultsBox.append(el('p',result.disclaimer,'result-disclaimer'));
          const actions=el('div',null,'hero-actions');const contact=el('button',result.cta_label||'Discuss this summary ↗','btn btn-primary');contact.type='button';
          contact.addEventListener('click',()=>{
            try{sessionStorage.setItem('auvorentAssessment',[result.title,...questions.map(q=>q.prompt+'\n'+(q.options.find(o=>o.id===answers[q.id])?.label||''))].join('\n\n'));}catch(_){}
            window.location.href=result.cta_url||'/contact/?from=assessment';
          });const reset=el('button','Start again','btn btn-secondary');reset.type='button';reset.addEventListener('click',()=>{Object.keys(answers).forEach(k=>delete answers[k]);step=0;draw();});actions.append(contact,reset);resultsBox.append(actions);
        }catch(error){next.disabled=false;next.textContent='Try again';questionBox.append(el('p','We could not generate your summary. Please try again.','form-status'));}
      }
      next.addEventListener('click',()=>{if(!answers[questions[step].id])return;if(step<questions.length-1){step++;draw();}else finish();});
      back.addEventListener('click',()=>{if(step>0){step--;draw();}});draw();
    }catch(error){questionBox.replaceChildren(el('p','The Business Optimization Check is temporarily unavailable. Please return later.'));next.disabled=true;}
  }
  // Both scripts use only public read/evaluate and consent-gated submission APIs.
  setupContact();setupAssessment();
})();
