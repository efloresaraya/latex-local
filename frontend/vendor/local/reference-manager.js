/* Módulo local: referencias de los artículos y citas pendientes. */
'use strict';
let referenceModel=null,referenceContext=null,referenceBusy=false,referenceRequested=null;
function renderReferenceSide(host,query){
 const launch=el('button','reference-launch','＋ Incorporar referencias');launch.onclick=()=>openReferenceManager(query).catch(handleError);host.append(launch);
 const organize=el('button','reference-launch','↕ Organizar bibliografía');organize.onclick=async()=>{try{await openReferenceManager();await previewBibliographyOrder();}catch(error){handleError(error);}};host.append(organize);
 for(const ref of (state.missingRefs||[]).filter(r=>r.key.toLowerCase().includes(query))){
  const row=el('button','ref-row ref-missing');row.append(el('b','',ref.key),el('small','','Falta en el .bib · '+ref.path),el('code','ref-cite','\\cite{'+ref.key+'}'));
  row.onclick=()=>openReferenceManager(ref.key,ref.key,ref.path).catch(handleError);host.append(row);
 }
}
async function openReferenceManager(query='',requested=null,requestedPath=null){
 await saveAll();
 if(requestedPath&&state.current!==requestedPath)await openFile(requestedPath);
 const doc=currentDoc();referenceContext=doc&&ext(doc.path)==='tex'?{project:state.project,path:doc.path,doc,selection:doc.cm.listSelections(),requested}:null;
 referenceRequested=requested;referenceModel=await api(base()+'/references');
 const sourceFilter=$('reference-filter');
 for(const option of [...sourceFilter.options])if(option.value.startsWith('source:'))option.remove();
 for(const source of [...new Set(referenceModel.catalog.flatMap(row=>row.sources))].sort()){const option=el('option','',source);option.value='source:'+source;sourceFilter.append(option);}
 $('reference-search').value=query;$('reference-filter').value=requested?'all':'missing';$('reference-feedback').hidden=true;
 $('reference-target').replaceChildren();for(const b of referenceModel.bibs){const option=el('option','',b.path+' · '+b.count+' entradas');option.value=b.path;$('reference-target').append(option);}
 const ieee=referenceModel.style==='IEEEtran';
 $('references-order').textContent=ieee?'IEEEtran numera por primera aparición de la cita en el texto. La entrada se incorpora al final del .bib, conservando el contenido anterior. Compila después de insertar citas para actualizar los números.':'La entrada se incorpora al final del .bib, conservando el contenido anterior. La numeración y el orden final dependen del estilo bibliográfico; compila después de insertar citas.';
 $('manual-reference').open=false;$('reference-bibtex').value='';
 resetDoiLookup();setReferenceMode(query||requested?'local':'doi');
 renderReferenceResults();openDialog('references-dialog');
}
function referenceCitation(key,relatedKeys=[]){
 const wrap=el('div','reference-citation'),cite='\\cite{'+key+'}';
 const code=el('code','',cite),copy=el('button','','Copiar cita');copy.onclick=async()=>{try{await navigator.clipboard.writeText(cite);toast('Cita copiada: '+cite);}catch{toast('Selecciona y copia el comando que aparece junto al botón.');}};
 const insert=el('button','','Insertar en el texto');insert.disabled=!referenceContext;
 if(!referenceContext)insert.title='Abre un archivo .tex antes de entrar al módulo.';
 insert.onclick=()=>{
  const ctx=referenceContext;
  if(!ctx||state.project!==ctx.project||state.docs.get(ctx.path)!==ctx.doc)return toast('Abre de nuevo el módulo desde el archivo donde quieres citar.');
  const destination=ctx.doc;destination.cm.setSelections(ctx.selection);destination.cm.replaceSelection(cite,'end','+input');
  $('references-dialog').close();toast('Cita insertada en '+ctx.path+'. Compila para actualizar su número.');editor.focus();
 };
 wrap.append(code,copy,insert);
 if(referenceContext?.requested&&referenceContext.requested!==key&&relatedKeys.includes(referenceContext.requested)){
  const fix=el('button','','Corregir clave '+referenceContext.requested+' → '+key);
  fix.onclick=()=>{
   const ctx=referenceContext;if(state.project!==ctx.project||state.docs.get(ctx.path)!==ctx.doc)return toast('Reabre el módulo desde el archivo de la cita.');
   const source=ctx.doc.cm.getValue(),clean=stripComments(source),edits=[];
   for(const match of clean.matchAll(/\\(?:[Cc]ite\w*|nocite)\*?\s*(?:\[[^\]]*\]\s*)*\{([^}]+)\}/g)){
    const start=match.index+match[0].lastIndexOf('{')+1;
    let offset=0;for(const part of match[1].split(',')){const trim=part.trim();if(trim===ctx.requested){const from=start+offset+part.indexOf(trim);edits.push({from,to:from+trim.length});}offset+=part.length+1;}
   }
   if(!edits.length)return toast('La clave pendiente ya no aparece en este archivo.');
   for(const edit of edits.reverse())ctx.doc.cm.replaceRange(key,ctx.doc.cm.posFromIndex(edit.from),ctx.doc.cm.posFromIndex(edit.to),'+input');
   $('references-dialog').close();toast('Clave corregida en '+ctx.path+'. Compila para actualizar la cita.');editor.focus();
  };wrap.append(fix);
 }
 return wrap;
}
function renderReferenceResults(){
 const host=$('reference-results');host.replaceChildren();if(!referenceModel)return;
 const q=$('reference-search').value.trim().toLocaleLowerCase(),filter=$('reference-filter').value;
 const rows=referenceModel.catalog.filter(r=>(filter!=='missing'||!r.present_key)&&(!filter.startsWith('source:')||r.sources.includes(filter.slice(7)))&&[r.key,...r.aliases,r.title,r.description,...r.dois].join(' ').toLocaleLowerCase().includes(q));
 const missing=referenceModel.catalog.filter(r=>!r.present_key).length;
 $('reference-count').textContent=`${rows.length} coincidencias · ${missing} referencias de los artículos faltan en la bibliografía. Catálogo de fuentes locales, sin consulta externa.`;
 for(const r of rows){
  const card=el('article','reference-card');card.append(el('small','reference-source',r.sources.join(' · ')),el('h3','',r.key),el('p','',r.title));
  if(r.dois.length)card.append(el('small','reference-doi','DOI: '+r.dois.join(' · ')));
  const details=el('details','reference-entry');details.append(el('summary','','Ver entrada BibTeX · '+r.format),el('pre','',r.bibtex));card.append(details);
  if(r.present_key){card.append(el('p','reference-present','✓ Ya está en el proyecto · clave '+r.present_key));card.append(referenceCitation(r.present_key,r.aliases));}
  else{
   if(r.conflict)card.append(el('p','reference-error',r.conflict));
   const command=el('code','ref-cite','\\cite{'+r.key+'}');card.append(command);
   const button=el('button','primary','＋ Añadir al .bib');button.disabled=referenceBusy||!referenceModel.bibs.length||Boolean(r.conflict);
   button.onclick=()=>incorporateReference({catalog_id:r.id},button).catch(referenceError);card.append(button);
  }
  host.append(card);
 }
 if(!rows.length){host.append(el('p','empty-note','No hay coincidencias en los artículos locales. Puedes incorporar una entrada BibTeX debajo.'));if(referenceRequested)$('manual-reference').open=true;}
 $('reference-add-manual').disabled=referenceBusy||!referenceModel.bibs.length;
 if(!referenceModel.bibs.length)$('reference-count').textContent='El documento principal no declara una bibliografía .bib. Añade primero \\bibliography{nombre} en tu documento.';
}
function referenceError(error){$('reference-feedback').hidden=false;$('reference-feedback').className='reference-feedback reference-error';$('reference-feedback').textContent=error.message;}
async function incorporateReference(data,button){
 if(referenceBusy)return;
 const path=$('reference-target').value,bib=referenceModel.bibs.find(b=>b.path===path);
 if(!bib)throw new Error('Selecciona una bibliografía de destino.');
 referenceBusy=true;button.disabled=true;
 try{
  // Flush open buffers before a CAS-protected addition. No blind overwrite on conflict.
  await saveAll();
  const result=await api(base()+'/references','POST',{...data,bib_path:path,revision:bib.revision,requested_key:data.bibtex?referenceRequested:null});
  await checkExternal();await refreshFiles();await indexSources();referenceModel=await api(base()+'/references');
  $('reference-feedback').hidden=false;$('reference-feedback').className='reference-feedback';
  $('reference-feedback').replaceChildren(el('strong','',result.added?'Referencia incorporada a '+result.path+' con respaldo.':'Ya existe en el proyecto; se utiliza su clave y no se duplica.'),referenceCitation(result.key,[result.requested_key]));
  if(referenceContext?.requested===result.key)referenceContext.requested=null;
  for(const option of $('reference-target').options){const updated=referenceModel.bibs.find(b=>b.path===option.value);if(updated)option.textContent=updated.path+' · '+updated.count+' entradas';}
  referenceRequested=null;$('reference-bibtex').value='';referenceBusy=false;renderReferenceResults();return result;
 }finally{referenceBusy=false;button.disabled=false;$('reference-add-manual').disabled=!referenceModel?.bibs.length;}
}
$('reference-search').oninput=renderReferenceResults;$('reference-filter').onchange=renderReferenceResults;
$('reference-add-manual').onclick=()=>incorporateReference({bibtex:$('reference-bibtex').value},$('reference-add-manual')).catch(referenceError);
function refreshMissingCitationMarks(){
 const known=new Set(state.refs.map(r=>r.key));
 for(const doc of state.docs.values()){
  for(const mark of doc.referenceMarks||[])mark.clear();doc.referenceMarks=[];
  if(ext(doc.path)!=='tex')continue;
  const clean=stripComments(doc.cm.getValue());
  for(const match of clean.matchAll(/\\(?:[Cc]ite\w*|nocite)\*?\s*(?:\[[^\]]*\]\s*)*\{([^}]+)\}/g)){
   const start=match.index+match[0].lastIndexOf('{')+1;let offset=0;
   for(const part of match[1].split(',')){
    const key=part.trim();if(key&&key!=='*'&&!known.has(key)){
     const from=start+offset+part.indexOf(key),mark=doc.cm.markText(doc.cm.posFromIndex(from),doc.cm.posFromIndex(from+key.length),{className:'missing-citation',title:'Falta en la bibliografía. Clic para incorporar '+key});
     mark.referenceKey=key;doc.referenceMarks.push(mark);
    }
    offset+=part.length+1;
   }
  }
 }
}
editor.on('mousedown',(cm,event)=>{
 if(!event.target.closest?.('.missing-citation'))return;
 const position=cm.coordsChar({left:event.clientX,top:event.clientY},'window');
 const mark=cm.findMarksAt(position).find(m=>m.referenceKey);
 if(mark){event.preventDefault();openReferenceManager(mark.referenceKey,mark.referenceKey,state.current).catch(handleError);}
});

