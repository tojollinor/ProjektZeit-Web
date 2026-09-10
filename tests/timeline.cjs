const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

// Reject HTML style attributes, just as the production CSP does. Capture the
// supported property assignments separately to detect this rendering regression.
class Element {
  constructor() { this.style = {}; this.children = []; this.value = ''; this.clientWidth=724; this.scrollLeft=0; }
  getBoundingClientRect() { return {width:parseFloat(this.style.width)||720,left:0}; }
  append(child) { this.children.push(child); }
  setAttribute(name,value) { this[name]=value; }
  addEventListener(name,handler) { this[name]=handler; }
  replaceChildren(child) { this.children = child.fragment ? child.children : [child]; }
  set innerHTML(value) {
    assert(!/style\s*=/i.test(value), 'Blocked inline style attribute');
    this.firstElementChild = new Element();
  }
}
const nodes = Object.fromEntries(['#timeline-date', '#timeline-track', '#timeline-summary','.timeline-scroll','.timeline-layout','.timeline-hours','#zoom-reset'].map(id => [id, new Element()]));
nodes['#timeline-date'].value = '2026-09-08';
const source = fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8');
const context = {
  state:{},
  $: id => nodes[id],
  document: {
    createElement: () => new Element(),
    createDocumentFragment: () => Object.assign(new Element(), { fragment: true }),
  },
  dateValue: () => '2026-09-08',
  duration: (start, end) => String(end - start),
};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('function renderTimeline('), source.indexOf('function fillSelect(')), context);
const entry = (start, end, project) => ({started_at: `2026-09-08T${start}:00`, ended_at: `2026-09-08T${end}:00`, project, category: 'Test'});
context.renderTimeline([entry('08:00', '10:00', 'A'), entry('08:30', '09:00', 'B'), entry('10:00', '10:01', '<Text>')]);
const track = nodes['#timeline-track'];
const cards = track.children.filter(child => child.className === 'timeline-segment');
assert.equal(cards.length, 3);
assert.deepEqual(cards.map(card => card.style.top), ['8px', '8px', '8px']);
assert(cards.every(card => parseFloat(card.style.left) > 0 && card.style.backgroundColor));
assert(cards[2]['aria-label'].includes('<Text>'));
assert.equal(typeof cards[2].click,'function');
assert.equal(cards[2].style.width, `${1/1440*100}%`);
assert.equal(cards[0].style.width, `${120/1440*100}%`);
assert.equal(track.style.height, '66px');
context.zoomTimeline(2,200);
assert.equal(nodes['.timeline-layout'].style.width,'1440px');
assert.equal(nodes['.timeline-scroll'].scrollLeft,200);
context.zoomTimeline(.5,200);
assert.equal(nodes['.timeline-scroll'].scrollLeft,0);
assert.equal(nodes['.timeline-layout'].style.width,'720px');
context.zoomTimeline(1000,0);
assert.equal(context.state.timelineZoom,96);
context.zoomTimeline(.00001,0);
assert.equal(context.state.timelineZoom,1);
context.renderTimeline([]);
assert.equal(track.children[0].className, 'timeline-empty');
assert.equal(track.style.height, '66px');
console.log('Timeline checks passed: single row, exact durations, zoom anchor and bounds, safe text, empty day.');
