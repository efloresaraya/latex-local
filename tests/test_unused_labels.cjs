'use strict';
const assert=require('node:assert/strict');
const {analyze,mask}=require('../frontend/vendor/local/unused-labels.js');
const file=(path,content)=>({path,content});
const check=(sources,want,main='main.tex')=>{const result=analyze(sources,main);assert.deepEqual(result.unused.map(x=>x.key),want);for(const label of result.unused)assert.equal(sources.find(s=>s.path===label.path).content.slice(label.from,label.to),label.key);return result;};
check([file('main.tex',String.raw`\label{a}\label{b}\ref{a}`)],['b']);
check([file('main.tex',String.raw`\label{a}\input{chapter}`),file('chapter.tex',String.raw`\ref{a}\label{b}`),file('inactive.tex',String.raw`\ref{b}`)],['b']);
for(const command of ['ref','eqref','autoref','Autoref','pageref','nameref','vref','Vref','vpageref','subref','cref','Cref','cpageref','Cpageref','labelcref','labelcpageref','namecref','nameCref','lcnamecref','namecrefs','nameCrefs']){
 check([file('main.tex',String.raw`\label{a}`+'\\'+command+'*{a}')],[]);
}
for(const command of ['crefrange','Crefrange','cpagerefrange','Cpagerefrange','vrefrange','Vrefrange']){
 check([file('main.tex',String.raw`\label{a}\label{b}\label{c}`+'\\'+command+'{a}{b}')],['c']);
}
check([file('main.tex',String.raw`\label{a}\label{b}\cref{a,b}`)],[]);
check([file('main.tex',String.raw`\label{a}\hyperref[a]{texto}`)],[]);
check([file('main.tex',String.raw`\label{a}\ref[texto]{a}`)],[]);
check([file('main.tex',String.raw`\label{a}% \ref{a}`)],['a']);
check([file('main.tex',String.raw`\label{a}\verb|\ref{a}|\begin{verbatim}\ref{a}\end{verbatim}`)],['a']);
check([file('main.tex',String.raw`\begin{comment}\label{x}\end{comment}\label{a}\ref{a}`)],[]);
check([file('main.tex',String.raw`\label{a}\end{document}\ref{a}`)],['a']);
check([file('main.tex',String.raw`\includeonly{used}\include{used}\include{inactive}`),file('used.tex',String.raw`\label{a}`),file('inactive.tex',String.raw`\ref{a}`)],['a']);
check([file('sub/main.tex',String.raw`\input{child}`),file('sub/child.tex',String.raw`\label{a}`)],['a'],'sub/main.tex');
check([file('main.tex',String.raw`\label{a}\input chapter`),file('chapter.tex',String.raw`\ref{a}`)],[]);
assert.equal(check([file('main.tex',String.raw`\label{a}\input{missing}`)],[]).incomplete,true);
assert.equal(check([file('main.tex',String.raw`\label{a}\input{main}`)],[]).incomplete,true);
check([file('main.tex',String.raw`\\label{not-a-label}\label{a}\\ref{a}`)],['a']);
check([file('main.tex',String.raw`\label{a} \\% comentario \ref{a}`)],['a']);
check([file('main.tex',String.raw`\label{a}\% literal \ref{a}`)],[]);
check([file('main.tex','á🙂\r\n'+String.raw`\label{  fig:ñ  }`)],['fig:ñ']);
const text='% comentario\n'+String.raw`\verb|% \label{x}|`+'\n'+String.raw`\label{a}`;
assert.equal(mask(text).length,text.length);assert.equal(mask(text).split('\n').length,text.split('\n').length);
console.log('Etiquetas verificadas: llamadas entre capítulos, 27 variantes de referencias, rangos, comentarios, ejemplos, includeonly, Unicode y borradores.');
