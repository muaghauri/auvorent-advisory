(function () {
  'use strict';
  const menuButton = document.querySelector('.menu-toggle');
  const mobileNav = document.querySelector('#mobile-nav');
  if (menuButton && mobileNav) {
    const close = () => { mobileNav.hidden = true; menuButton.setAttribute('aria-expanded', 'false'); menuButton.setAttribute('aria-label', 'Open menu'); };
    menuButton.addEventListener('click', () => {
      const opening = mobileNav.hidden;
      mobileNav.hidden = !opening;
      menuButton.setAttribute('aria-expanded', String(opening));
      menuButton.setAttribute('aria-label', opening ? 'Close menu' : 'Open menu');
    });
    mobileNav.querySelectorAll('a').forEach(a => a.addEventListener('click', close));
    window.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });
    window.addEventListener('resize', () => { if (window.innerWidth > 920) close(); });
  }

  const questions = [
    { title: 'What business challenge deserves the most attention right now?', options: [
      ['performance', 'We are growing but profitability and delivery consistency are under pressure.'],
      ['process', 'Our operations rely too heavily on manual work and workarounds.'],
      ['visibility', 'We cannot see performance trends early enough to act confidently.'],
      ['customers', 'Our customer intake, response or retention process needs improvement.']
    ]},
    { title: 'Where does the friction show up most often?', options: [
      ['handoffs', 'Handoffs, approvals and internal coordination.'],
      ['reporting', 'Reporting, spreadsheets and pulling data together.'],
      ['customer', 'Customer communication, onboarding and follow-up.'],
      ['planning', 'Capacity, forecasting or unpredictable demand.']
    ]},
    { title: 'How well can your team measure the current problem?', options: [
      ['high', 'We have reliable KPIs and a clear baseline.'],
      ['partial', 'We have reports, but key metrics are scattered or delayed.'],
      ['low', 'We rely mainly on spreadsheets and management judgment.'],
      ['unknown', 'We have not defined consistent measures yet.']
    ]},
    { title: 'How is AI being used in your organization today?', options: [
      ['none', 'We have not introduced AI in any meaningful way.'],
      ['individual', 'Some people use standalone AI tools.'],
      ['pilot', 'We have small pilots or limited automations.'],
      ['embedded', 'AI supports multiple established business workflows.']
    ]},
    { title: 'How ready is your operational data for deeper analysis?', options: [
      ['strong', 'Most critical data is accessible and consistently defined.'],
      ['mixed', 'Useful data exists, but systems and definitions vary.'],
      ['weak', 'Important information is incomplete, manual or hard to access.'],
      ['unsure', 'We need to assess data quality first.']
    ]},
    { title: 'Who could own improvements after an initial diagnostic?', options: [
      ['leader', 'A named executive or process owner has time and authority.'],
      ['shared', 'Several leaders would need to coordinate.'],
      ['limited', 'Our team has little spare implementation capacity.'],
      ['unclear', 'We have not identified an accountable owner yet.']
    ]},
    { title: 'What outcome would make an engagement valuable?', options: [
      ['margin', 'Improved margins and less avoidable work.'],
      ['experience', 'Faster and more consistent customer delivery.'],
      ['decisions', 'Better visibility, forecasting and management decisions.'],
      ['roadmap', 'A credible roadmap for practical AI and operational change.']
    ]}
  ];
  const assessment = document.querySelector('#assessment-form');
  if (assessment) {
    const answers = Array(questions.length).fill(null);
    let step = 0;
    const questionBox = document.querySelector('#assessment-question');
    const resultsBox = document.querySelector('#assessment-results');
    const next = document.querySelector('#assessment-next');
    const back = document.querySelector('#assessment-back');
    const progress = document.querySelector('#assessment-progress');
    const progressCaption = document.querySelector('#assessment-step');
    const progressPercent = document.querySelector('#assessment-percent');
    const esc = value => String(value).replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));
    function render() {
      const q = questions[step];
      const percent = Math.round((step + 1) / questions.length * 100);
      progress.style.width = `${percent}%`;
      progressCaption.textContent = `Question ${step + 1} of ${questions.length}`;
      progressPercent.textContent = `${percent}%`;
      questionBox.hidden = false;
      resultsBox.hidden = true;
      next.hidden = false;
      back.hidden = false;
      next.textContent = step === questions.length - 1 ? 'See your summary ↗' : 'Continue ↗';
      next.disabled = !answers[step];
      back.disabled = step === 0;
      questionBox.innerHTML = `<div class="assessment-q"><h2>${esc(q.title)}</h2><div role="radiogroup" aria-label="${esc(q.title)}">${q.options.map(([value, label], i) => `<label class="option-row"><input type="radio" name="question-${step}" value="${esc(value)}" ${answers[step] === value ? 'checked' : ''}/><span>${esc(label)}</span></label>`).join('')}</div></div>`;
      questionBox.querySelectorAll('input').forEach(input => input.addEventListener('change', event => {
        answers[step] = event.target.value;
        next.disabled = false;
      }));
    }
    function showResults() {
      const area = answers[0];
      const reporting = answers[2];
      const data = answers[4];
      const owner = answers[5];
      const outcome = answers[6];
      const areas = {
        performance: ['Margin and delivery diagnostic', 'Start by examining the economics of the work you deliver. Compare revenue, time, rework and handoffs before deciding what to automate.'],
        process: ['Workflow and bottleneck diagnostic', 'Map one high-volume workflow from start to finish, identify where waiting and rework occur, then review simpler changes before introducing AI.'],
        visibility: ['Decision and reporting diagnostic', 'Define the business decisions to support, examine data reliability, then design a small number of actionable KPIs and scenarios.'],
        customers: ['Customer journey diagnostic', 'Trace customer intake, handoffs and follow-up to isolate the moments that create friction and decide which changes have measurable impact.']
      };
      const [heading, explanation] = areas[area];
      const pointers = [explanation];
      if (reporting === 'low' || reporting === 'unknown' || data === 'weak' || data === 'unsure') {
        pointers.push('Prioritize a lightweight measurement and data-quality baseline before purchasing forecasting software or deploying complex models.');
      } else if (reporting === 'partial' || data === 'mixed') {
        pointers.push('Reconcile inconsistent metrics and disconnected reporting so improvement can be evaluated against a trustworthy baseline.');
      }
      if (owner === 'limited' || owner === 'unclear') pointers.push('Assign a process owner and agree on a practical implementation capacity before launching a wider initiative.');
      if (outcome === 'decisions') pointers.push('Choose the management decision you want to improve, and build reporting or forecasting only where it helps that decision.');
      if (outcome === 'roadmap') pointers.push('Define a short list of high-value use cases, with explicit feasibility, risk, ownership and ROI assumptions.');
      questionBox.hidden = true;
      resultsBox.hidden = false;
      progress.style.width = '100%';
      progressCaption.textContent = 'Your preliminary summary';
      progressPercent.textContent = 'Complete';
      next.hidden = true;
      back.hidden = true;
      resultsBox.innerHTML = `<div class="result-highlight"><p class="eyebrow">SUGGESTED AREA TO INVESTIGATE</p><h3>${esc(heading)}</h3><p>This is a preliminary screening result based on your selections—not a verified diagnosis.</p></div><h3>Practical next steps</h3><ol class="result-list">${pointers.map(p => `<li>${esc(p)}</li>`).join('')}</ol><p class="result-disclaimer">A root-cause conclusion requires actual process data, stakeholder interviews and evidence. Forecasting recommendations depend on data quality and uncertainty.</p><div class="hero-actions"><button class="btn btn-primary" type="button" id="assessment-contact">Discuss this summary ↗</button><button class="btn btn-secondary" type="button" id="assessment-reset">Start again</button></div>`;
      document.querySelector('#assessment-reset').addEventListener('click', () => { answers.fill(null); step = 0; render(); });
      document.querySelector('#assessment-contact').addEventListener('click', () => {
        try {
          const summary = [`Preliminary area: ${heading}`, ...questions.map((q, index) => {
            const match = q.options.find(o => o[0] === answers[index]);
            return `${q.title}\n${match ? match[1] : ''}`;
          })].join('\n\n');
          sessionStorage.setItem('auvorentAssessment', summary);
        } catch (_) { /* Storage is optional. */ }
        window.location.href = '/contact/?from=assessment';
      });
    }
    next.addEventListener('click', () => {
      if (!answers[step]) return;
      if (step < questions.length - 1) { step += 1; render(); } else showResults();
    });
    back.addEventListener('click', () => { if (step > 0) { step -= 1; render(); } });
    render();
  }

  const form = document.querySelector('#contact-form');
  if (form) {
    const params = new URLSearchParams(window.location.search);
    if (params.get('from') === 'assessment') {
      try {
        const prior = sessionStorage.getItem('auvorentAssessment');
        if (prior) {
          const msg = form.elements.namedItem('message');
          msg.value = `I'd like to discuss the following assessment summary:\n\n${prior.slice(0, 2500)}`;
          sessionStorage.removeItem('auvorentAssessment');
        }
      } catch (_) { /* Optional handoff. */ }
    }
    const status = document.querySelector('#contact-status');
    const submit = form.querySelector('button[type=submit]');
    form.addEventListener('submit', async event => {
      event.preventDefault();
      status.classList.remove('success');
      status.textContent = '';
      if (!form.reportValidity()) return;
      const data = Object.fromEntries(new FormData(form).entries());
      if (!data.consent) { status.textContent = 'Consent is required to submit an inquiry.'; return; }
      submit.disabled = true;
      submit.textContent = 'Sending…';
      try {
        const res = await fetch('/api/contact', { method: 'POST', headers: { 'Content-Type':'application/json' }, body: JSON.stringify(data) });
        let payload = {};
        try { payload = await res.json(); } catch (_) { /* Host may return plain text. */ }
        if (!res.ok) throw new Error(payload.error || 'The contact service is not configured yet. Please try again after the website is connected.');
        status.classList.add('success');
        status.textContent = 'Your inquiry has been received. Thank you for reaching out.';
        form.reset();
      } catch (e) {
        status.textContent = e.message || 'Unable to send the inquiry at this time.';
      } finally {
        submit.disabled = false;
        submit.textContent = 'Send inquiry ↗';
      }
    });
  }
})();
