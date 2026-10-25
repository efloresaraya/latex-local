/* Une únicamente citas simples completas; conserva notas, comentarios y ejemplos. */
(function(root){
 'use strict';
 function citation(text,start){
  if(!text.startsWith('\\cite{',start))return null;
  let i=start+6,keys=[],part='';
  function flush(){const key=part.trim();part='';if(key){if(!/^[^\s{},\\%]+$/.test(key)||key==='*')return false;keys.push(key);}return true;}
  const stack=[];
  while(i<text.length){
   if(text.startsWith('\\cite{',i)){
    if(!flush())return null;stack.push(true);i+=6;continue;
   }
   const c=text[i++];
   if(c==='}'){
    if(!flush())return null;
    if(stack.length){stack.pop();continue;}
    return keys.length?{start,end:i,keys}:null;
   }
   if(c===','){if(!flush())return null;}
   else if(c==='{'||c==='\\'||c==='%')return null;
   else part+=c;
  }
  return null;
 }
 function edits(text,from=0,to=text.length){
  const result=[];let i=0,group=null;
  function finish(){
   if(!group)return;
   const replacement='\\cite{'+[...new Set(group.keys)].join(',')+'}';
   if(group.start<=to&&group.end>=from&&text.slice(group.start,group.end)!==replacement)
    result.push({from:group.start,to:group.end,text:replacement});
   group=null;
  }
  while(i<text.length){
   if(text[i]==='%'){finish();const end=text.indexOf('\n',i);i=end<0?text.length:end+1;continue;}
   if(text[i]==='\\'){
    const literal=/^\\begin\{(verbatim\*?|Verbatim|lstlisting|minted|comment)\}/.exec(text.slice(i));
    if(literal){finish();const end=text.indexOf('\\end{'+literal[1]+'}',i+literal[0].length);i=end<0?text.length:end+literal[1].length+6;continue;}
    const verb=/^\\verb\*?([^A-Za-z\s])/.exec(text.slice(i));
    if(verb){finish();const end=text.indexOf(verb[1],i+verb[0].length);i=end<0?text.length:end+1;continue;}
    const item=citation(text,i);
    if(item){
     if(group&&/^[ \t]*(?:\r?\n[ \t]*)?$/.test(text.slice(group.end,item.start))){group.end=item.end;group.keys.push(...item.keys);}
     else{finish();group=item;}
     i=item.end;continue;
    }
    finish();
    // Skip a whole control sequence (including escaped percent/backslash).
    const command=/^\\(?:[A-Za-z]+\*?|[^\r\n])/.exec(text.slice(i));
    if(command){
     i+=command[0].length;
     // Preserve arguments of other cite variants, including their nested text.
     if(/^\\(?:[Cc]ite\w*|[A-Za-z]*cite\w*)\*?$/.test(command[0])){
      while(/\s/.test(text[i]||'')&&i<text.length)i++;
      while(text[i]==='['){const end=text.indexOf(']',i+1);if(end<0){i=text.length;break;}i=end+1;while(i<text.length&&/\s/.test(text[i]))i++;}
      if(text[i]==='{'){let depth=1;i++;while(i<text.length&&depth){if(text[i]==='\\'){i+=2;continue;}if(text[i]==='{')depth++;if(text[i]==='}')depth--;i++;}}
     }
     continue;
    }
   }
   i++;
  }
  finish();return result;
 }
 function apply(cm,changes){
  const user=changes.filter(c=>!['setValue','undo','redo','citation-merge','accent-conversion'].includes(c.origin)&&c.text.join('\n').length);
  if(!user.length)return;
  const text=cm.getValue();let from=text.length,to=0;
  for(const c of user){const start=cm.indexFromPos(c.from);from=Math.min(from,start);to=Math.max(to,start+c.text.join('\n').length);}
  const changesToMake=edits(text,from,to);
  if(!changesToMake.length)return;
  cm.operation(()=>{for(const edit of changesToMake.reverse())cm.replaceRange(edit.text,cm.posFromIndex(edit.from),cm.posFromIndex(edit.to),'citation-merge');});
 }
 const api={edits,apply};if(typeof module==='object'&&module.exports)module.exports=api;else root.CitationMerge=api;
})(typeof globalThis!=='undefined'?globalThis:this);
