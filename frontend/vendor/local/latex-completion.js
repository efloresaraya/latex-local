/* LaTeX Local contributors — MIT. */
(function(root,factory){
 if(typeof module==='object'&&module.exports)module.exports=factory();
 else root.LatexCompletion=factory();
})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 const commands=[
  'textit{}','textbf{}','texttt{}','textnormal{}','textrm{}','textsf{}','textsc{}','text{}','emph{}','underline{}',
  'frac{}{}','dfrac{}{}','tfrac{}{}','sqrt{}','overline{}','underbrace{}','overbrace{}',
  'mathrm{}','mathbf{}','mathit{}','mathbb{}','mathcal{}','mathsf{}','boldsymbol{}','operatorname{}',
  'sum','prod','int','iint','iiint','lim','infty','partial','nabla','cdot','times','pm','mp','leq','geq','neq','approx','equiv','in','notin','subset','subseteq','cup','cap','forall','exists',
  'sin','cos','tan','log','ln','exp','min','max','left','right',
  'alpha','beta','gamma','delta','epsilon','varepsilon','zeta','eta','theta','vartheta','iota','kappa','lambda','mu','nu','xi','pi','rho','sigma','tau','upsilon','phi','varphi','chi','psi','omega',
  'Gamma','Delta','Theta','Lambda','Xi','Pi','Sigma','Upsilon','Phi','Psi','Omega',
  'section{}','subsection{}','subsubsection{}','chapter{}','paragraph{}','caption{}','footnote{}',
  'cite{}','citep{}','citet{}','ref{}','eqref{}','autoref{}','label{}','begin{}','end{}',
  'includegraphics[width=\\linewidth]{}','input{}','include{}','item','centering','noindent','smallskip','medskip','bigskip'
 ].map(x=>'\\'+x);
 function context(cm){
  if(cm.somethingSelected())return null;
  const cursor=cm.getCursor(),line=cm.getLine(cursor.line);
  const token=cm.getTokenAt?cm.getTokenAt(cursor):null;
  if(token&&/comment|verbatim/.test(token.type||''))return null;
  const before=line.slice(0,cursor.ch),m=before.match(/\\([A-Za-z]*)$/);
  if(!m)return null;
  const start=cursor.ch-m[0].length;
  let slashes=0;for(let i=start-1;i>=0&&line[i]==='\\';i--)slashes++;
  if(slashes%2)return null;
  // Consume the remaining command name when completing in its middle.
  const tail=(line.slice(cursor.ch).match(/^[A-Za-z]*/)||[''])[0];
  return {prefix:m[0],from:{line:cursor.line,ch:start},to:{line:cursor.line,ch:cursor.ch+tail.length}};
 }
 function insert(cm,data,item){
  const next=cm.getLine(data.to.line).slice(data.to.ch);
  let text=item.text,offset=text.indexOf('{}');
  // Reuse an existing argument rather than generating a second pair of braces.
  if(next.startsWith('{')&&offset>=0){text=text.slice(0,text.indexOf('{'));offset=text.length;}
  cm.operation(()=>{
   cm.replaceRange(text,data.from,data.to,'complete');
   cm.setCursor({line:data.from.line,ch:data.from.ch+(offset>=0?offset+1:text.length)});
  });
  cm.focus();
 }
 function hints(cm){
  const c=context(cm);if(!c)return {list:[],from:cm.getCursor(),to:cm.getCursor()};
  return {from:c.from,to:c.to,list:commands.filter(x=>x.startsWith(c.prefix)).map(text=>({text,displayText:text,hint:insert}))};
 }
 function shouldOpen(cm,change){
  if(!change||change.origin!=='+input'||cm.getOption('readOnly'))return false;
  const c=context(cm);return !!c&&c.prefix.length>=3&&commands.some(x=>x.startsWith(c.prefix));
 }
 return {hints,shouldOpen};
});
