const fs=require('fs'),vm=require('vm'),assert=require('assert');
const elements=new Map();
function el(id){if(!elements.has(id))elements.set(id,{value:'0',dataset:{},disabled:false,clientWidth:900,scrollLeft:0,attrs:{},setAttribute(k,v){this.attrs[k]=v;},getAttribute(k){return this.attrs[k];},replaceChildren(){},append(){},addEventListener(){},focus(){},setPointerCapture(){}});return elements.get(id);}
el('scoreZoom').value='80';el('scoreSnap').value='.1';
let contexts=[],frame=null;
class AudioMock{
 constructor(){this.currentTime=0;this.nodes=[];this.closed=false;contexts.push(this);}
 async resume(){}
 async close(){this.closed=true;}
 createGain(){return {gain:{value:0,setValueAtTime(){},linearRampToValueAtTime(){}},connect(){},disconnect(){}};}
 createOscillator(){const node={frequency:{value:0},connect(){},disconnect(){},start(t){this.startTime=t;},stop(t){this.endTime=t;}};this.nodes.push(node);return node;}
}
const context=vm.createContext({console,AudioContext:AudioMock,$:el,Option:function(){},
 document:{createElementNS:()=>el('svg-'+Math.random()),addEventListener(){},hidden:false},
 window:{addEventListener(){}},keyOrder:'ASDFGHJQWERTYUI',scaleSteps:[0,2,4,5,7,9,11,12,14,16,17,19,21,23,24],noteName:String,
 state:{},options:()=>({root:60,countdown:5,mode:'piano'}),stopPreview(){},toast(m){throw Error(m);},confirm:()=>true,
 requestAnimationFrame(fn){frame=fn;return 1;},cancelAnimationFrame(){frame=null;},call:async()=>({cancelled:true})});
