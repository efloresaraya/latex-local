'use strict';
const assert=require('node:assert/strict');
const {edits,apply}=require('../frontend/vendor/local/citation-merge.js');
function merge(text,from=0,to=text.length){for(const e of edits(text,from,to).reverse())text=text.slice(0,e.from)+e.text+text.slice(e.to);return text;}
const cases=[
 ['\\cite{a} \\cite{b}','\\cite{a,b}'],
 ['\\cite{a,\\cite{b}}','\\cite{a,b}'],
 ['\\cite{a,\\cite{b,\\cite{a,c}}} \\cite{d}','\\cite{a,b,c,d}'],
 ['Texto \\cite{a}\\cite{b}\n  \\cite{c,a}. Fin.','Texto \\cite{a,b,c}. Fin.'],
 ['\\cite{a,b,a}','\\cite{a,b}'],
 ['\\cite{a}\n\n\\cite{b}','\\cite{a}\n\n\\cite{b}'],
 ['\\cite{a}, \\cite{b}','\\cite{a}, \\cite{b}'],
 ['\\cite{a} y \\cite{b}','\\cite{a} y \\cite{b}'],
 ['% \\cite{a}\\cite{b}\n\\cite{c}\\cite{d}','% \\cite{a}\\cite{b}\n\\cite{c,d}'],
 ['\\cite{a}% comentario\n\\cite{b}','\\cite{a}% comentario\n\\cite{b}'],
 ['\\verb|\\cite{a}\\cite{b}|','\\verb|\\cite{a}\\cite{b}|'],
 ['\\begin{verbatim}\n\\cite{a}\\cite{b}\n\\end{verbatim}','\\begin{verbatim}\n\\cite{a}\\cite{b}\n\\end{verbatim}'],
 ['\\cite[p.~2]{a} \\cite{b}','\\cite[p.~2]{a} \\cite{b}'],
 ['\\cite{a} \\cite[nota]{b}','\\cite{a} \\cite[nota]{b}'],
 ['\\cite[nota]{a,\\cite{b}}','\\cite[nota]{a,\\cite{b}}'],
 ['\\citep{a}\\citep{b}','\\citep{a}\\citep{b}'],
 ['\\cite{a,\\cite{b}','\\cite{a,\\cite{b}'],
 ['\\\\cite{a}\\cite{b}','\\\\cite{a}\\cite{b}'],
 ['\\cite{Autor:2026-ñ}\\cite{b_2}','\\cite{Autor:2026-ñ,b_2}'],
 ['\\cite{*}\\cite{a}','\\cite{*}\\cite{a}'],
];
for(const [input,want] of cases){assert.equal(merge(input),want,input);assert.equal(merge(want),want,'Idempotencia: '+input);}
const many=Array.from({length:1500},(_,i)=>'\\cite{k'+i+'}').join(' ');
assert.equal(merge(many),'\\cite{'+Array.from({length:1500},(_,i)=>'k'+i).join(',')+'}');
const nested='\\cite{a,'.repeat(1000)+'\\cite{b}'+'}'.repeat(1000);
assert.equal(merge(nested),'\\cite{a,b}');
const local='\\cite{old}\\cite{old2}\nTexto \\cite{a}\\cite{b}';
assert.equal(merge(local,local.length-8,local.length),'\\cite{old}\\cite{old2}\nTexto \\cite{a,b}');
// Exercise integration without writing a project: undo/load must stay untouched.
let value='\\cite{a}\\cite{b}',replacements=0;
const cm={getValue:()=>value,indexFromPos:p=>p.ch,posFromIndex:n=>({line:0,ch:n}),operation:fn=>fn(),replaceRange:(s,a,b,origin)=>{assert.equal(origin,'citation-merge');replacements++;value=value.slice(0,a.ch)+s+value.slice(b.ch);}};
for(const origin of ['undo','redo','setValue','citation-merge','accent-conversion'])apply(cm,[{origin,from:{line:0,ch:0},text:[value]}]);
assert.equal(replacements,0);
apply(cm,[{origin:'paste',from:{line:0,ch:0},text:[value]}]);assert.equal(value,'\\cite{a,b}');assert.equal(replacements,1);
console.log('OK: unión de N citas, anidamiento, orden, duplicados, edición localizada y protecciones.');
