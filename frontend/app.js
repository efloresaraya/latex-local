'use strict';
const $ = id => document.getElementById(id);
const state = {project:null, root:null, cfg:{}, files:[], docs:new Map(), current:null, pane:'files', outline:[], refs:[], busy:false, navigating:false, loadID:0, pdfURL:null, folders:new Set()};
const TEXT = new Set(['tex','bib','sty','cls','bst','txt','md','cfg','def','ins','dtx','tikz','csv','json']);
const ext = path => path.split('.').pop().toLowerCase();
const enc = encodeURIComponent;
const fileURL = path => path.split('/').map(enc).join('/');
const base = () => `/api/projects/${enc(state.project)}`;
let toastTimer, noticeAction, conflictAction, updateTimer, labelUpdateTimer, pollBusy=false;
function el(tag, cls, text){ const node=document.createElement(tag); if(cls)node.className=cls;if(text!==undefined)node.textContent=text;return node; }
function openDialog(id){if(!$(id).open)$(id).showModal();}
function toast(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,4500);}
function notice(message, action=null){$('notice-message').textContent=message;$('notice').hidden=false;$('notice-action').hidden=!action;noticeAction=action;}
function handleError(error){const blocked=[...state.docs.values()].find(d=>d.blocked);notice(error.message || String(error),blocked?()=>showConflict(blocked):null);}
async function api(url, method='GET', body=null){
 const options={method,headers:{}};if(body!==null){options.headers['Content-Type']='application/json';options.body=JSON.stringify(body);}
 let response;try{response=await fetch(url,options);}catch(e){throw new Error('Sin conexión con el servidor. Conservamos el borrador en este navegador; vuelve a conectar para guardar en disco.');}
 if(!response.ok){let data;try{data=await response.json();}catch{data={detail:response.statusText};}const error=new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));error.status=response.status;throw error;}
 return response.json();
}
function localSet(key, value){try{localStorage.setItem(key,JSON.stringify(value));return true;}catch(e){notice('El navegador no pudo conservar el borrador de recuperación. Guarda en disco antes de cerrar.');return false;}}
function localGet(key, fallback=null){try{return JSON.parse(localStorage.getItem(key))??fallback;}catch{return fallback;}}
function draftKey(path){return `latex-draft:${state.root}:${path}`;}
function preserveDraft(doc, reason='edición'){
 const data={path:doc.path,root:state.root,project:state.project,content:doc.cm.getValue(),revision:doc.revision,updated:new Date().toISOString(),reason};
 return localSet(draftKey(doc.path),data);
}
function archiveDraft(doc, reason){const key=`latex-recovery:${state.root}:${Date.now()}:${Math.random().toString(16).slice(2)}`;return localSet(key,{path:doc.path,root:state.root,content:doc.cm.getValue(),updated:new Date().toISOString(),reason});}
function removeDraftIfSaved(doc){if(!doc.dirty){try{localStorage.removeItem(draftKey(doc.path));}catch{}}}
const editor=CodeMirror.fromTextArea($('source'),{
 mode:'stex',lineNumbers:true,lineWrapping:true,matchBrackets:true,autoCloseBrackets:true,styleActiveLine:true,
 indentUnit:2,tabSize:2,viewportMargin:15,readOnly:true,
 extraKeys:{'Cmd-S':()=>saveAll().catch(handleError),'Ctrl-S':()=>saveAll().catch(handleError),'Cmd-Enter':()=>compile(),'Ctrl-Enter':()=>compile(),
  'Cmd-F':()=>openSearch(),'Ctrl-F':()=>openSearch(),'Ctrl-Space':()=>editor.showHint({hint:complete,completeSingle:false}),
  'Tab':cm=>{if(cm.somethingSelected())cm.indentSelection('add');else cm.replaceSelection('  ','end','+input');}}
});
function currentDoc(){return state.docs.get(state.current);}
function complete(cm){
 const cursor=cm.getCursor(),line=cm.getLine(cursor.line).slice(0,cursor.ch);
 let m=line.match(/\\cite\w*\{([^}]*)$/);let list,from;
 if(m){const prefix=m[1].split(',').pop().trim();from=cursor.ch-prefix.length;list=state.refs.filter(r=>r.key.toLowerCase().startsWith(prefix.toLowerCase())).map(r=>({text:r.key,displayText:r.key+'  —  '+r.title.slice(0,80)}));}
 else if((m=line.match(/\\(?:ref|eqref|autoref)\{([^}]*)$/))){from=cursor.ch-m[1].length;list=state.labels.filter(x=>x.startsWith(m[1]));}
 else return LatexCompletion.hints(cm);
 return {list,from:CodeMirror.Pos(cursor.line,from),to:cursor};
}
state.labels=[];
editor.on('inputRead',(cm,change)=>{
 const doc=currentDoc();if(!doc||doc.loading||ext(doc.path)!=='tex')return;
 if(LatexCompletion.shouldOpen(cm,change)&&!cm.state.completionActive)cm.showHint({hint:complete,completeSingle:false});
});
editor.on('beforeChange',(cm,change)=>{
 const doc=currentDoc();if(!doc||doc.loading||ext(doc.path)!=='tex'||doc.cm!==cm.getDoc())return;
 LatexAccents.beforeChange(cm,change);
});
editor.on('change',()=>{
 const doc=currentDoc();if(!doc || doc.cm!==editor.getDoc() || doc.loading)return;
 doc.dirty=true;doc.generation++;preserveDraft(doc);renderTabs();renderSaveStatus();updateCounters();
 clearTimeout(doc.timer);doc.timer=setTimeout(()=>saveDoc(doc).catch(handleError),1000);
 clearTimeout(updateTimer);updateTimer=setTimeout(()=>indexSources().catch(handleError),1800);
 clearTimeout(labelUpdateTimer);labelUpdateTimer=setTimeout(()=>refreshUnusedLabelMarks(),650);
});
editor.on('changes',(cm,changes)=>{
 const doc=currentDoc();if(!doc||doc.loading||ext(doc.path)!=='tex'||doc.cm!==cm.getDoc())return;
 CitationMerge.apply(cm,changes);
});
editor.on('cursorActivity',updateCounters);
function updateCounters(){
 const p=editor.getCursor();$('cursor-position').textContent=`Línea ${p.line+1} · Columna ${p.ch+1}`;
 const text=editor.getValue().replace(/%[^\n]*/g,'').replace(/\\[a-zA-Z]+/g,' ');
 $('word-count').textContent=`${(text.match(/[\p{L}\p{N}]+/gu)||[]).length.toLocaleString('es-CL')} palabras en el archivo`;
}
function renderSaveStatus(){
 const docs=[...state.docs.values()];const blocked=docs.some(d=>d.blocked),dirty=docs.some(d=>d.dirty),saving=docs.some(d=>d.saving);
 $('save-status').className=blocked?'error':dirty?'dirty':'';
 $('save-status').textContent=blocked?'Conflicto pendiente de revisión':saving?'Guardando en tu carpeta…':dirty?'Cambios pendientes de guardar':'✓ Todo guardado en tu carpeta';
 $('save-button').disabled=!state.project;
}
async function saveDoc(doc){
 clearTimeout(doc.timer);
 if(doc.pending){await doc.pending;if(doc.dirty)return saveDoc(doc);return;}
 if(!doc.dirty)return;
 if(doc.blocked)throw new Error(`Revisa el conflicto en ${doc.path} antes de guardar.`);
 const value=doc.cm.getValue(),generation=doc.generation,project=state.project;
 doc.saving=true;renderSaveStatus();
 doc.pending=(async()=>{
  try{
   const saved=await api(`/api/projects/${enc(project)}/files/${fileURL(doc.path)}`,'PUT',{content:value,revision:doc.revision});
   doc.revision=saved.revision;doc.dirty=doc.generation!==generation;doc.error=null;
   if(doc.dirty)preserveDraft(doc);else removeDraftIfSaved(doc);
  }catch(error){
   doc.error=error.message;doc.dirty=true;preserveDraft(doc);
   if(error.status===409){doc.blocked=true;notice(`Cambió ${doc.path} fuera de esta pestaña. Tu texto está conservado.`,()=>showConflict(doc));}
   throw error;
  }finally{doc.saving=false;doc.pending=null;renderTabs();renderSaveStatus();}
 })();
 await doc.pending;
 if(doc.dirty&&!doc.blocked){clearTimeout(doc.timer);doc.timer=setTimeout(()=>saveDoc(doc).catch(handleError),1000);}
 else if($('auto-compile').checked && !state.busy){clearTimeout(state.compileTimer);state.compileTimer=setTimeout(compile,2500);}
}
async function saveAll(){
 clearTimeout(state.compileTimer);
 for(const doc of state.docs.values()){let passes=0;do{await saveDoc(doc);if(++passes>10)throw new Error('Continúas escribiendo. Espera un momento antes de compilar.');}while(doc.dirty);}
 renderSaveStatus();
}
function renderTabs(){
 const host=$('tabs');host.replaceChildren();
 for(const doc of state.docs.values()){
  const tab=el('div','tab'+(doc.path===state.current?' active':''));tab.setAttribute('role','tab');tab.setAttribute('aria-selected',String(doc.path===state.current));tab.tabIndex=0;
  tab.title=doc.path;tab.append(el('span','',doc.path.split('/').pop()));
  if(doc.dirty)tab.append(el('span','dirty-dot','●'));
  const close=el('button','close-tab','×');close.title='Cerrar archivo';close.setAttribute('aria-label','Cerrar '+doc.path);close.onclick=e=>{e.stopPropagation();closeFile(doc.path).catch(handleError);};tab.append(close);
  tab.onclick=()=>openFile(doc.path).catch(handleError);tab.onkeydown=e=>{if(e.key==='Enter')tab.click();};host.append(tab);
 }
}
async function closeFile(path){
 const doc=state.docs.get(path);if(doc)await saveDoc(doc);
 state.docs.delete(path);if(state.current===path){state.current=null;const next=[...state.docs.keys()].pop();if(next)await openFile(next);else{editor.swapDoc(new CodeMirror.Doc('','stex'));editor.setOption('readOnly',true);$('file-label').textContent='Selecciona un archivo';}}
 renderTabs();
}
async function openFile(path,line=null){
 if(state.navigating)return;state.navigating=true;
 try{
  if(!TEXT.has(ext(path))){await previewAsset(path);return;}
  let doc=state.docs.get(path);
  if(!doc){
   const data=await api(`${base()}/files/${fileURL(path)}`);
   doc={path,cm:new CodeMirror.Doc(data.content,ext(path)==='tex'?'stex':'text/plain'),revision:data.revision,dirty:false,generation:0,blocked:false};
   const draft=localGet(draftKey(path));
   if(draft && draft.content!==data.content){doc.cm.setValue(draft.content);doc.dirty=true;doc.generation++;doc.blocked=draft.revision!==data.revision;doc.revision=data.revision;
    notice(doc.blocked?`Recuperamos tu borrador de ${path}; el disco tiene otra versión. Revísalas antes de guardar.`:`Recuperamos tu borrador pendiente de ${path}.`,doc.blocked?()=>showConflict(doc):null);
   }
   state.docs.set(path,doc);
  }
  state.current=path;editor.swapDoc(doc.cm);editor.setOption('readOnly',false);
  $('asset-preview').hidden=true;$('editor-host').hidden=false;$('file-label').textContent=path;
  refreshMissingCitationMarks();refreshUnusedLabelMarks();renderTabs();renderSide();renderSaveStatus();editor.refresh();updateCounters();
  if(line){editor.setCursor(line-1,0);editor.scrollIntoView({line:line-1,ch:0},120);}
  if(doc.dirty&&!doc.blocked){doc.timer=setTimeout(()=>saveDoc(doc).catch(handleError),1600);}
  localSet(`latex-last-file:${state.root}`,path);
 }finally{state.navigating=false;}
}
async function previewAsset(path){
 const container=$('asset-preview');container.replaceChildren();const url=`${base()}/raw/${fileURL(path)}`;
 if(['png','jpg','jpeg','gif','webp'].includes(ext(path))){const image=el('img');image.src=url;image.alt=path;container.append(image);}
 else if(ext(path)==='pdf'){const frame=el('iframe');frame.src=url;frame.title=path;container.append(frame);}
 else{const link=el('a','',`Descargar ${path} ↗`);link.href=url;link.download=path.split('/').pop();container.append(link);}
 $('asset-preview').hidden=false;$('editor-host').hidden=true;$('file-label').textContent=path+' · Vista de recurso';
}
async function refreshFiles(){state.files=await api(`${base()}/files`);const selected=state.cfg.main_file;$('main-file').replaceChildren();for(const f of state.files.filter(f=>ext(f.path)==='tex')){const o=el('option','',f.path);o.value=f.path;$('main-file').append(o);}$('main-file').value=selected;renderSide();}
function renderSide(){
 const host=$('side-content');host.replaceChildren();const query=$('file-search').value.toLocaleLowerCase();
 if(state.pane==='files'){
  const paths=state.files.filter(f=>f.path.toLocaleLowerCase().includes(query));const tree={};
  for(const file of paths){const parts=file.path.split('/');let node=tree;parts.forEach((part,i)=>{if(i===parts.length-1)node[part]={file};else node=node[part]??={};});}
  function draw(node,depth=0){for(const [name,value] of Object.entries(node).sort(([a,av],[b,bv])=>(!!av.file-!!bv.file)||a.localeCompare(b))){
   if(value.file){const f=value.file,row=el('button','file-row'+(f.path===state.current?' active':''));row.style.paddingLeft=(9+depth*12)+'px';row.title=f.path;const type=ext(name);row.append(el('span','file-type '+type,type==='tex'?'TEX':type==='bib'?'BIB':['png','jpg','jpeg','svg'].includes(type)?'▧':type==='pdf'?'PDF':'·'),el('span','name',name));row.onclick=()=>openFile(f.path).catch(handleError);host.append(row);}
   else{const key=name+'@'+depth,opened=Boolean(query)||state.folders.has(key);const row=el('button','file-row folder',(opened?'▾  ':'▸  ')+name);row.style.paddingLeft=(12+depth*12)+'px';row.setAttribute('aria-expanded',String(opened));row.onclick=()=>{if(state.folders.has(key))state.folders.delete(key);else state.folders.add(key);renderSide();};host.append(row);if(opened)draw(value,depth+1);}
  }}draw(tree);
 }else if(state.pane==='outline'){
  for(const o of state.outline.filter(o=>(o.title+' '+o.path).toLowerCase().includes(query))){const row=el('button','outline-row',o.title);row.style.paddingLeft=(10+o.depth*12)+'px';row.append(el('small','',o.path+' · línea '+o.line));row.onclick=()=>openFile(o.path,o.line).catch(handleError);host.append(row);}
 }else{
  renderReferenceSide(host,query);
  for(const r of state.refs.filter(r=>(r.key+' '+r.title+' '+r.author).toLowerCase().includes(query))){const row=el('button','ref-row');row.append(el('b','',r.key),el('small','',r.title),el('small','',r.author),el('code','ref-cite','\\cite{'+r.key+'}'));row.title='Insertar \\cite{'+r.key+'}';row.onclick=()=>{if(!currentDoc()||ext(state.current)!=='tex')return toast('Abre primero el archivo .tex donde insertar la cita.');editor.replaceSelection('\\cite{'+r.key+'}');editor.focus();};host.append(row);}
 }
 if(!host.childNodes.length)host.append(el('p','empty-note','No hay coincidencias.'));
}
function stripComments(s){return s.replace(/\\begin\{comment\}[\s\S]*?\\end\{comment\}/g,m=>m.replace(/[^\n]/g,' ')).replace(/(?<!\\)%[^\n]*/g,m=>' '.repeat(m.length));}
function field(entry,name){const rx=new RegExp('\\b'+name+'\\s*=\\s*([{"])','i'),m=rx.exec(entry);if(!m)return '';let start=m.index+m[0].length;if(m[1]==='"')return entry.slice(start,entry.indexOf('"',start));let depth=1,i=start;for(;i<entry.length;i++){if(entry[i]==='{')depth++;else if(entry[i]==='}'&&!--depth)break;}return entry.slice(start,i);}
async function indexSources(){
 if(!state.project)return;const id=++state.loadID,project=state.project;const contents=[];
 for(const f of state.files.filter(f=>['tex','bib'].includes(ext(f.path)))){
  const doc=state.docs.get(f.path);try{contents.push({path:f.path,content:doc?doc.cm.getValue():(await api(`/api/projects/${enc(project)}/files/${fileURL(f.path)}`)).content});}catch{}
 }
 if(id!==state.loadID||project!==state.project)return;
 const refs=[],outline=[],labels=[];
 for(const item of contents){
  const content=stripComments(item.content);
  if(ext(item.path)==='tex'){
   const rx=/\\(chapter|section|subsection|subsubsection)\*?(?:\[[^\]]*\])?\{([^}]+)\}/g;let m;
   while((m=rx.exec(content)))outline.push({title:m[2],path:item.path,line:content.slice(0,m.index).split('\n').length,depth:['chapter','section','subsection','subsubsection'].indexOf(m[1])});
   for(const m of content.matchAll(/\\label\{([^}]+)\}/g))labels.push(m[1]);
  }else{
   const entries=[...content.matchAll(/@\w+\s*\{\s*([^,]+),/g)];for(let i=0;i<entries.length;i++){const entry=content.slice(entries[i].index,entries[i+1]?.index??content.length);refs.push({key:entries[i][1].trim(),title:(field(entry,'title')||field(entry,'note')).replace(/[{}]/g,''),author:field(entry,'author').replace(/[{}]/g,'')});}
  }
 }
 state.refs=refs;state.outline=outline;state.labels=labels;
 const known=new Set(refs.map(r=>r.key));state.missingRefs=[];
 for(const item of contents.filter(i=>ext(i.path)==='tex'))for(const m of stripComments(item.content).matchAll(/\\(?:[Cc]ite\w*|nocite)\*?\s*(?:\[[^\]]*\]\s*)*\{([^}]+)\}/g))for(const key of m[1].split(',').map(k=>k.trim()))if(key&&key!=='*'&&!known.has(key)&&!state.missingRefs.some(r=>r.key===key))state.missingRefs.push({key,path:item.path});
 refreshMissingCitationMarks();refreshUnusedLabelMarks(contents);renderSide();
}
function refreshUnusedLabelMarks(contents=null){
 if(contents)state.labelSources=contents.filter(item=>ext(item.path)==='tex');
 const sources=new Map((state.labelSources||[]).map(item=>[item.path,item]));
 for(const doc of state.docs.values()){
  for(const mark of doc.unusedLabelMarks||[])mark.clear();doc.unusedLabelMarks=[];
  if(ext(doc.path)==='tex')sources.set(doc.path,{path:doc.path,content:doc.cm.getValue()});
 }
 if(!state.cfg.main_file)return;
 const result=UnusedLabels.analyze([...sources.values()],state.cfg.main_file);
 for(const label of result.unused){
  const doc=state.docs.get(label.path);if(!doc)continue;
  doc.unusedLabelMarks.push(doc.cm.markText(doc.cm.posFromIndex(label.from),doc.cm.posFromIndex(label.to),{
   className:'unused-label',title:'Etiqueta sin llamadas: '+label.key+'. No se encontró una referencia en los archivos incluidos (\\ref, \\eqref, \\autoref, \\cref y similares).'
  }));
 }
}
async function openProject(name){
 if(state.busy)return toast('Espera a que termine la compilación.');
 if(state.project)await saveAll();
 const cfg=await api(`/api/projects/${enc(name)}/config`);
 const session=await api(`/api/projects/${enc(name)}/session`,'POST'); // No editing before the opening backup succeeds.
 for(const d of state.docs.values())clearTimeout(d.timer);
 state.project=name;state.root=session.root;state.cfg=cfg;state.labelSources=[];state.docs.clear();state.current=null;state.loadID++;
 $('project-title').textContent=name;$('project-path').textContent=state.root;$('project-path').title=state.root;$('footer-root').textContent=state.root;
 $('backup-label').textContent='Respaldo inicial verificado';$('engine').value=cfg.engine;
 localSet('latex-last-project',name);hidePDF();
 await refreshFiles();connectWS();
 const last=localGet(`latex-last-file:${state.root}`);const target=state.files.find(f=>f.path===last)?.path||cfg.main_file;
 await openFile(target);indexSources().catch(handleError);
 reloadPDF().catch(()=>{});$('projects-dialog').close();renderSaveStatus();
}
async function projectPicker(){
 const projects=await api('/api/projects');const host=$('project-list');host.replaceChildren();
 for(const project of projects){const card=el('button','project-card'+(project.name===state.project?' current':''));card.append(el('b','',project.name),el('small','',project.linked_path||'Proyecto local del editor'));card.disabled=!project.available;card.onclick=()=>openProject(project.name).catch(handleError);host.append(card);}openDialog('projects-dialog');
}
async function compile(){
 if(!state.project||state.busy)return;
 clearTimeout(state.compileTimer);state.busy=true;$('compile-button').disabled=true;$('compile-button').textContent='◌ Compilando…';$('build-state').textContent='Compilando '+state.cfg.main_file;
 try{
  await saveAll();
  const result=await api(`${base()}/compile`,'POST',{engine:state.cfg.engine,mode:'final'});
  $('raw-log').textContent=result.log;$('diagnostic-items').replaceChildren();
  $('compile-result').textContent=result.success?`✓ ${result.main_file} · ${result.duration.toFixed(1)} s`:`No se pudo compilar ${result.main_file}`;
  for(const d of result.diagnostics){const row=el('button','diagnostic '+d.severity,(d.file?`${d.file}:${d.line} — `:'')+d.message);if(d.file)row.onclick=()=>{const f=state.files.find(f=>f.path===d.file||f.path.endsWith('/'+d.file)||f.path.endsWith(d.file.replace(/^\.\//,'')));if(f)openFile(f.path,d.line).catch(handleError);};$('diagnostic-items').append(row);}
  if(result.success){await reloadPDF();$('build-state').textContent='PDF actualizado · '+result.duration.toFixed(1)+' s';toast('PDF actualizado. Bibliografía y referencias resueltas.');}
  else{$('build-state').textContent='Error de compilación · último PDF conservado';$('diagnostics').hidden=false;if(!result.diagnostics.length)$('raw-log').hidden=false;notice('La compilación encontró errores. Tus fuentes y el último PDF correcto están conservados.');}
 }catch(e){handleError(e);$('build-state').textContent='No se completó la compilación';}
 finally{state.busy=false;$('compile-button').disabled=false;$('compile-button').innerHTML='▶ Compilar <kbd>⌘/Ctrl ↵</kbd>';}
}
pdfjsLib.GlobalWorkerOptions.workerSrc='/vendor/pdfjs/pdf.worker.min.js';
let pdfDocument=null,pdfObserver=null,pdfGeneration=0,pdfRevision=null,pdfSyncSerial=0;
function hidePDF(){
 pdfRevision=null;pdfSyncSerial++;pdfGeneration++;if(pdfObserver)pdfObserver.disconnect();if(pdfDocument){pdfDocument.destroy();pdfDocument=null;}
 if(state.pdfURL)URL.revokeObjectURL(state.pdfURL);state.pdfURL=null;
 $('pdf-pages').hidden=true;$('pdf-pages').replaceChildren();$('pdf-controls').hidden=true;$('pdf-empty').hidden=false;$('pdf-download').hidden=true;$('pdf-status').textContent='Sin compilar';
}
async function renderPDF(){
 if(!pdfDocument)return;const generation=++pdfGeneration,doc=pdfDocument,host=$('pdf-pages');
 if(pdfObserver)pdfObserver.disconnect();const oldHeight=host.scrollHeight,ratio=oldHeight?host.scrollTop/oldHeight:0;host.replaceChildren();
 const page1=await doc.getPage(1);if(generation!==pdfGeneration)return;
 const viewport1=page1.getViewport({scale:1});const scale=Math.max(.3,(host.clientWidth-28)/viewport1.width)*Number($('pdf-zoom').value);
 const ratioPixels=Math.min(window.devicePixelRatio||1,2);
 async function renderPage(wrapper){
  if(wrapper.dataset.rendered)return;wrapper.dataset.rendered='yes';
  const page=await doc.getPage(Number(wrapper.dataset.page));if(generation!==pdfGeneration)return;
  const viewport=page.getViewport({scale});
  wrapper.title='Doble clic para abrir esta parte en LaTeX';
  wrapper.ondblclick=event=>navigateFromPDF(event,wrapper,page,viewport).catch(handleError);
  wrapper.style.width=viewport.width+'px';wrapper.style.height=viewport.height+'px';
  const canvas=el('canvas');canvas.width=Math.round(viewport.width*ratioPixels);canvas.height=Math.round(viewport.height*ratioPixels);canvas.style.width=viewport.width+'px';canvas.style.height=viewport.height+'px';canvas.setAttribute('aria-label','Página '+wrapper.dataset.page);wrapper.replaceChildren(canvas);
  await page.render({canvasContext:canvas.getContext('2d'),viewport,transform:ratioPixels===1?null:[ratioPixels,0,0,ratioPixels,0,0]}).promise;
  if(generation!==pdfGeneration)return;
  const layer=el('div','textLayer');layer.style.setProperty('--scale-factor',String(scale));wrapper.append(layer);
  const content=await page.getTextContent();if(generation===pdfGeneration)await pdfjsLib.renderTextLayer({textContentSource:content,container:layer,viewport,textDivs:[]}).promise;
 }
 pdfObserver=new IntersectionObserver(entries=>{for(const entry of entries)if(entry.isIntersecting)renderPage(entry.target).catch(e=>{if(generation===pdfGeneration)notice('No se pudo mostrar una página del PDF: '+e.message);});},{root:host,rootMargin:'700px'});
 for(let i=1;i<=doc.numPages;i++){const page=el('div','pdf-page');page.dataset.page=String(i);page.style.width=viewport1.width*scale+'px';page.style.height=viewport1.height*scale+'px';page.setAttribute('aria-label','Página '+i+' de '+doc.numPages);host.append(page);pdfObserver.observe(page);}
 $('pdf-page-count').textContent=doc.numPages+' páginas';host.scrollTop=ratio*host.scrollHeight;
}
async function reloadPDF(){
 const project=state.project,response=await fetch(`${base()}/pdf?t=${Date.now()}`);if(!response.ok)return;
 const bytes=await response.arrayBuffer();if(project!==state.project)return;
 const revision=await PDFSourceSync.sha256(bytes);if(project!==state.project)return;
 const loaded=await pdfjsLib.getDocument({data:bytes.slice(0),isEvalSupported:false}).promise;
 if(project!==state.project){loaded.destroy();return;}
 if(pdfObserver)pdfObserver.disconnect();if(pdfDocument)await pdfDocument.destroy();pdfDocument=loaded;pdfRevision=revision;
 const old=state.pdfURL;state.pdfURL=URL.createObjectURL(new Blob([bytes],{type:'application/pdf'}));
 $('pdf-pages').hidden=false;$('pdf-controls').hidden=false;$('pdf-empty').hidden=true;
 $('pdf-download').href=state.pdfURL;$('pdf-download').download=state.cfg.main_file.replace(/\.tex$/,'.pdf');$('pdf-download').hidden=false;$('pdf-status').textContent='Último PDF guardado · doble clic para ir al LaTeX';
 await renderPDF();if(old)URL.revokeObjectURL(old);
}
async function navigateFromPDF(event,wrapper,page,viewport){
 event.preventDefault();
 if(!pdfRevision||state.busy)return toast('Espera a que termine de actualizarse el PDF.');
 if(state.navigating)return;
 const point=PDFSourceSync.coordinates(viewport,page.view,wrapper.getBoundingClientRect(),event.clientX,event.clientY,page.userUnit||1);
 const project=state.project,revision=pdfRevision,serial=++pdfSyncSerial;
 $('pdf-status').textContent='Buscando la posición en LaTeX…';
 try{
  const result=await api(base()+'/synctex/inverse','POST',{page:Number(wrapper.dataset.page),...point,pdf_revision:revision});
  if(state.project!==project||pdfRevision!==revision||serial!==pdfSyncSerial)return;
  const existing=state.docs.get(result.path);
  if(existing&&(existing.dirty||existing.blocked||existing.revision!==result.revision))
   throw new Error('Hay cambios en el texto desde la compilación. Guarda y compila para sincronizar el PDF.');
  await openFile(result.path,result.line);
  if(state.current!==result.path)return;
  const destination=editor.getDoc(),line=destination.getLineHandle(result.line-1);
  if(line){destination.addLineClass(line,'background','synctex-source-line');setTimeout(()=>destination.removeLineClass(line,'background','synctex-source-line'),2200);}
  editor.focus();toast('LaTeX: '+result.path+' · línea '+result.line);
  $('pdf-status').textContent='Ubicado en '+result.path+' · línea '+result.line;
 }catch(error){
  if(state.project===project&&serial===pdfSyncSerial){$('pdf-status').textContent='Doble clic para ir al LaTeX';toast(error.message);}
 }
}
$('pdf-zoom').onchange=()=>renderPDF().catch(handleError);
let resizePDFTimer;new ResizeObserver(()=>{clearTimeout(resizePDFTimer);resizePDFTimer=setTimeout(()=>renderPDF().catch(handleError),300);}).observe($('preview-panel'));
let socket=null,wsRetry=null;
function connectWS(){
 clearTimeout(wsRetry);if(socket){socket.onclose=null;socket.close();}
 const project=state.project;socket=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws/${enc(project)}`);
 socket.onopen=()=>{$('connection').className='';$('connection').innerHTML='<i></i> Conectado';};
 socket.onclose=()=>{$('connection').className='offline';$('connection').innerHTML='<i></i> Sin conexión';if(state.project===project)wsRetry=setTimeout(connectWS,3000);};
 socket.onerror=()=>{};
 socket.onmessage=event=>{const msg=JSON.parse(event.data);if(msg.type==='file_changed')checkExternal().catch(()=>{});if(msg.type==='backup_ready')$('backup-label').textContent='Respaldo automático verificado';if(msg.type==='backup_error')notice('No se pudo crear el respaldo automático: '+msg.message);};
}
async function checkExternal(){
 if(pollBusy||!state.project)return;pollBusy=true;
 try{for(const doc of state.docs.values()){
  if(doc.saving||doc.blocked)continue;
  let disk;try{disk=await api(`${base()}/files/${fileURL(doc.path)}`);}catch(error){if(error.status===404){doc.blocked=true;doc.dirty=true;preserveDraft(doc);notice(`${doc.path} fue eliminado fuera del editor. Tu versión está conservada.`,()=>showConflict(doc));renderSaveStatus();}continue;}
  if(doc.saving||disk.revision===doc.revision)continue;
  if(doc.dirty){doc.blocked=true;preserveDraft(doc);notice(`Cambió ${doc.path} en otra aplicación. Revisa las dos versiones.`,()=>showConflict(doc));renderSaveStatus();}
  else{const cursor=doc.cm.getCursor();doc.loading=true;doc.cm.setValue(disk.content);doc.cm.clearHistory();doc.cm.setCursor(cursor);doc.loading=false;doc.revision=disk.revision;toast('Se actualizó '+doc.path+' desde el disco.');}
 }}finally{pollBusy=false;}
}
async function showConflict(doc){
 let disk;try{disk=await api(`${base()}/files/${fileURL(doc.path)}`);}catch(e){if(e.status!==404)throw e;disk={revision:'missing',content:'[El archivo ya no existe en disco]'};}
 $('version-title').textContent='Conflicto · '+doc.path;$('version-explanation').textContent='Ambas versiones están conservadas. Puedes volver a tu borrador, usar la versión del disco o guardar tu texto sobre la revisión mostrada. Si el disco cambia otra vez, se detendrá el guardado.';
 $('compare-current').value=doc.cm.getValue();$('compare-other').value=disk.content;
 showVersionDiff(disk.revision==='missing'?'':disk.content,doc.cm.getValue(),'Disco · consultado el '+dateLabel(Date.now()),'Tu borrador · comparado el '+dateLabel(Date.now()));
 $('diff-note').textContent='Cambios desde el disco hacia tu borrador. Verde (+): añadido. Rojo (−): eliminado. Hora local del navegador.';
 $('restore-version').textContent='Guardar mi versión';$('use-disk').hidden=disk.revision==='missing';
 $('use-disk').onclick=async()=>{try{if(!archiveDraft(doc,'antes de cargar versión del disco'))return;doc.loading=true;doc.cm.setValue(disk.content);doc.cm.clearHistory();doc.loading=false;doc.revision=disk.revision;doc.dirty=false;doc.blocked=false;removeDraftIfSaved(doc);$('version-dialog').close();$('notice').hidden=true;renderSaveStatus();renderTabs();}catch(e){handleError(e);}};
 conflictAction=async()=>{
  archiveDraft(doc,'resolución de conflicto');doc.revision=disk.revision;doc.blocked=false;
  try{await saveDoc(doc);$('version-dialog').close();$('notice').hidden=true;toast('Tu versión quedó guardada con respaldo.');}catch(e){handleError(e);}
 };
 openDialog('version-dialog');
}
async function openHistory(){
 if(!state.project)return;
 $('backup-path').textContent=state.root+'/.latex-local/';$('export-link').href=base()+'/export';
 const recorded=await api(base()+'/history-files');const paths=[...new Set([...state.files.filter(f=>TEXT.has(ext(f.path))).map(f=>f.path),...recorded])].sort();
 $('history-file').replaceChildren();for(const path of paths){const option=el('option','',path);option.value=path;$('history-file').append(option);}
 if(paths.includes(state.current))$('history-file').value=state.current;
 await Promise.all([loadVersions(),loadSnapshots()]);loadDrafts();openDialog('history-dialog');
}
function dateLabel(value){return new Date(value).toLocaleString('es-CL',{dateStyle:'medium',timeStyle:'medium'});}
let activeDiff=null;
function showVersionDiff(before,after,beforeLabel,afterLabel,binary=false){
 activeDiff=binary?null:LatexDiff.compare(before,after);
 $('diff-all').checked=false;
 $('diff-meta').replaceChildren(el('span','',beforeLabel),el('span','',afterLabel));
 $('diff-summary').textContent=binary?'Archivo binario: revisa el respaldo para comparar su contenido.':`${activeDiff.added} líneas añadidas · ${activeDiff.removed} líneas eliminadas`;
 $('diff-note').textContent=binary?'':('Los cambios se muestran desde la versión seleccionada hacia la actual. Verde (+): añadido. Rojo (−): eliminado. Hora local del navegador.'+(activeDiff.coarse?' Comparación por bloques: estos archivos son demasiado diferentes para alinear cada línea.':''));
 $('diff-all').disabled=binary;
 $('version-dialog').querySelector('.full-versions').open=false;
 renderVersionDiff();
}
function renderVersionDiff(){
 const view=$('diff-view');view.replaceChildren();if(!activeDiff)return;
 const {rows,added,removed}=activeDiff;
 if(!added&&!removed){view.append(el('p','diff-empty','Sin cambios: ambas versiones contienen el mismo texto.'));return;}
 const visible=new Set();
 if($('diff-all').checked)rows.forEach((_,i)=>visible.add(i));
 else rows.forEach((row,i)=>{if(row.type!=='same')for(let j=Math.max(0,i-3);j<=Math.min(rows.length-1,i+3);j++)visible.add(j);});
 const fragment=document.createDocumentFragment();let skipped=0;
 const gap=()=>{if(skipped){fragment.append(el('div','diff-gap',`⋯ ${skipped} líneas sin cambios ⋯`));skipped=0;}};
 for(let i=0;i<rows.length;i++){
  if(!visible.has(i)){skipped++;continue;}gap();const row=rows[i],line=el('div','diff-line diff-'+row.type);
  line.append(el('span','diff-number',row.old??''),el('span','diff-number',row.now??''),el('span','diff-sign',row.type==='add'?'+':row.type==='remove'?'−':' '));
  const text=row.text.endsWith('\n')?row.text.slice(0,-1):row.text;
  line.append(el('code','',text||' '));
  if(!row.text.endsWith('\n'))line.append(el('small','diff-eof','Sin salto final'));
  fragment.append(line);
 }
 gap();view.append(fragment);
}
$('diff-all').onchange=renderVersionDiff;
async function loadVersions(){
 const path=$('history-file').value;if(!path)return;
 const list=await api(`${base()}/history?file=${enc(path)}`);$('version-list').replaceChildren();
 for(const entry of list){const button=el('button','history-item',dateLabel(entry.created_at));button.append(el('small','',entry.reason+' · '+(entry.size/1024).toFixed(1)+' KB'));button.onclick=()=>previewVersion(path,entry.id).catch(handleError);$('version-list').append(button);}
 if(!list.length)$('version-list').append(el('p','empty-note','Este archivo no ha cambiado en el editor. Su versión inicial está en el respaldo completo.'));
}
async function loadSnapshots(){
 const list=await api(base()+'/snapshots');$('snapshot-list').replaceChildren();
 for(const item of list){const link=el('a','history-item',dateLabel(item.modified*1000)+' ↗');link.href=`${base()}/snapshot-file/${enc(item.id)}`;link.append(el('small','',(item.size/1048576).toFixed(2)+' MB · Descargar ZIP'));$('snapshot-list').append(link);}
}
async function previewVersion(path,version){
 const result=await api(`${base()}/version?file=${enc(path)}&version=${enc(version)}`);
 const disk=await api(`${base()}/file-state?file=${enc(path)}`);
 $('version-title').textContent='Restaurar · '+path;$('version-explanation').textContent=`Versión del ${dateLabel(result.meta.created_at)}. Al restaurar, se respalda primero la versión actual.`;
 $('compare-current').value=state.docs.get(path)?.cm.getValue()??disk.content;$('compare-other').value=result.content;$('restore-version').textContent='Restaurar esta versión';$('use-disk').hidden=true;
 showVersionDiff(result.content,$('compare-current').value,'Seleccionada · guardada el '+dateLabel(result.meta.created_at),(state.docs.get(path)?.dirty?'Borrador actual':state.docs.has(path)?'Actual en editor':'Actual en disco')+' · comparada el '+dateLabel(Date.now()),result.binary||disk.binary);
 conflictAction=async()=>{try{
  const doc=state.docs.get(path);if(doc)await saveDoc(doc);
  const expected=doc?.revision??disk.revision;
  const saved=await api(base()+'/restore','POST',{file:path,version,revision:expected});
  if(doc){doc.loading=true;doc.cm.setValue(result.content);doc.cm.clearHistory();doc.loading=false;doc.revision=saved.revision;doc.dirty=false;doc.blocked=false;removeDraftIfSaved(doc);}
  await refreshFiles();await loadVersions();$('version-dialog').close();renderSaveStatus();toast('Versión restaurada. La anterior sigue en el historial.');
 }catch(e){handleError(e);}};openDialog('version-dialog');
}
function loadDrafts(){
 $('draft-list').replaceChildren();
 const entries=[];for(let i=0;i<localStorage.length;i++){const key=localStorage.key(i);if(key.startsWith('latex-recovery:')||key.startsWith('latex-draft:')){const draft=localGet(key);if(draft?.root===state.root)entries.push(draft);}}
 for(const draft of entries.sort((a,b)=>b.updated.localeCompare(a.updated))){const row=el('button','history-item',draft.path);row.append(el('small','',dateLabel(draft.updated)+' · '+draft.reason));row.onclick=()=>{const blob=new Blob([draft.content],{type:'text/plain;charset=utf-8'});const url=URL.createObjectURL(blob);const a=el('a');a.href=url;a.download='borrador-'+draft.path.split('/').pop();a.click();setTimeout(()=>URL.revokeObjectURL(url),3000);};$('draft-list').append(row);}
 if(!entries.length)$('draft-list').append(el('p','empty-note','No hay borradores pendientes.'));
}
function openSearch(){if(!currentDoc())return;openDialog('search-dialog');$('search-text').focus();}
function searchNext(){const query=$('search-text').value;if(!query)return;let cursor=editor.getSearchCursor(query,editor.getCursor('to'),{caseFold:true});if(!cursor.findNext()){cursor=editor.getSearchCursor(query,CodeMirror.Pos(0,0),{caseFold:true});if(!cursor.findNext()){$('search-result').textContent='No se encontraron coincidencias.';return;}}editor.setSelection(cursor.from(),cursor.to());editor.scrollIntoView(cursor.from(),100);$('search-result').textContent='Coincidencia en la línea '+(cursor.from().line+1);}
function applyPreferences(){
 const font=localGet('latex-font',15),theme=localGet('latex-theme','light');$('font-size').value=String(font);$('theme').value=theme;$('auto-compile').checked=localGet('latex-auto-compile',false);document.documentElement.style.setProperty('--editor-font',font+'px');editor.getWrapperElement().style.fontSize=font+'px';document.body.classList.toggle('editor-dark',theme==='dark');editor.refresh();
}
$('notice-close').onclick=()=>$('notice').hidden=true;$('notice-action').onclick=()=>Promise.resolve(noticeAction?.()).catch(handleError);
$('save-button').onclick=()=>saveAll().then(()=>toast('Todo guardado en tu carpeta.')).catch(handleError);
$('compile-button').onclick=compile;$('empty-compile').onclick=compile;
$('project-picker').onclick=()=>projectPicker().catch(handleError);$('history-button').onclick=()=>openHistory().catch(handleError);
$('settings-button').onclick=()=>{$('settings-location').textContent='Carpeta real: '+state.root;openDialog('settings-dialog');};
$('help-button').onclick=()=>openDialog('help-dialog');$('find-button').onclick=openSearch;$('focus-button').onclick=()=>{document.body.classList.toggle('focus');$('focus-button').textContent=document.body.classList.contains('focus')?'Volver a paneles':'Concentración';editor.refresh();};
$('file-search').oninput=renderSide;
for(const button of document.querySelectorAll('[data-pane]'))button.onclick=()=>{state.pane=button.dataset.pane;document.querySelectorAll('[data-pane]').forEach(b=>b.classList.toggle('active',b===button));$('file-search').value='';$('file-search').placeholder=state.pane==='refs'?'Buscar citas…':state.pane==='outline'?'Buscar secciones…':'Buscar archivos…';renderSide();};
$('main-file').onchange=async()=>{const main=$('main-file').value;try{await saveAll();await api(base()+'/config','PUT',{main_file:main});state.cfg.main_file=main;hidePDF();await reloadPDF();toast('Documento principal: '+main);}catch(e){$('main-file').value=state.cfg.main_file;handleError(e);}};
$('engine').onchange=async()=>{try{await api(base()+'/config','PUT',{engine:$('engine').value});state.cfg.engine=$('engine').value;}catch(e){handleError(e);}};
$('font-size').onchange=()=>{localSet('latex-font',Number($('font-size').value));applyPreferences();};$('theme').onchange=()=>{localSet('latex-theme',$('theme').value);applyPreferences();};$('auto-compile').onchange=()=>localSet('latex-auto-compile',$('auto-compile').checked);
function insertSnippet(text){if(!currentDoc())return toast('Abre primero un archivo de texto.');$('asset-preview').hidden=true;$('editor-host').hidden=false;editor.replaceSelection(text);editor.focus();}
$('insert-figure').onclick=()=>insertSnippet('\n'+String.raw`\begin{figure}[htbp]
  \centering
  \includegraphics[width=0.85\linewidth]{imagenes/nombre-de-la-figura.pdf}
  \caption{Descripción de la figura.}
  \label{fig:nombre-de-la-figura}
\end{figure}`+'\n');
$('insert-table').onclick=()=>insertSnippet('\n'+String.raw`\begin{table}[htbp]
  \centering
  \caption{Descripción de la tabla.}
  \label{tab:nombre-de-la-tabla}
  \begin{tabular}{lrr}
    \toprule
    Columna & Valor 1 & Valor 2 \\
    \midrule
    Fila & 0 & 0 \\
    \bottomrule
  \end{tabular}
\end{table}`+'\n');
$('upload-button').onclick=()=>$('asset-input').click();
$('asset-input').onchange=async()=>{
 try{await saveAll();for(const file of $('asset-input').files){
  const safeName=file.name.replace(/[^\p{L}\p{N}._-]/gu,'_');const path=(['tex','bib','sty','cls','bst'].includes(ext(safeName))?'':'imagenes/')+safeName;
  const form=new FormData();form.append('file',file);const response=await fetch(`${base()}/assets?path=${enc(path)}`,{method:'POST',body:form});
  if(!response.ok){const error=await response.json();throw new Error('No se incorporó '+file.name+': '+error.detail+' Usa otro nombre si ya existe.');}
 }await refreshFiles();await indexSources();toast('Archivos incorporados a tu carpeta con respaldo.');}catch(e){handleError(e);}finally{$('asset-input').value='';}
};
$('new-file').onclick=async()=>{if(!state.project)return;const path=prompt('Nombre del archivo, por ejemplo: capitulos/metodologia.tex');if(!path)return;try{await api(`${base()}/files/${fileURL(path)}`,'POST');await refreshFiles();await openFile(path);toast('Archivo creado con historial.');}catch(e){handleError(e);}};
$('link-form').onsubmit=async e=>{e.preventDefault();try{await saveAll();const p=await api('/api/projects/from-path','POST',{path:$('link-path').value});await openProject(p.name);}catch(error){handleError(error);}};
$('history-file').onchange=()=>loadVersions().catch(handleError);
$('snapshot-button').onclick=async()=>{const button=$('snapshot-button');button.disabled=true;try{await saveAll();await api(base()+'/snapshots','POST');await loadSnapshots();$('backup-label').textContent='Respaldo manual verificado';toast('Respaldo completo creado y verificado.');}catch(e){handleError(e);}finally{button.disabled=false;}};
$('restore-version').onclick=()=>Promise.resolve(conflictAction?.()).catch(handleError);
$('search-form').onsubmit=e=>{e.preventDefault();searchNext();};$('replace-one').onclick=()=>{if(editor.getSelection().toLocaleLowerCase()===$('search-text').value.toLocaleLowerCase()){editor.replaceSelection($('replace-text').value);searchNext();}else $('search-result').textContent='Primero busca y selecciona una coincidencia.';};
$('toggle-raw').onclick=()=>$('raw-log').hidden=!$('raw-log').hidden;$('close-diagnostics').onclick=()=>$('diagnostics').hidden=true;
for(const button of document.querySelectorAll('[data-close]'))button.onclick=()=>button.closest('dialog').close();
for(const handle of document.querySelectorAll('[data-resize]'))handle.onpointerdown=e=>{e.preventDefault();const start=e.clientX,side=$('sidebar').offsetWidth,preview=$('preview-panel').offsetWidth;handle.setPointerCapture(e.pointerId);handle.onpointermove=e=>{if(handle.dataset.resize==='sidebar')document.documentElement.style.setProperty('--sidebar',Math.max(180,Math.min(400,side+e.clientX-start))+'px');else document.documentElement.style.setProperty('--preview',Math.max(260,Math.min(innerWidth*.65,preview+start-e.clientX))+'px');editor.refresh();};handle.onpointerup=()=>{handle.onpointermove=null;};};
window.addEventListener('beforeunload',e=>{let pending=false;for(const doc of state.docs.values()){if(doc.dirty||doc.saving){preserveDraft(doc);pending=true;}}if(pending){e.preventDefault();e.returnValue='Hay cambios sin guardar en disco.';}});
document.addEventListener('visibilitychange',()=>{if(document.hidden)saveAll().catch(()=>{});else checkExternal().catch(()=>{});});
setInterval(()=>{checkExternal().catch(()=>{});},5000);
async function init(){
 applyPreferences();try{const [workspace,projects]=await Promise.all([api('/api/workspace'),api('/api/projects')]);const last=localGet('latex-last-project');const name=workspace.default_project||last||projects.find(p=>p.available)?.name;if(name)await openProject(name);else await projectPicker();}catch(e){handleError(e);$('save-status').className='error';$('save-status').textContent='No se abrió el proyecto';}
}
init();
