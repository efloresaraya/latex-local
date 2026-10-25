'use strict';
const assert=require('node:assert/strict');
const {coordinates}=require('../frontend/vendor/local/pdf-source-sync.js');
for(const scale of [.3,.8,1,1.5,2.5]){
 const viewport={width:600*scale,height:800*scale,convertToPdfPoint:(x,y)=>[x/scale,800-y/scale]};
 for(const cssScale of [.75,1,1.25]){
  const rect={left:30,top:50,width:viewport.width*cssScale,height:viewport.height*cssScale};
  const result=coordinates(viewport,[0,0,600,800],rect,30+123*scale*cssScale,50+456*scale*cssScale);
  assert.ok(Math.abs(result.x-123)<1e-8);assert.ok(Math.abs(result.y-456)<1e-8);
 }
}
const rotated={width:800,height:600,convertToPdfPoint:(x,y)=>[y,x]};
assert.deepEqual(coordinates(rotated,[0,0,600,800],{left:0,top:0,width:800,height:600},344,123),{x:123,y:456});
console.log('Coordenadas SyncTeX verificadas: zoom, escala CSS, rotación y origen superior izquierdo.');