vm.runInContext(fs.readFileSync('outputs/KeyScore/editor.js','utf8'),context);
const run=s=>vm.runInContext(s,context);
(async()=>{
 run("replaceScore({version:1,title:'test',settings:{root:60,countdown:5,mode:'piano'},notes:[{s:0,e:4,k:'A',p:60,v:.8},{s:1,e:1.5,k:'D',p:64,v:.8},{s:3,e:4,k:'G',p:67,v:.8}]}); seekScore(2)");
 assert.equal(run('previewSegments(editor.score.notes,2).length'),2);
 assert.equal(run('previewSegments(editor.score.notes,2)[0].s'),0);
 await run('scorePlayback.enabled=true; startScorePlayback()');let ctx=contexts.at(-1);
 assert.equal(ctx.nodes.length,1);assert.equal(ctx.nodes[0].frequency.value,440*2**((60-69)/12));
 assert.equal(ctx.nodes[0].endTime,2.05); // Remaining sustain only.
 ctx.currentTime=.8;frame();assert(Math.abs(run('scorePlayback.position')-2.75)<1e-8);
 assert.equal(ctx.nodes.length,2); // Upcoming note scheduled within horizon.
 run('seekScore(1)');assert(ctx.closed);assert.equal(run('scorePlayback.position'),1);assert.equal(frame,null);
 await run('scorePlayback.enabled=true; startScorePlayback()');ctx=contexts.at(-1);run('remember()');assert(ctx.closed); // Editing stops all sound.
 run('seekScore(4)');await run('scorePlayback.enabled=true; startScorePlayback()');assert.equal(run('scorePlayback.ctx'),null);
 run('seekScore(0)');await run('scorePlayback.enabled=true; startScorePlayback()');ctx=contexts.at(-1);ctx.currentTime=5;frame();assert(ctx.closed);assert.equal(run('scorePlayback.position'),4);
 // Stop during asynchronous resume must not resurrect playback.
 run('seekScore(0)');const pending=run('scorePlayback.enabled=true; startScorePlayback()');run('stopScorePlayback()');await pending;assert.equal(run('scorePlayback.ctx'),null);assert.equal(frame,null);
 run('stopScorePlayback(); seekScore(2)');const count=contexts.length;
 await run('scrubAtCursor()');assert.equal(contexts.length,count); // OFF is silent.
 run('scorePlayback.enabled=true');await run('scrubAtCursor()');const scrubCtx=contexts.at(-1);
 assert.equal(scrubCtx.nodes.length,1);assert.equal(scrubCtx.nodes[0].endTime,.11);
 await run('scrubAtCursor()');assert.equal(scrubCtx.nodes.length,1); // Throttled.
 scrubCtx.currentTime=.1;run('scorePlayback.position=1.2');await run('scrubAtCursor()');assert.equal(scrubCtx.nodes.length,3); // Two simultaneous notes.
 run('finishSeek()');await Promise.resolve();assert(scrubCtx.closed);assert(run('scorePlayback.enabled'));assert(run('scorePlayback.ctx')!==null);
 await el('scorePlay').onclick();assert.equal(run('scorePlayback.enabled'),false);assert.equal(run('scorePlayback.ctx'),null);assert.equal(run('scrub.ctx'),null);
 run("replaceScore({version:1,title:'batch',settings:{root:60,countdown:5,mode:'piano'},notes:[{s:1,e:2,k:'A',p:60,v:.8},{s:2,e:4,k:'D',p:64,v:.8},{s:5,e:6,k:'I',p:84,v:.8}]}); editor.boxMode=true;editor.box={a:{x:140,y:380},b:{x:390,y:474}};updateBoxSelection();editor.box=null;drawScore()");
 assert.equal(run('editor.selection.size'),2);assert(el('addNote').disabled);assert(el('applyNote').disabled);assert(el('noteLength').disabled);assert(!el('deleteNote').disabled);
 el('batchTime').value='-5';el('batchPitch').value='-5';el('moveBatch').onclick();
 assert.equal(run('editor.score.notes[0].s'),0);assert.equal(run('editor.score.notes[1].s'),1);assert.equal(run('editor.score.notes[1].e-editor.score.notes[1].s'),2);assert.equal(run('editor.score.notes[0].k'),'A');
 el('deleteNote').onclick();assert.equal(run('editor.score.notes.length'),1);assert.equal(run('editor.score.notes[0].k'),'I');
 el('undoScore').onclick();assert.equal(run('editor.score.notes.length'),3);assert.equal(run('editor.boxMode'),false);
 assert(!el('addNote').disabled);el('redoScore').onclick();assert.equal(run('editor.score.notes.length'),1);
 run('editor.boxMode=true;editor.selection=new Set([0]);drawScore()');const saved=run('JSON.stringify(editor.score)');run('editNote(true)');assert.equal(run('JSON.stringify(editor.score)'),saved);
 el('clearSelection').onclick();assert.equal(run('editor.selection.size'),0);assert(!el('noteLength').disabled);
 // Real pointer handler sequence: box select, group drag, cancel restores data.
 el('undoScore').onclick(); // Restore the two deleted notes.
 el('scoreGrid').getBoundingClientRect=()=>({left:0,top:0});
 run("globalThis.ev=(x,y,id=null)=>({clientX:x,clientY:y,button:0,pointerId:1,preventDefault(){},target:{hasAttribute(a){return a==='data-note'&&id!==null;},getAttribute(){return String(id);}}}); $('scoreGrid').onpointerdown(ev(65,380));$('scoreGrid').onpointermove(ev(310,474));$('scoreGrid').onpointerup()");
 assert.equal(run('editor.selection.size'),2);const beforeDrag=run('JSON.stringify(editor.score)');
 run("$('scoreGrid').onpointerdown(ev(80,455,0));$('scoreGrid').onpointermove(ev(160,425,0))");
 assert.equal(run('editor.score.notes[0].s'),1);assert.equal(run('editor.score.notes[0].k'),'S');
 run("$('scoreGrid').onpointercancel()");assert.equal(run('JSON.stringify(editor.score)'),beforeDrag);
 console.log('PASS: playback, scrub, box intersections, group boundary/length preservation, batch deletion/undo/redo and control locking.');
})().catch(e=>{console.error(e);process.exitCode=1;});
