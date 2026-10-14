/* Referência HTML: valores importados das capturas, separados do SQLite do app. */
(() => {
  const names = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];
  const monthly = {10:28.65,9:50.40,8:14.48,7:.12,6:0,5:12.85,4:16.25,3:16.81};
  const daily = {4:.90,5:2.44,6:3.16,7:3.26,8:2.22,9:3.33,10:3.04,11:1.28};
  const summary = document.getElementById('energy-summary');
  if (!summary) {
    if (location.hash === '#energy-detail-action') requestAnimationFrame(() => document.getElementById('energy-detail-action')?.focus());
    return;
  }
  const dailyView = document.getElementById('energy-daily');
  const heading = document.getElementById('energy-heading');
  const back = document.getElementById('energy-back');
  let month = 10, selected = 11, start = 3, summaryScroll = 0;
  function renderMonths() {
    const container = document.getElementById('energy-months');
    container.replaceChildren();
    for (const m of Object.keys(monthly).map(Number).sort((a,b)=>b-a)) {
      const button = document.createElement('button'); button.className = 'month-row';
      button.dataset.month = String(m);
      button.innerHTML = '<span><strong>'+names[m-1]+'</strong><span class="energy-muted">Referência Smart Life</span></span><span><span class="month-total">'+monthly[m].toFixed(2)+'</span><svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="m6 4 4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></span>';
      button.setAttribute('aria-label', names[m-1]+', '+monthly[m].toFixed(2)+' kWh. Ver dias.');
      button.addEventListener('click', () => openMonth(m)); container.append(button);
    }
  }
  function openMonth(m) {
    summaryScroll = window.scrollY;
    month = m; selected = m === 10 ? 11 : 1; start = m === 10 ? 3 : 0;
    summary.hidden = true; dailyView.hidden = false; heading.textContent = names[m-1];
    back.setAttribute('aria-label','Voltar ao resumo mensal');
    document.getElementById('month-total').textContent = monthly[m].toFixed(2);
    document.getElementById('month-origin').textContent = 'Referência Smart Life • Ano 2026';
    document.getElementById('daily-origin').textContent = m === 10 ? 'Barras anteriores aproximadas pela captura de referência.' : 'A referência deste mês fornece apenas o total mensal.';
    drawChart(); heading.focus(); window.scrollTo({top:0});
  }
  function drawChart() {
    const count = new Date(2026, month, 0).getDate();
    const days = Array.from({length:8},(_,i)=>start+i+1);
    const value = day => month === 10 ? daily[day] : undefined;
    const upper = Math.max(1, Math.ceil(Math.max(...days.map(d=>value(d)||0))*2)/2);
    const axis = document.getElementById('chart-axis'); axis.replaceChildren();
    for(let i=7;i>=0;i--) { const el=document.createElement('span'); el.textContent=(upper*i/7).toFixed(1); axis.append(el); }
    const bars = document.getElementById('chart-bars'); bars.replaceChildren();
    for(const d of days) {
      const v=value(d), active=d===selected, button=document.createElement('button');
      button.className='bar-button'; button.setAttribute('aria-pressed',String(active));
      button.dataset.empty=String(v===undefined);
      button.setAttribute('aria-label',`${d}/${month}: ${v===undefined?'sem leitura':v.toFixed(2)+' kWh'}`);
      const label=document.createElement('span'); label.className='bar-value'+(active?' selected':''); label.textContent=v===undefined?'--':v.toFixed(2);
      const fill=document.createElement('span'); fill.className='bar-fill'; fill.style.height=(v===undefined?2:Math.max(2,v/upper*228))+'px';
      const date=document.createElement('span'); date.className='bar-label';
      const monthPrefix=document.createElement('span'); monthPrefix.className='month-prefix'; monthPrefix.textContent=String(month).padStart(2,'0')+'-';
      date.append(monthPrefix, document.createTextNode(String(d).padStart(2,'0')));
      button.append(label,fill,date); button.addEventListener('click',()=>{selected=d;drawChart(); bars.children[d-start-1]?.focus();}); bars.append(button);
    }
    document.getElementById('days-range').textContent=`Dias ${String(start+1).padStart(2,'0')}–${String(start+8).padStart(2,'0')}`;
    document.getElementById('days-prev').disabled=start===0;
    document.getElementById('days-next').disabled=start+8>=count;
    document.getElementById('chart-empty').hidden=month===10;
  }
  document.getElementById('days-prev').addEventListener('click',()=>{start=Math.max(0,start-8);selected=start+1;drawChart();});
  document.getElementById('days-next').addEventListener('click',()=>{start=Math.min(new Date(2026,month,0).getDate()-8,start+8);selected=start+1;drawChart();});
  back.addEventListener('click',()=>{
    if(dailyView.hidden) location.href='../telemetria_tomada_ekaza/code.html#energy-detail-action';
    else {dailyView.hidden=true;summary.hidden=false;heading.textContent='Consumo de energia';back.setAttribute('aria-label','Voltar à telemetria');document.querySelector('.month-row[data-month="'+month+'"]').focus({preventScroll:true});window.scrollTo({top:summaryScroll});}
  });
  document.getElementById('energy-year').addEventListener('change',renderMonths);
  renderMonths();
})();
