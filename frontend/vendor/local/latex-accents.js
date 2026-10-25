/* Convierte solamente el texto nuevo; conserva claves, rutas y código literal. */
(function(root){
 'use strict';
 function escaped(text,i){let count=0;while(i>0&&text[--i]==='\\')count++;return count%2===1;}
 function endGroup(text,start,open='{',close='}'){
  let depth=1,i=start+1;
  while(i<text.length){if(text[i]==='\\'){i+=2;continue;}if(text[i]===open)depth++;if(text[i]===close&&!--depth)return i+1;i++;}
  return text.length;
 }
 function protectedMask(text){
  const mask=new Uint8Array(text.length);let i=0;
  const protect=end=>{mask.fill(1,i,end);i=end;};
  while(i<text.length){
   if(text[i]==='%'&&!escaped(text,i)){const end=text.indexOf('\n',i);protect(end<0?text.length:end);continue;}
   if(text[i]==='$'&&!escaped(text,i)){
    const delimiter=text.startsWith('$$',i)?'$$':'$';let end=i+delimiter.length;
    while(end<text.length&&(!text.startsWith(delimiter,end)||escaped(text,end)))end++;
    protect(Math.min(text.length,end+delimiter.length));continue;
   }
   if(text[i]==='\\'&&!escaped(text,i)){
    const env=/^\\begin\{(verbatim\*?|Verbatim|lstlisting|minted|comment|filecontents\*?|equation\*?|align\*?|alignat\*?|gather\*?|multline\*?|displaymath|math)\}/.exec(text.slice(i));
    if(env){const close='\\end{'+env[1]+'}',end=text.indexOf(close,i+env[0].length);protect(end<0?text.length:end+close.length);continue;}
    const literal=/^\\(?:verb\*?|path)([^A-Za-z\s{])/.exec(text.slice(i));
    if(literal){const end=text.indexOf(literal[1],i+literal[0].length);protect(end<0?text.length:end+1);continue;}
    if(text.startsWith('\\(',i)||text.startsWith('\\[',i)){
     const close=text[i+1]==='('? '\\)':'\\]';let end=text.indexOf(close,i+2);
     while(end>=0&&escaped(text,end))end=text.indexOf(close,end+2);
     protect(end<0?text.length:end+2);continue;
    }
    const command=/^\\([A-Za-z]+)\*?/.exec(text.slice(i));
    if(command){
     const name=command[1],keyCommand=/^(?:[Cc]ite\w*|[A-Za-z]*cite\w*|label|ref|eqref|autoref|Autoref|pageref|nameref|vref|Vref|vpageref|subref|[cC](?:page)?ref\w*|labelcref|labelcpageref|namecref|nameCref|lcnamecref|namecrefs|nameCrefs|[vV]refrange)$/.test(name);
     const pathCommand=/^(?:input|include|includeonly|includegraphics|bibliography|bibliographystyle|addbibresource|url|path|href|nolinkurl|documentclass|usepackage)$/.test(name);
     if(keyCommand||pathCommand||name==='hyperref'){
      const start=i;let end=i+command[0].length;
      while(end<text.length&&/\s/.test(text[end]))end++;
      while(text[end]==='['){end=endGroup(text,end,'[',']');while(end<text.length&&/\s/.test(text[end]))end++;}
      const argumentStart=end,groups=/range$/.test(name)?2:name==='hyperref'?0:1;
      for(let g=0;g<groups&&text[end]==='{';g++){end=endGroup(text,end);if(g+1<groups)while(end<text.length&&/\s/.test(text[end]))end++;}
      if(name==='input'&&text[argumentStart]!=='{'){while(end<text.length&&!/[\s{}]/.test(text[end]))end++;}
      protect(end);continue;
     }
     i+=command[0].length;continue;
    }
   }
   i++;
  }
  return mask;
 }
 const accents={'\u0301':"\\'",'\u0300':'\\`','\u0302':'\\^','\u0303':'\\~','\u0308':'\\"','\u0327':'\\c'};
 function encode(value){
  const chars=Array.from(value.normalize('NFD'));
  if(chars.length!==2||!/[A-Za-z]/.test(chars[0])||!accents[chars[1]])return value;
  const accent=accents[chars[1]];return accent==='\\c'?accent+'{'+chars[0]+'}':accent+chars[0];
 }
 function transform(source,from,to,inserted){
  // Some keyboards deliver a combining accent after the base letter.
  if(/^[\u0300-\u036f]/.test(inserted)&&from===to&&from>0&&/[A-Za-z]/.test(source[from-1])){
   from--;inserted=source[from]+inserted;
  }
  const proposed=source.slice(0,from)+inserted+source.slice(to),mask=protectedMask(proposed);
  const text=inserted.replace(/[A-Za-z][\u0300-\u036f]+|[\u00c0-\u024f\u1e00-\u1eff]/g,(value,offset)=>mask[from+offset]?value:encode(value));
  return {from,to,text,changed:text!==inserted};
 }
 function plan(source,from=0,to=source.length){
  const mask=protectedMask(source),edits=[];
  for(const match of source.matchAll(/[A-Za-z][\u0300-\u036f]+|[\u00c0-\u024f\u1e00-\u1eff]/g)){
   const start=match.index,end=start+match[0].length;
   if(start<from||end>to||mask[start])continue;
   const text=encode(match[0]);if(text!==match[0])edits.push({from:start,to:end,text});
  }
  let after=source;for(const edit of edits.slice().reverse())after=after.slice(0,edit.from)+edit.text+after.slice(edit.to);
  return {before:source,after,edits};
 }
 function beforeChange(cm,change){
  if(['setValue','undo','redo','citation-merge'].includes(change.origin)||!change.update)return;
  const inserted=change.text.join('\n');if(!/[\u00c0-\u024f\u0300-\u036f\u1e00-\u1eff]/.test(inserted))return;
  const result=transform(cm.getValue(),cm.indexFromPos(change.from),cm.indexFromPos(change.to),inserted);
  if(result.changed)change.update(cm.posFromIndex(result.from),cm.posFromIndex(result.to),result.text.split('\n'));
 }
 const api={encode,transform,plan,beforeChange};if(typeof module==='object'&&module.exports)module.exports=api;else root.LatexAccents=api;
})(typeof globalThis!=='undefined'?globalThis:this);
