'use strict';
const assert=require('node:assert/strict');
const {compare}=require('../frontend/vendor/local/version-diff.js');
function check(a,b){const result=compare(a,b);assert.equal(result.rows.filter(r=>r.type!=='add').map(r=>r.text).join(''),a);assert.equal(result.rows.filter(r=>r.type!=='remove').map(r=>r.text).join(''),b);let old=1,now=1;for(const row of result.rows){assert.equal(row.old,row.type==='add'?null:old++);assert.equal(row.now,row.type==='remove'?null:now++);}return result;}
for(const [a,b] of [['',''],['','nuevo\n'],['viejo\n',''],['igual\n','igual\n'],['a\nb\nc\n','a\nB\nc\nnuevo\n'],['sin salto','sin salto\n'],['á\r\nβ\r\n','á\nβ\n'],['<script>alert(1)</script>','\\cite{autor}'],['x\nx\ny\n','x\ny\nx\n']])check(a,b);
assert.equal(check('a\nb\nc\n','a\nx\nc\n').added,1);
assert.equal(check('a\nb\nc\n','a\nx\nc\n').removed,1);
let seed=17;const random=()=>((seed=(seed*1664525+1013904223)>>>0)/4294967296);
for(let k=0;k<1000;k++){const a=Array.from({length:Math.floor(random()*25)},()=>['a','β','','x'][Math.floor(random()*4)]+'\n').join('');const b=Array.from({length:Math.floor(random()*25)},()=>['a','β','','x'][Math.floor(random()*4)]+'\n').join('');const r=check(a,b);const x=a.split('\n').slice(0,-1),y=b.split('\n').slice(0,-1),dp=Array.from({length:x.length+1},()=>Array(y.length+1).fill(0));for(let i=x.length-1;i>=0;i--)for(let j=y.length-1;j>=0;j--)dp[i][j]=x[i]===y[j]?1+dp[i+1][j+1]:Math.max(dp[i+1][j],dp[i][j+1]);assert.equal(r.added+r.removed,x.length+y.length-2*dp[0][0]);}
assert.equal(check('a\n'.repeat(2100),'b\n'.repeat(2100)).coarse,true);
console.log('Comparación verificada: 1000 casos aleatorios, Unicode, CRLF, salto final, numeración y límite de memoria.');
