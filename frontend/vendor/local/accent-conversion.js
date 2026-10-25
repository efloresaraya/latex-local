/* Conversión voluntaria del documento abierto, con revisión y guardado protegido. */
'use strict';
let accentConversionContext=null;
$('convert-accents').onclick=()=>{
 const doc=currentDoc();
 if(!doc||ext(doc.path)!=='tex')return toast('Abre el archivo .tex cuyos acentos quieres convertir.');
 if(doc.blocked)return showConflict(doc);
 const plan=LatexAccents.plan(doc.cm.getValue());
 accentConversionContext={project:state.project,doc,path:doc.path,plan};
 $('accent-conversion-summary').textContent=doc.path+' · '+plan.edits.length+' acentos para convertir.';
 $('accent-conversion-before').value=plan.before;$('accent-conversion-after').value=plan.after;
 $('accent-conversion-apply').disabled=!plan.edits.length;
 $('accent-conversion-status').textContent=plan.edits.length?'La conversión se aplicará solo a este archivo. Puedes deshacerla con ⌘Z o Ctrl+Z.':'No hay acentos pendientes de conversión en el texto editable.';
 openDialog('accent-conversion-dialog');
};
$('accent-conversion-apply').onclick=async()=>{
 const context=accentConversionContext,button=$('accent-conversion-apply');
 if(!context)return;button.disabled=true;
 try{
  const {doc,plan,path,project}=context;
  if(state.project!==project||state.docs.get(path)!==doc||doc.cm.getValue()!==plan.before)
   throw new Error('El archivo cambió desde la vista previa. Cierra esta ventana y vuelve a pulsar Convertir acentos.');
  // Preserve the exact pre-conversion draft on disk first; SafeStore keeps
  // both that version and the following conversion. Never retry a CAS conflict.
  await saveDoc(doc);
  if(state.project!==project||state.current!==path||editor.getDoc()!==doc.cm||doc.blocked||doc.cm.getValue()!==plan.before)throw new Error('El archivo cambió. Revisa de nuevo la vista previa antes de convertir.');
  doc.cm.changeGeneration(true);
  editor.operation(()=>{
   for(const edit of plan.edits.slice().reverse())doc.cm.replaceRange(edit.text,doc.cm.posFromIndex(edit.from),doc.cm.posFromIndex(edit.to),'accent-conversion');
  });
  doc.cm.changeGeneration(true);
  await saveDoc(doc);
  $('accent-conversion-dialog').close();
  toast(plan.edits.length+' acentos convertidos y guardados con respaldo en '+path+'.');editor.focus();
 }catch(error){$('accent-conversion-status').textContent=error.message;handleError(error);}
};
