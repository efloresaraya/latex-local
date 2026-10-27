'use strict';
const assert=require('node:assert/strict');
const completion=require('../frontend/vendor/local/latex-completion.js');
function editor(text,cursor=text.length,type=null){return {
 text,cursor, focused:false, somethingSelected:()=>false,getCursor(){return {line:0,ch:this.cursor};},
 getLine(){return this.text;},getTokenAt:()=>({type}),getOption:()=>false,
 operation(fn){fn();},replaceRange(value,from,to){this.text=this.text.slice(0,from.ch)+value+this.text.slice(to.ch);},
 setCursor(p){this.cursor=p.ch;},focus(){this.focused=true;}
};}
function pick(cm,text){const data=completion.hints(cm);const item=data.list.find(x=>x.text===text);assert.ok(item,text);item.hint(cm,data,item);}
let cm=editor('Un texto \\texti');pick(cm,'\\textit{}');assert.equal(cm.text,'Un texto \\textit{}');assert.equal(cm.text[cm.cursor],'}');
cm=editor('\\fra');pick(cm,'\\frac{}{}');assert.equal(cm.text,'\\frac{}{}');assert.equal(cm.cursor,6);assert.ok(cm.focused);
cm=editor('\\textit{contenido}',6);pick(cm,'\\textit{}');assert.equal(cm.text,'\\textit{contenido}');assert.equal(cm.cursor,8);
cm=editor('\\alpha');pick(cm,'\\alpha');assert.equal(cm.cursor,6);
assert.equal(completion.hints(editor('\\\\texti')).list.length,0);
assert.equal(completion.hints(editor('% \\texti',9,'comment')).list.length,0);
assert.equal(completion.hints(editor('texto normal')).list.length,0);
assert.equal(completion.shouldOpen(editor('\\te'),{origin:'+input'}),true);
assert.equal(completion.shouldOpen(editor('\\t'),{origin:'+input'}),false);
assert.equal(completion.shouldOpen(editor('\\texti'),{origin:'paste'}),false);
assert.equal(completion.hints(editor('\\desconocido')).list.length,0);
console.log('Autocompletado verificado: comandos, primera llave, argumentos existentes, selección parcial y contexto.');
