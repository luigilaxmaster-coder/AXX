/* A desktop click is required for each sensitive command requested by a phone. */
(function (Axx) {
  'use strict';
  if (!Axx?.isNative()) return;
  const card = document.createElement('section');
  card.id = 'axx-mobile-work-approval';
  card.className = 'setup-card';
  card.innerHTML = '<strong>Órdenes del teléfono pendientes de aprobación</strong><p class="micro-copy">Revisa el comando exacto y el teléfono. PowerShell, CMD, lectura de archivos y escrituras solo se ejecutan después de pulsar «Ejecutar» aquí. La aprobación vale para esta operación.</p><div id="axx-work-pending" role="status"></div>';
  const anchor = document.getElementById('axx-remote-control');
  if (anchor) anchor.after(card); else (document.getElementById('view-settings') || document.body).append(card);
  const style = document.createElement('style');
  style.textContent = '#axx-mobile-work-approval{border:1px solid #e4bf7480;border-radius:20px;padding:20px;background:linear-gradient(145deg,#3c3024ad,#14202bd9);margin-bottom:18px}#axx-mobile-work-approval>strong{font-size:19px;color:#ffe3a6}#axx-work-pending{display:grid;gap:12px;margin-top:14px}#axx-work-pending article{padding:14px;border:1px solid #e4bf7460;border-radius:12px;background:#fff8ed0a}#axx-work-pending pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:210px;overflow:auto;color:#f1e7d6;font-size:12px}#axx-work-pending .quick-row button{min-height:42px}';
  document.head.append(style);
  const list = document.getElementById('axx-work-pending');
  let busy = false, actionBusy = false;
  function render(rows) {
    list.replaceChildren();
    if (!rows.length) { const p = document.createElement('p'); p.className='micro-copy'; p.textContent='No hay órdenes pendientes.'; list.append(p); return; }
    for (const row of rows) {
      const item = document.createElement('article');
      const title = document.createElement('strong'); title.textContent = row.command_id + ' · teléfono ' + row.device_id.slice(0,8);
      const preview = document.createElement('pre'); preview.textContent = JSON.stringify(row.inputs, null, 2);
      const actions = document.createElement('div'); actions.className='quick-row';
      for (const [approved,label] of [[true,'Ejecutar esta orden'],[false,'Rechazar']]) {
        const button = document.createElement('button'); button.type='button'; button.textContent=label;
        if (approved) button.className='primary';
        button.onclick=async()=>{
          if (actionBusy) return;
          actionBusy=true; button.disabled=true;
          try {
            const result=await Axx.backendRequest('POST','/axx-api/mobile/work/approve',{operation_id:row.operation_id,approved});
            item.replaceChildren(); const feedback=document.createElement('p'); feedback.textContent='Resultado: '+(result.state || 'sin confirmar')+' · '+row.operation_id; item.append(feedback);
            await refresh();
          } catch(error) { const feedback=document.createElement('p'); feedback.textContent='No se pudo confirmar: '+(error.message||String(error));item.append(feedback); }
          finally { actionBusy=false; button.disabled=false; }
        };
        actions.append(button);
      }
      item.append(title,preview,actions); list.append(item);
    }
  }
  async function refresh() {
    if (busy || actionBusy) return;
    busy=true;
    try { const data=await Axx.backendRequest('GET','/axx-api/mobile/work/pending');render(data.operations||[]); }
    catch(error) { list.textContent='No se pudo consultar las órdenes: '+(error.message||String(error)); }
    finally { busy=false; }
  }
  setInterval(()=>void refresh(),2000);void refresh();
})(window.Axx);
