const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../browser-extension/popup.js'), 'utf8');

async function popup(url) {
  const nodes = new Map();
  const messages = [];
  const timers = new Map();
  const listeners = {};
  const port = {
    onMessage: {addListener: callback => {listeners.message = callback;}},
    onDisconnect: {addListener: callback => {listeners.disconnect = callback;}},
    postMessage: message => messages.push(JSON.parse(JSON.stringify(message))),
  };
  const document = {getElementById: id => {
    if (!nodes.has(id)) nodes.set(id, {hidden: id === 'retry', textContent: '',
      removeAttribute(name) {delete this[name];}, addEventListener(name, callback) {this[name] = callback;}});
    return nodes.get(id);
  }};
  vm.runInNewContext(source, {document, URL, chrome: {
    tabs: {query: async () => [{url}]}, runtime: {connectNative: () => port},
  }, setInterval: callback => {timers.set(1, callback); return 1;}, clearInterval: id => timers.delete(id)});
  await new Promise(setImmediate);
  return {nodes, messages, timers, listeners};
}

test('a toolbar popup starts only one job and polling never starts another', async () => {
  const p = await popup('https://www.youtube.com/watch?v=abcdefghijk');
  assert.deepEqual(p.messages, [{action: 'start', url: 'https://www.youtube.com/watch?v=abcdefghijk', retry: false}]);
  p.listeners.message({ok: true, job: {id: 'abcdefghijk', state: 'queued'}});
  p.timers.get(1)();
  p.timers.get(1)();
  assert.equal(p.messages.filter(m => m.action === 'start').length, 1);
  assert.equal(p.messages.filter(m => m.action === 'status').length, 2);
  p.listeners.message({ok: true, job: {id: 'abcdefghijk', state: 'completed', progress: 1}});
  assert.equal(p.nodes.get('progress').value, 100);
  assert.equal(p.timers.size, 0);
});

test('unrelated websites never contact the local app', async () => {
  const p = await popup('https://example.com');
  assert.equal(p.messages.length, 0);
  assert.match(p.nodes.get('status').textContent, /يوتيوب/);
});

test('failed jobs require an explicit retry button click', async () => {
  const p = await popup('https://youtu.be/abcdefghijk');
  p.listeners.message({ok: true, job: {id: 'abcdefghijk', state: 'failed', message: 'راجع Buzz'}});
  assert.equal(p.timers.size, 0);
  assert.equal(p.nodes.get('retry').hidden, false);
  assert.equal(p.messages.length, 1);
  p.nodes.get('retry').click();
  await new Promise(setImmediate);
  assert.equal(p.messages[1].retry, true);
});
