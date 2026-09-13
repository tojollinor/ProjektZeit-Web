const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const document={querySelector:()=>null,querySelectorAll:()=>[],addEventListener:()=>{}};
const context={window:{},document,Date,Map,Set,requestAnimationFrame:()=>{}};
vm.runInNewContext(fs.readFileSync('static/time-workspace.js','utf8'),context);
const base=Date.parse('2026-03-29T00:00:00Z'),at=m=>new Date(base+m*60000).toISOString();
const event=(key,start,end,employee='A',source='starface')=>({key,start:at(start),end:end===null?'':at(end),employee,source});
const rows=context.window.pzTimeLayout([event('1',0,20),event('2',10,30),event('3',20,40),event('4',5,15,'B'),event('ticket',2,null,'A','zammad')],base,base+3600000);
assert.equal(rows.find(x=>x.e.key==='1').lane,0);
assert.equal(rows.find(x=>x.e.key==='2').lane,1);
assert.equal(rows.find(x=>x.e.key==='3').lane,0);
assert.equal(rows.find(x=>x.e.key==='4').lane,0);
const point=rows.find(x=>x.e.key==='ticket');assert.equal(point.a,point.b);
const clipped=context.window.pzTimeLayout([event('span',-10,90)],base,base+3600000)[0];assert.equal(clipped.a,base);assert.equal(clipped.b,base+3600000);
console.log('Time workspace: overlaps, employees, point events and clipping passed');
// A live timer changes text every second. Global decorators must not rerun for it.
let native,timer;
class Observer{constructor(fn){this.fn=fn;native=this;}observe(){}disconnect(){}takeRecords(){return [];}}
const body={};const win={MutationObserver:Observer,fetch:()=>{},addEventListener:()=>{}};
const perfContext={window:win,document:{...document,body},performance:{now:()=>0},setTimeout:fn=>{timer=fn;return 1},clearTimeout:()=>{},Date,URL,location:{href:'https://example.test/'}};
vm.runInNewContext(fs.readFileSync('static/performance-guard.js','utf8'),perfContext);
let callbacks=0;const observer=new win.MutationObserver(()=>callbacks++);observer.observe(body,{childList:true,subtree:true});
const target={closest:()=>null};for(let i=0;i<1000;i++)native.fn([{addedNodes:[{nodeType:3}],removedNodes:[{nodeType:3}],target}]);
assert.equal(timer,undefined);assert.equal(callbacks,0);
native.fn([{addedNodes:[{nodeType:1}],removedNodes:[],target}]);timer();assert.equal(callbacks,1);
console.log('Global decorators ignore 1,000 timer text mutations and process new elements');