let doiSequence=0,doiResult=null;
function setReferenceMode(mode){
 $('reference-local-section').hidden=mode!=='local';$('reference-doi-section').hidden=mode!=='doi';
 $('reference-tab-doi').setAttribute('aria-pressed',String(mode==='doi'));$('reference-tab-local').setAttribute('aria-pressed',String(mode==='local'));
}
function resetDoiLookup(){doiSequence++;doiResult=null;$('doi-input').value='';$('doi-result').hidden=true;$('doi-status').textContent='';$('doi-lookup-button').disabled=false;$('doi-external').checked=localGet('latex-doi-external',true);}
$('reference-tab-doi').onclick=()=>setReferenceMode('doi');$('reference-tab-local').onclick=()=>setReferenceMode('local');
$('doi-external').onchange=()=>localSet('latex-doi-external',$('doi-external').checked);
$('doi-input').oninput=()=>{doiSequence++;doiResult=null;$('doi-result').hidden=true;$('doi-status').textContent='';};
$('doi-form').onsubmit=async event=>{
 event.preventDefault();const project=state.project,sequence=++doiSequence;
 $('doi-lookup-button').disabled=true;$('doi-status').className='muted';$('doi-status').textContent='Revisando tus archivos y buscando metadatos…';$('doi-result').hidden=true;$('reference-feedback').hidden=true;
 try{
  await saveAll();
  const data=await api(base()+'/references/doi','POST',{doi:$('doi-input').value,allow_external:$('doi-external').checked,requested_key:referenceRequested});
  if(sequence!==doiSequence||project!==state.project)return;
  doiResult=data;renderDoiResult();$('doi-status').textContent=data.present_key?'DOI encontrado: ya está en la bibliografía activa.':data.matches.length?'DOI encontrado en un .bib que no está activo. Puedes incorporarlo a la bibliografía del proyecto.':'Referencia encontrada. Revisa los datos antes de añadirla al .bib.';
 }catch(error){if(sequence===doiSequence){$('doi-status').className='reference-feedback reference-error';$('doi-status').textContent=error.message;}}
 finally{if(project===state.project)$('doi-lookup-button').disabled=false;}
};
function renderDoiResult(){
 const data=doiResult,host=$('doi-result');host.replaceChildren();host.hidden=false;
 const card=el('article','reference-card');card.append(el('small','reference-source',data.source+(data.cached?' · consulta reciente':'')),el('h3','',data.title),el('p','',[data.author,data.year].filter(Boolean).join(' · ')),el('small','reference-doi','DOI: '+data.doi));
 if(data.source_url){const source=el('a','doi-source-link','Ver registro de metadatos ↗');source.href=data.source_url;source.target='_blank';source.rel='noopener noreferrer';card.append(source);}
 for(const match of data.matches)card.append(el('p','reference-present',`✓ ${match.path} · clave ${match.key}${match.active?' · bibliografía activa':' · no utilizado por el documento principal'}`));
 if(data.citations.length)card.append(el('p','muted','Citada en '+data.citations.slice(0,5).map(c=>c.path+':'+c.line).join(', ')+(data.citations.length>5?' y otras ubicaciones.':'.')));
 else if(data.matches.length)card.append(el('p','muted','Está guardada, pero no se detectaron citas con esta clave en los archivos activos.'));
 for(const warning of data.warnings)card.append(el('p','reference-error',warning));
 const keyLabel=el('label','','Clave para citar'),key=el('input');key.id='doi-citation-key';key.value=data.key;key.disabled=Boolean(data.present_key);keyLabel.htmlFor=key.id;card.append(keyLabel,key);
 const preview=el('pre','doi-bib-preview',data.bibtex);card.append(preview);
 const citationHost=el('div');
 if(data.present_key)citationHost.append(referenceCitation(data.present_key,referenceContext?.requested?[referenceContext.requested]:[]));
 else{
  const cite=el('code','ref-cite',data.cite);citationHost.append(cite);
  const add=el('button','primary','＋ Añadir al .bib');add.disabled=!referenceModel.bibs.length;
  key.oninput=()=>{const candidate=key.value.trim();preview.textContent=data.bibtex.replace(/^(@\w+\s*[({]\s*)[^,]+/,(_,prefix)=>prefix+candidate);cite.textContent='\\cite{'+candidate+'}';};
  add.onclick=async()=>{
   const requested=key.value.trim();if(!/^[A-Za-z0-9_:.+/-]+$/.test(requested))return referenceError(new Error('Usa una clave sin espacios ni llaves, por ejemplo Autor2026.'));
   try{
    const result=await incorporateReference({bibtex:preview.textContent},add);if(!result)return;
    doiResult={...data,key:result.key,cite:result.cite,present_key:result.key,bibtex:preview.textContent,matches:[{key:result.key,path:result.path,active:true}]};
    renderDoiResult();$('doi-status').textContent=result.added?'Referencia añadida con respaldo. Ya puedes copiar o insertar la cita.':'El DOI ya existía: se utiliza la clave guardada sin duplicar la referencia.';
   }catch(error){referenceError(error);}
  };citationHost.append(add);
 }
 card.append(citationHost);host.append(card);
}

/* Organización voluntaria, siempre precedida de una vista previa revisable. */
let bibliographyOrderPlan=null,bibliographyOrderProject=null;
async function previewBibliographyOrder(path=null){
 await saveAll();
 const selected=path||$('reference-target').value;
 if(!selected)throw new Error('El documento principal no declara una bibliografía .bib.');
 const project=state.project;
 const plan=await api(base()+'/references/organize/preview','POST',{bib_path:selected});
 if(state.project!==project)throw new Error('Cambió el proyecto. Abre de nuevo la vista previa.');
 bibliographyOrderPlan=plan;bibliographyOrderProject=project;
 $('bibliography-order-summary').textContent=`${plan.path}: ${plan.used.length} referencias usadas y ${plan.unused.length} sin citar. Revisados ${plan.sources.length} archivos .tex.`;
 $('bibliography-order-warning').textContent=plan.wildcard?'Se encontró \\nocite{*}: todas las entradas se incorporan a la bibliografía. Se conserva el orden actual para proteger su numeración.':plan.missing.length?'Hay claves citadas que faltan en los .bib: '+plan.missing.join(', ')+'. Organizar no crea esas referencias.':'';
 $('bibliography-order-before').value=plan.before;$('bibliography-order-after').value=plan.after;
 const host=$('bibliography-order-list');host.replaceChildren();
 const table=el('table'),head=el('tr');for(const title of ['Antes','Después','Clave','Uso'])head.append(el('th','',title));table.append(head);
 for(const entry of plan.order){const row=el('tr',entry.old===entry.new?'':'bibliography-moved');row.append(el('td','',entry.old),el('td','',entry.new),el('td','',entry.key),el('td','',entry.used?'Usada':'Sin citar'));table.append(row);}
 host.append(table);$('bibliography-order-apply').disabled=!plan.changed;
 $('bibliography-order-status').textContent=plan.changed?'Revisa el orden propuesto antes de aplicarlo.':'La bibliografía ya tiene el orden propuesto. No hay cambios que guardar.';
 $('references-dialog').close();openDialog('bibliography-order-dialog');
}
$('reference-organize').onclick=()=>previewBibliographyOrder().catch(referenceError);
$('bibliography-order-refresh').onclick=()=>previewBibliographyOrder(bibliographyOrderPlan?.path).catch(error=>{$('bibliography-order-status').textContent=error.message;$('bibliography-order-apply').disabled=true;});
$('bibliography-order-apply').onclick=async()=>{
 const plan=bibliographyOrderPlan,button=$('bibliography-order-apply');
 if(!plan||state.project!==bibliographyOrderProject)return;
 button.disabled=true;
 try{
  await saveAll();
  const result=await api(base()+'/references/organize','POST',{bib_path:plan.path,token:plan.token});
  await checkExternal();await refreshFiles();await indexSources();
  $('bibliography-order-status').textContent=result.changed?'Bibliografía organizada. La versión anterior está disponible en el historial.':'No había cambios que guardar.';
  toast('Bibliografía organizada con respaldo.');
 }catch(error){$('bibliography-order-status').textContent=error.message+' Actualiza la vista previa para continuar.';}
};
