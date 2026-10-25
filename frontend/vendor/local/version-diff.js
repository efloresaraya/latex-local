/* Comparación local de líneas, sin acceso a documentos ni escrituras. */
(function(root){
'use strict';
function compare(before,after){
 const lines=s=>s===''?[]:s.match(/[^\n]*\n|[^\n]+$/g);
 const a=lines(before),b=lines(after),rows=[];let start=0,end=0;
 while(start<a.length&&start<b.length&&a[start]===b[start])start++;
 while(end<a.length-start&&end<b.length-start&&a[a.length-1-end]===b[b.length-1-end])end++;
 let old=1,now=1;
 const push=(type,text)=>rows.push({type,text,old:type==='add'?null:old++,now:type==='remove'?null:now++});
 for(let i=0;i<start;i++)push('same',a[i]);
 const n=a.length-start-end,m=b.length-start-end;
 // Limita memoria y trabajo cuando dos archivos grandes son completamente diferentes.
 const coarse=n*m>4000000;
 if(coarse){for(let i=0;i<n;i++)push('remove',a[start+i]);for(let j=0;j<m;j++)push('add',b[start+j]);}
 else{
  const width=m+1,table=new Uint32Array((n+1)*width);
  for(let i=n-1;i>=0;i--)for(let j=m-1;j>=0;j--)table[i*width+j]=a[start+i]===b[start+j]?1+table[(i+1)*width+j+1]:Math.max(table[(i+1)*width+j],table[i*width+j+1]);
  let i=0,j=0;
  while(i<n||j<m){
   if(i<n&&j<m&&a[start+i]===b[start+j]){push('same',a[start+i]);i++;j++;}
   else if(i<n&&(j===m||table[(i+1)*width+j]>=table[i*width+j+1]))push('remove',a[start+i++]);
   else push('add',b[start+j++]);
  }
 }
 for(let i=a.length-end;i<a.length;i++)push('same',a[i]);
 return {rows,coarse,added:rows.filter(r=>r.type==='add').length,removed:rows.filter(r=>r.type==='remove').length};
}
const api={compare};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.LatexDiff=api;
})(typeof window!=='undefined'?window:globalThis);
