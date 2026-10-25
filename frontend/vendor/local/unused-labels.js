/* Análisis local de etiquetas: no modifica ni guarda el documento. */
(function(root){
 'use strict';
 function escaped(text,index){let n=0;while(index>0&&text[--index]==='\\')n++;return n%2===1;}
 function mask(text){
  const chars=text.split('');let i=0;
  const blank=(start,end)=>{for(let j=start;j<end;j++)if(chars[j]!=='\n'&&chars[j]!=='\r')chars[j]=' ';};
  while(i<text.length){
   if(text[i]==='%'&&!escaped(text,i)){let end=text.indexOf('\n',i);if(end<0)end=text.length;blank(i,end);i=end;continue;}
   if(text[i]==='\\'&&!escaped(text,i)){
    const env=/^\\begin\{(verbatim\*?|Verbatim|lstlisting|minted|comment)\}/.exec(text.slice(i));
    if(env){const closing='\\end{'+env[1]+'}',found=text.indexOf(closing,i+env[0].length),end=found<0?text.length:found+closing.length;blank(i,end);i=end;continue;}
    const verb=/^\\verb\*?([^A-Za-z\s])/.exec(text.slice(i));
    if(verb){const found=text.indexOf(verb[1],i+verb[0].length),end=found<0?text.length:found+1;blank(i,end);i=end;continue;}
   }
   i++;
  }
  return chars.join('');
 }
 function normalize(path){const parts=[];for(const part of path.split('/')){if(!part||part==='.')continue;if(part==='..'){if(!parts.length)return null;parts.pop();}else parts.push(part);}return parts.join('/');}
 function analyze(sources,main){
  const files=new Map(sources.map(s=>[s.path,mask(s.content)])),labels=[],used=new Set(),active=new Set();let incomplete=false,stopped=false;
  const root=main.includes('/')?main.slice(0,main.lastIndexOf('/')+1):'';
  const first=files.get(main);if(first===undefined)return {unused:[],active:[],incomplete:true};
  const only=/\\includeonly\s*\{([^}]*)\}/.exec(first);
  const included=only?new Set(only[1].split(',').map(s=>s.trim().replace(/\.tex$/,''))):null;
  const refs='(?:ref|eqref|autoref|Autoref|pageref|nameref|vref|Vref|vpageref|subref|cref|Cref|cpageref|Cpageref|labelcref|labelcpageref|namecref|nameCref|lcnamecref|namecrefs|nameCrefs)';
  const ranges='(?:crefrange|Crefrange|cpagerefrange|Cpagerefrange|vrefrange|Vrefrange)';
  const token=new RegExp('\\\\(?:label|'+refs+'|'+ranges+'|input|include)(?![A-Za-z])\\*?\\s*(?:\\[[^\\]]*\\]\\s*)*\\{([^{}]*)\\}(?:\\s*\\{([^{}]*)\\})?|\\\\hyperref\\s*\\[([^\\]]+)\\]|\\\\input(?![A-Za-z])\\s+([^\\s{}%]+)|\\\\end\\s*\\{document\\}','g');
  function visit(path,stack){
   if(stack.includes(path)||stack.length>100){incomplete=true;return;}
   const text=files.get(path);if(text===undefined){incomplete=true;return;}
   active.add(path);
   // Each recursive visit needs its own regex cursor.
   for(const match of text.matchAll(new RegExp(token.source,'g'))){
    if(stopped)break;if(escaped(text,match.index))continue;
    const command=/^\\([A-Za-z]+)/.exec(match[0])[1];
    if(command==='end'){stopped=true;break;}
    if(command==='input'||command==='include'){
     const value=(match[1]??match[4]??'').trim();
     if(command==='include'&&included&&!included.has(value.replace(/\.tex$/,'')))continue;
     if(!value||/[\\#]/.test(value)){incomplete=true;continue;}
     const child=normalize(root+value+(/\.[^/]+$/.test(value)?'':'.tex'));
     if(!child){incomplete=true;continue;}visit(child,[...stack,path]);
    }else if(command==='label'){
     const raw=match[1],key=raw.trim(),offset=match[0].indexOf('{')+1+raw.indexOf(key);
     if(key&&!/[\\#]/.test(key))labels.push({path,key,from:match.index+offset,to:match.index+offset+key.length});
    }else{
     const values=command==='hyperref'?[match[3]]:[match[1],...(new RegExp('^'+ranges+'$').test(command)?[match[2]]:[])];
     for(const value of values)for(const key of (value||'').split(',').map(v=>v.trim()))if(key)used.add(key);
    }
   }
  }
  visit(main,[]);
  return {unused:incomplete?[]:labels.filter(label=>!used.has(label.key)),active:[...active],incomplete};
 }
 const api={analyze,mask};if(typeof module==='object'&&module.exports)module.exports=api;else root.UnusedLabels=api;
})(typeof globalThis!=='undefined'?globalThis:this);
