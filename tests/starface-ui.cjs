const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const read = file => fs.readFileSync(path.join(__dirname, '..', file), 'utf8');
const html = read('static/index.html');
const scripts = [...html.matchAll(/<script\b[^>]*src="([^"?]+)[^"]*"[^>]*>/g)].map(m => m[1]);
assert(scripts.indexOf('/starface-connect.js') >= 0, 'STARFACE must load directly from the page');
assert(scripts.indexOf('/starface-connect.js') < scripts.indexOf('/app.js'), 'Renderer must be available before app startup');
let click, poll, connected = false;
const element = () => ({value:'', classList:{add(){},remove(){}}, replaceChildren(...children){this.children=children;}});
const fields = Object.fromEntries(['domain','client_id','client_secret'].map(k=>[k,element()]));
fields.domain.value='https://pbx.example.com';fields.client_id.value='rest-client';fields.client_secret.value='private-secret';
const status=element(),launch=element(),badge=element(),output=element();
const card={isConnected:true,querySelector(s){return s.startsWith('[data-field=')?fields[s.match(/"([^"]+)"/)[1]]:({'.integration-status':status,'.desktop-launch':launch,'.badge':badge,'.debug-output':output})[s];},querySelectorAll(){return Object.values(fields)}};
const container={addEventListener(name,fn){click=fn;}};
const posts=[];
const uri='projektzeit://starface/connect?server=https%3A%2F%2Ftime.example.com&request='+'a'.repeat(40);
const context={console,Event:class Event{},document:{querySelector:()=>container,createElement:element},window:{location:{},dispatchEvent(){}},
  attr:v=>String(v??'').replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;'),esc:String,
  normalizeStarfaceAddress:v=>v,clearInterval(){},setInterval(fn){poll=fn;return 1;},
  api:async()=>({integrations:[{provider:'starface',has_secret:connected}]}),
  post:async(url,body)=>{posts.push({url,body});return body.configure_only?{domain:body.domain,client_id:body.client_id}:{uri};}};
vm.createContext(context);
vm.runInContext(read('static/starface-connect.js'),context);
const markup=context.window.renderStarfaceCard({domain:'https://pbx.example.com',username:'',has_secret:false});
for(const field of ['domain','client_id','client_secret'])assert(markup.includes(`data-field="${field}"`));
assert(markup.includes('type="password"'));
assert(markup.includes('value="rest-client"'));
assert(!context.window.renderStarfaceCard({username:'"><script>',domain:'',has_secret:false}).includes('<script>'));
(async()=>{
  const button={dataset:{starfaceAction:'connect'},closest:()=>card};
  await click({target:{closest:()=>button},preventDefault(){},stopImmediatePropagation(){}});
  assert.equal(posts.length,2);
  assert.equal(posts[0].body.client_secret,'private-secret');
  assert.equal(posts[1].body.desktop_prepare,true);
  assert.equal(fields.client_secret.value,'');
  assert.equal(context.window.location.href,uri);
  assert.equal(launch.children[0].href,uri,'Manual launch remains available if the browser blocks automatic opening');
  assert(!uri.includes('private-secret'));
  connected=true;await poll();assert.equal(badge.textContent,'Verbunden');
  assert(fields.client_id.disabled===false);
  console.log('STARFACE UI checks passed: script loading, credentials, desktop handoff and connection feedback.');
})().catch(error=>{console.error(error);process.exitCode=1;});
