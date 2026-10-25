/* Coordinates are PDF points, independent of zoom and Retina pixel density. */
(function(root){
 'use strict';
 function coordinates(viewport,view,rect,clientX,clientY,unit=1){
  const [x,y]=viewport.convertToPdfPoint((clientX-rect.left)*viewport.width/rect.width,(clientY-rect.top)*viewport.height/rect.height);
  return {x:Math.max(0,(x-view[0])*unit),y:Math.max(0,(view[3]-y)*unit)};
 }
 async function sha256(bytes){
  const result=await crypto.subtle.digest('SHA-256',bytes);
  return Array.from(new Uint8Array(result),b=>b.toString(16).padStart(2,'0')).join('');
 }
 const api={coordinates,sha256};if(typeof module==='object'&&module.exports)module.exports=api;else root.PDFSourceSync=api;
})(typeof globalThis!=='undefined'?globalThis:this);
