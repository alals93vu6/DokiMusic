'use strict';
const referenceAudio={buffer:null,name:'',volume:.5,muted:false,offset:0,gain:null,loading:0};
const editor={score:null,selected:-1,undo:[],redo:[],dirty:false,drag:null};
editor.tracks=[];editor.active=-1;editor.clipboard=[];editor.compare=false;
editor.selection=new Set();editor.boxMode=false;editor.box=null;
function clearScoreSelection(){editor.selected=-1;editor.selection.clear();editor.boxMode=false;editor.box=null;}
const scorePlayback={position:0,ctx:null,raf:0,generation:0,origin:0,start:0,end:0,seeking:false};
scorePlayback.enabled=false;
const scrub={ctx:null,last:-1,nodes:[]};
const cloneScore=x=>JSON.parse(JSON.stringify(x));
function editorPage(open){stopScorePlayback();stopPreview();$('analysisPage').hidden=open;$('editorPage').hidden=!open;if(open)drawScore();}
$('editorTab').onclick=()=>editorPage(true);
$('analysisTab').onclick=()=>editorPage(false);
function remember(){stopScorePlayback();editor.undo.push(JSON.stringify(editor.score));if(editor.undo.length>50)editor.undo.shift();editor.redo=[];editor.dirty=true;}
function replaceScore(score){
  if(editor.dirty&&!confirm('目前的修改尚未匯出。要改載入另一份樂譜嗎？'))return;
  stopScorePlayback();scorePlayback.position=0;
  editor.score=cloneScore(score);clearScoreSelection();editor.undo=[];editor.redo=[];editor.dirty=false;
  if(editor.active<0){editor.active=0;editor.tracks.push({});}
  Object.assign(editor.tracks[editor.active],{score:editor.score,comparison:null,muted:false});editor.compare=false;
  $('scoreTitle').value=score.title;$('scoreCountdown').value=score.settings.countdown;drawScore();
}
$('newScore').onclick=()=>replaceScore({version:1,title:'未命名樂譜',settings:options(),notes:[]});
$('useAnalysis').onclick=()=>{if(!state.result||state.dirty||state.busy){toast('請先完成解析並套用設定。',true);return;}replaceScore({version:1,title:state.result.title,settings:state.result.settings,notes:state.result.notes});};
$('importScore').onclick=async()=>{try{const r=await call('import_score');if(!r.cancelled)replaceScore(r.score);}catch(e){toast(e.message,true);}};
$('saveScore').onclick=async()=>{
  if(!editor.score){toast('請先建立或載入樂譜。',true);return;}
  const target=editor.tracks[editor.active],snapshot=JSON.stringify(editor.score);$('saveScore').disabled=true;
  try{const r=await call('export_score',cloneScore(editor.score));if(!r.cancelled){if(JSON.stringify(target.score)===snapshot){target.dirty=false;if(editor.tracks[editor.active]===target)editor.dirty=false;}toast('已儲存：'+r.path);drawScore();}}catch(e){toast(e.message,true);}finally{$('saveScore').disabled=false;}
};
for(const [id,field] of [['scoreTitle','title'],['scoreCountdown','countdown']])$(id).onchange=()=>{if(!editor.score)return;remember();if(field==='title')editor.score.title=$(id).value;else editor.score.settings.countdown=Number($(id).value);drawScore();};
function historyScore(from,to){if(!from.length)return;stopScorePlayback();to.push(JSON.stringify(editor.score));editor.score=JSON.parse(from.pop());clearScoreSelection();editor.dirty=true;$('scoreTitle').value=editor.score.title;$('scoreCountdown').value=editor.score.settings.countdown;drawScore();}
$('undoScore').onclick=()=>historyScore(editor.undo,editor.redo);
$('redoScore').onclick=()=>historyScore(editor.redo,editor.undo);
const svgNS='http://www.w3.org/2000/svg';
function svgElement(name,attrs,text){const el=document.createElementNS(svgNS,name);for(const [k,v] of Object.entries(attrs))el.setAttribute(k,v);if(text!==undefined)el.textContent=text;return el;}
function drawScore(){
  syncTrack();renderTracks();
  const svg=$('scoreGrid');svg.replaceChildren();const score=editor.score,zoom=Number($('scoreZoom').value);
  $('undoScore').disabled=!editor.undo.length;$('redoScore').disabled=!editor.redo.length;
  const batch=editor.boxMode;
  for(const id of ['noteKey','noteStart','noteLength','addNote'])$(id).disabled=batch;
  $('applyNote').disabled=batch||editor.selected<0;
  $('deleteNote').disabled=batch?!editor.selection.size:editor.selected<0;
  $('deleteNote').textContent=batch?`刪除框選 ${editor.selection.size} 音`:'刪除選取音符';
  $('batchTools').hidden=!batch;$('moveBatch').disabled=!editor.selection.size;
  $('scoreStatus').textContent=score?`${score.notes.length} 個音符${editor.dirty?' · 尚未匯出':''}`:'尚未載入樂譜。';
  if(batch)$('scoreStatus').textContent+=` · 框選 ${editor.selection.size} 音（可複製／移動／刪除）`;
  const duration=Math.max(15,scoreEnd()+2),width=Math.max(900,64+duration*zoom);
  svg.setAttribute('width',width);svg.setAttribute('viewBox',`0 0 ${width} 474`);
  const root=score?.settings.root||60;
  $('noteKey').replaceChildren(...[...keyOrder].map((k,i)=>new Option(`${k} · ${noteName(root+scaleSteps[i])}`,k)));
  for(let i=0;i<15;i++){const y=24+(14-i)*30;svg.append(svgElement('rect',{x:0,y,width,height:30,fill:i%2?'#18221f':'#111a17'}));svg.append(svgElement('text',{x:5,y:y+20,fill:'#a5bead','font-size':11},keyOrder[i]+' '+noteName(root+scaleSteps[i])));}
  const tick=zoom>=80?1:2;
  for(let t=0;t<=duration;t+=tick){const x=64+t*zoom;svg.append(svgElement('line',{x1:x,x2:x,y1:24,y2:474,stroke:'#304139'}));svg.append(svgElement('text',{x:x+2,y:16,fill:'#a5bead','font-size':11},t+'s'));}
  const comparison=editor.tracks[editor.active]?.comparison;
  if(comparison)comparison.notes.forEach(n=>{const row=keyOrder.indexOf(n.k);svg.append(svgElement('rect',{x:64+n.s*zoom,y:24+(14-row)*30+1,width:Math.max(4,(n.e-n.s)*zoom),height:28,fill:'#c6a5ff',opacity:.28,'pointer-events':'none'}));});
  if(score)score.notes.forEach((n,i)=>{const x=64+n.s*zoom,y=24+(14-keyOrder.indexOf(n.k))*30+3,w=Math.max(4,(n.e-n.s)*zoom);svg.append(svgElement('rect',{x,y,width:w,height:24,rx:3,fill:(batch?editor.selection.has(i):i===editor.selected)?'#e1f4a8':'#79cfc2','data-note':i}));if(!batch)svg.append(svgElement('rect',{x:x+Math.max(0,w-6),y,width:Math.min(w,6),height:24,fill:'#466859','data-note':i,'data-resize':'1'}));});
  if(editor.box){const b=editor.box;svg.append(svgElement('rect',{x:Math.min(b.a.x,b.b.x),y:Math.min(b.a.y,b.b.y),width:Math.abs(b.a.x-b.b.x),height:Math.abs(b.a.y-b.b.y),fill:'#a6dca522',stroke:'#d8f5a0','stroke-dasharray':'4 3','pointer-events':'none'}));}
  const n=score?.notes[editor.selected];if(n){$('noteKey').value=n.k;$('noteStart').value=n.s;$('noteLength').value=+(n.e-n.s).toFixed(3);}
  svg.append(svgElement('line',{id:'scorePlayhead',x1:64,x2:64,y1:24,y2:474,stroke:'#ff827a','stroke-width':2,'pointer-events':'none'}));
  svg.append(svgElement('path',{id:'scoreHandle',d:'M -7 0 L 7 0 L 7 14 L 0 23 L -7 14 Z',fill:'#ff827a','data-seek':'1',cursor:'ew-resize'}));
  updateScoreCursor();
}
function noteInput(){const s=Number($('noteStart').value),length=Number($('noteLength').value),k=$('noteKey').value;if(!Number.isFinite(s)||!Number.isFinite(length)||s<0||length<.05||s+length>2400)throw Error('請輸入有效時間：長度至少 0.05 秒，結束不超過 2400 秒。');return {s:+s.toFixed(3),e:+(s+length).toFixed(3),k,p:editor.score.settings.root+scaleSteps[keyOrder.indexOf(k)],v:.8};}
function editNote(add){if(editor.boxMode)return;try{if(!editor.score)throw Error('請先建立或載入樂譜。');const n=noteInput();remember();if(add){editor.score.notes.push(n);editor.selected=editor.score.notes.length-1;}else editor.score.notes[editor.selected]={...editor.score.notes[editor.selected],...n};drawScore();}catch(e){toast(e.message,true);}}
$('addNote').onclick=()=>editNote(true);$('applyNote').onclick=()=>editNote(false);
$('deleteNote').onclick=()=>{const ids=editor.boxMode?editor.selection:new Set(editor.selected<0?[]:[editor.selected]);if(!ids.size)return;remember();editor.score.notes=editor.score.notes.filter((n,i)=>!ids.has(i));clearScoreSelection();drawScore();};
$('clearSelection').onclick=()=>{clearScoreSelection();drawScore();};
function moveScoreGroup(originals,seconds,steps){
  const notes=originals.map(x=>x.note);if(!notes.length)return;
  const dt=Math.max(-Math.min(...notes.map(n=>n.s)),Math.min(seconds,2400-Math.max(...notes.map(n=>n.e))));
  const rows=notes.map(n=>keyOrder.indexOf(n.k)),dr=Math.max(-Math.min(...rows),Math.min(steps,14-Math.max(...rows)));
  for(const {id,note} of originals){const row=keyOrder.indexOf(note.k)+dr;editor.score.notes[id]={...note,s:+(note.s+dt).toFixed(3),e:+(note.e+dt).toFixed(3),k:keyOrder[row],p:editor.score.settings.root+scaleSteps[row]};}
}
$('moveBatch').onclick=()=>{const dt=Number($('batchTime').value),dr=Number($('batchPitch').value);if(!editor.selection.size)return;if(!Number.isFinite(dt)||!Number.isInteger(dr)){toast('請輸入有效秒數及整數鍵位。',true);return;}remember();moveScoreGroup([...editor.selection].map(id=>({id,note:{...editor.score.notes[id]}})),dt,dr);drawScore();};
function updateBoxSelection(){const b=editor.box,zoom=Number($('scoreZoom').value);editor.selection.clear();if(!b)return;const x1=Math.min(b.a.x,b.b.x),x2=Math.max(b.a.x,b.b.x),y1=Math.min(b.a.y,b.b.y),y2=Math.max(b.a.y,b.b.y);editor.score.notes.forEach((n,i)=>{const x=64+n.s*zoom,y=24+(14-keyOrder.indexOf(n.k))*30+3;if(x<x2&&x+Math.max(4,(n.e-n.s)*zoom)>x1&&y<y2&&y+24>y1)editor.selection.add(i);});}
$('scoreZoom').onchange=drawScore;
function gridPoint(e){const r=$('scoreGrid').getBoundingClientRect();return {x:e.clientX-r.left,y:e.clientY-r.top};}
function snapTime(t){const step=Number($('scoreSnap').value);return +(Math.round(t/step)*step).toFixed(3);}
$('scoreGrid').ondblclick=e=>{if(!editor.score||e.target.hasAttribute('data-note'))return;const p=gridPoint(e),row=14-Math.floor((p.y-24)/30);if(p.x<64||row<0||row>14)return;$('noteKey').value=keyOrder[row];$('noteStart').value=Math.max(0,snapTime((p.x-64)/Number($('scoreZoom').value)));$('noteLength').value=.5;editNote(true);};
$('scoreGrid').onpointerdown=e=>{
  const point=gridPoint(e);if(e.target.hasAttribute('data-seek')||(point.y<24&&point.x>=64)){e.preventDefault();stopScorePlayback(true);scorePlayback.seeking=true;$('scoreGrid').setPointerCapture(e.pointerId);seekScore((point.x-64)/Number($('scoreZoom').value));return;}
  if(!editor.score||e.button>0)return;stopScorePlayback();e.preventDefault();$('scoreGrid').focus({preventScroll:true});$('scoreGrid').setPointerCapture(e.pointerId);
  if(!e.target.hasAttribute('data-note')){if(point.x<64||point.y<24)return;editor.box={a:point,b:point};editor.drag={box:true,previous:[...editor.selection],previousMode:editor.boxMode,previousSingle:editor.selected};return;}
  const id=Number(e.target.getAttribute('data-note'));if(!editor.boxMode||!editor.selection.has(id)){clearScoreSelection();editor.selected=id;}
  const n=editor.score.notes[id];editor.drag={point,note:{...n},resize:!editor.boxMode&&e.target.hasAttribute('data-resize'),snapshot:JSON.stringify(editor.score),group:editor.boxMode?[...editor.selection].map(id=>({id,note:{...editor.score.notes[id]}})):null};drawScore();
};
$('scoreGrid').onpointermove=e=>{const d=editor.drag;if(!d)return;const p=gridPoint(e);if(d.box){editor.box.b=p;if(Math.hypot(p.x-editor.box.a.x,p.y-editor.box.a.y)>4){d.moved=true;editor.boxMode=true;editor.selected=-1;updateBoxSelection();drawScore();}return;}const delta=snapTime((p.x-d.point.x)/Number($('scoreZoom').value));if(d.group){moveScoreGroup(d.group,delta,-Math.round((p.y-d.point.y)/30));drawScore();return;}const n=editor.score.notes[editor.selected];if(d.resize)n.e=Math.min(2400,Math.max(n.s+.05,+(d.note.e+delta).toFixed(3)));else{const length=d.note.e-d.note.s;n.s=Math.max(0,Math.min(2400-length,+(d.note.s+delta).toFixed(3)));n.e=+(n.s+length).toFixed(3);const row=Math.max(0,Math.min(14,keyOrder.indexOf(d.note.k)-Math.round((p.y-d.point.y)/30)));n.k=keyOrder[row];n.p=editor.score.settings.root+scaleSteps[row];}drawScore();};
$('scoreGrid').onpointerup=()=>{const wasSeeking=scorePlayback.seeking;scorePlayback.seeking=false;if(wasSeeking)finishSeek();const d=editor.drag;if(!d)return;if(d.box){editor.box=null;if(!d.moved)clearScoreSelection();editor.drag=null;drawScore();return;}if(d.snapshot!==JSON.stringify(editor.score)){editor.undo.push(d.snapshot);if(editor.undo.length>50)editor.undo.shift();editor.redo=[];editor.dirty=true;}editor.drag=null;drawScore();};
$('scoreGrid').onpointercancel=()=>{if(scorePlayback.seeking)stopScorePlayback();scorePlayback.seeking=false;const d=editor.drag;if(d){if(d.box){editor.selection=new Set(d.previous);editor.boxMode=d.previousMode;editor.selected=d.previousSingle;editor.box=null;}else editor.score=JSON.parse(d.snapshot);editor.drag=null;drawScore();}};
$('scoreGrid').onkeydown=e=>{if(e.key==='Delete'){e.preventDefault();$('deleteNote').click();}};
function scoreEnd(){syncTrack();return editor.tracks.reduce((end,t)=>Math.max(end,...t.score.notes.map(n=>n.e),...(t.comparison?.notes||[]).map(n=>n.e)),referenceAudio.buffer?Math.max(0,referenceAudio.buffer.duration-referenceAudio.offset):0);}
function updateScoreCursor(){
  const end=scoreEnd(),limit=Math.max(15,end+2);scorePlayback.position=Math.max(0,Math.min(limit,scorePlayback.position));
  const x=64+scorePlayback.position*Number($('scoreZoom').value);
  if($('scorePlayhead')){for(const a of ['x1','x2'])$('scorePlayhead').setAttribute(a,x);$('scoreHandle').setAttribute('transform',`translate(${x} 0)`);}
  $('scoreSeek').max=limit;$('scoreSeek').value=scorePlayback.position;$('scorePosition').value=scorePlayback.position.toFixed(2);
  $('scoreTime').textContent=`${scorePlayback.position.toFixed(2)} / ${end.toFixed(2)} 秒`;
  $('scorePlay').disabled=!end;$('scoreStop').disabled=!scorePlayback.enabled;
  $('scorePlay').textContent=scorePlayback.enabled?'試播 ON':'試播 OFF';
  $('scorePlay').setAttribute('aria-checked',String(scorePlayback.enabled));
}
function stopScorePlayback(keepEnabled=false){
  if(keepEnabled!==true){scorePlayback.enabled=false;closeScrub();}
  referenceAudio.gain=null;
  const p=scorePlayback;if(p.ctx){p.position=Math.min(p.end,p.start+Math.max(0,p.ctx.currentTime-p.origin));p.ctx.close().catch(()=>{});p.ctx=null;}
  p.generation++;cancelAnimationFrame(p.raf);p.raf=0;updateScoreCursor();
}
function seekScore(value){stopScorePlayback(true);scorePlayback.position=Number.isFinite(Number(value))?Math.max(0,Math.min(2400,Number(value))):0;updateScoreCursor();if(scorePlayback.enabled)scrubAtCursor();}
$('scoreSeek').oninput=e=>seekScore(e.target.value);$('scoreSeek').onchange=finishSeek;
$('scoreSeek').onpointercancel=()=>stopScorePlayback();
$('scorePosition').onchange=e=>{seekScore(e.target.value);finishSeek();};
$('scoreRewind').onclick=()=>{seekScore(0);finishSeek();};$('scoreStop').onclick=()=>stopScorePlayback();
$('scoreGrid').addEventListener('pointermove',e=>{if(scorePlayback.seeking)seekScore((gridPoint(e).x-64)/Number($('scoreZoom').value));});
function previewSegments(notes,position){return notes.filter(n=>n.e>position).map(n=>({...n,s:Math.max(n.s,position)-position,e:n.e-position})).sort((a,b)=>a.s-b.s);}
$('scorePlay').onclick=async()=>{if(scorePlayback.enabled){stopScorePlayback();return;}scorePlayback.enabled=true;return startScorePlayback();};
async function startScorePlayback(){
  closeScrub();stopScorePlayback(true);stopPreview();const p=scorePlayback,end=scoreEnd();if(!p.enabled||p.position>=end)return;
  const generation=p.generation,start=p.position,ctx=new AudioContext();p.ctx=ctx;p.start=start;p.end=end;p.origin=ctx.currentTime;updateScoreCursor();
  try{await ctx.resume();if(p.generation!==generation||p.ctx!==ctx)return;p.origin=ctx.currentTime+.05;
    scheduleReference(ctx,p.origin,start);
    const master=ctx.createGain();master.gain.value=.045;master.connect(ctx.destination);
    const notes=previewSegments(playbackNotes(),start);let index=0;
    function frame(){if(p.ctx!==ctx)return;const elapsed=Math.max(0,ctx.currentTime-p.origin);
      while(index<notes.length&&notes[index].s<=elapsed+.25){const n=notes[index++];if(n.e<=elapsed)continue;
        const s=Math.max(ctx.currentTime,p.origin+n.s),e=p.origin+n.e,osc=ctx.createOscillator(),gain=ctx.createGain(),ramp=Math.min(n.mode==='cello'?.06:n.mode==='violin'?.035:.015,(e-s)/3);
        osc.type=voiceType(n.mode||editor.score.settings.mode);osc.frequency.value=440*2**((n.p-69)/12);
        gain.gain.setValueAtTime(0,s);gain.gain.linearRampToValueAtTime(Math.max(.05,Math.min(1,n.v)),s+ramp);gain.gain.linearRampToValueAtTime(Math.max(.05,Math.min(1,n.v))*(['piano','harp'].includes(n.mode)? .25:1),e-ramp);gain.gain.linearRampToValueAtTime(0,e);
        osc.connect(gain);gain.connect(master);osc.onended=()=>{osc.disconnect();gain.disconnect();};osc.start(s);osc.stop(e);
      }
      p.position=Math.min(end,start+elapsed);updateScoreCursor();const x=64+p.position*Number($('scoreZoom').value),pane=$('scoreScroll');if(x>pane.scrollLeft+pane.clientWidth-30||x<pane.scrollLeft)pane.scrollLeft=Math.max(0,x-100);
      if(p.position>=end){stopScorePlayback(true);return;}p.raf=requestAnimationFrame(frame);
    }frame();
  }catch(e){stopScorePlayback();toast('無法啟動試播：'+e.message,true);}
}
function closeScrub(){if(scrub.ctx)scrub.ctx.close().catch(()=>{});scrub.ctx=null;scrub.nodes=[];scrub.last=-1;}
async function scrubAtCursor(){
  if(!scorePlayback.enabled||!editor.score)return;
  try{
    if(!scrub.ctx)scrub.ctx=new AudioContext();const ctx=scrub.ctx;await ctx.resume();
    if(scrub.ctx!==ctx||!scorePlayback.enabled)return;
    const now=ctx.currentTime;if(now-scrub.last<.05)return;scrub.last=now;
    for(const node of scrub.nodes){try{node.stop();}catch{}}scrub.nodes=[];
    const t=scorePlayback.position,notes=playbackNotes().filter(n=>n.s<=t&&n.e>t).slice(0,32);
    for(const n of notes){const osc=ctx.createOscillator(),gain=ctx.createGain();osc.type=voiceType(n.mode||editor.score.settings.mode);osc.frequency.value=440*2**((n.p-69)/12);
      const volume=.07*Math.max(.05,Math.min(1,n.v))/Math.sqrt(Math.max(1,notes.length));
      gain.gain.setValueAtTime(0,now);gain.gain.linearRampToValueAtTime(volume,now+.008);gain.gain.linearRampToValueAtTime(0,now+.10);
      osc.connect(gain);gain.connect(ctx.destination);osc.onended=()=>{osc.disconnect();gain.disconnect();};osc.start(now);osc.stop(now+.11);scrub.nodes.push(osc);
    }
  }catch(e){stopScorePlayback();toast('無法啟動拖曳試聽：'+e.message,true);}
}
function finishSeek(){closeScrub();if(scorePlayback.enabled)startScorePlayback();}
window.addEventListener('beforeunload',stopScorePlayback);
document.addEventListener('visibilitychange',()=>{if(document.hidden)stopScorePlayback();});

const instrumentNames={piano:'鋼琴',cello:'大提琴',violin:'小提琴',harp:'豎琴'};
function voiceType(mode){return {piano:'triangle',cello:'sawtooth',violin:'sawtooth',harp:'sine'}[mode]||'triangle';}
function syncTrack(){
  if(editor.active>=0)Object.assign(editor.tracks[editor.active],{score:editor.score,undo:editor.undo,redo:editor.redo,dirty:editor.dirty});
}
function playbackNotes(){
  syncTrack();
  const tracks=editor.tracks.length?editor.tracks:[{score:editor.score}];
  return tracks.flatMap((t,i)=>{
    const score=editor.compare&&i===editor.active?t.comparison:t.score;
    return t.muted||!score?[]:score.notes.map(n=>({...n,mode:score.settings.mode}));
  });
}
function renderTracks(){
  const list=$('trackList');list.replaceChildren();
  editor.tracks.forEach((t,i)=>{
    const mute=document.createElement('button');mute.textContent=t.muted?'🔇':'🔊';mute.title='切換此音軌試聽';mute.setAttribute('aria-pressed',String(!t.muted));
    mute.onclick=()=>{const playing=scorePlayback.enabled;stopScorePlayback(true);t.muted=!t.muted;drawScore();if(playing)startScorePlayback();};
    const select=document.createElement('button');select.textContent=(i===editor.active?'● ':'')+instrumentNames[t.score.settings.mode]+' · '+t.score.title;
    select.onclick=()=>activateTrack(i);list.append(mute,select);
  });
  $('switchCompare').disabled=!editor.tracks[editor.active]?.comparison;
  $('switchCompare').textContent=editor.compare?'SWITCH · 比較組':'SWITCH · 編輯組';
  $('switchCompare').setAttribute('aria-pressed',String(editor.compare));
  if(editor.score)$('trackInstrument').value=editor.score.settings.mode;
}
function activateTrack(i){
  const playing=scorePlayback.enabled;stopScorePlayback(true);syncTrack();
  editor.active=i;const t=editor.tracks[i];editor.score=t.score;editor.undo=t.undo||[];editor.redo=t.redo||[];editor.dirty=!!t.dirty;editor.compare=false;clearScoreSelection();
  $('scoreTitle').value=t.score.title;$('scoreCountdown').value=t.score.settings.countdown;drawScore();if(playing)startScorePlayback();
}
$('addTrack').onclick=()=>{
  stopScorePlayback();syncTrack();
  const mode=$('trackInstrument').value||'piano';
  editor.tracks.push({score:{version:1,title:'未命名樂譜',settings:{...options(),mode},notes:[]},comparison:null,muted:false,undo:[],redo:[],dirty:false});
  activateTrack(editor.tracks.length-1);
};
$('trackInstrument').onchange=()=>{if(!editor.score)return;remember();editor.score.settings.mode=$('trackInstrument').value;drawScore();};
$('importComparison').onclick=async()=>{
  if(!editor.score){toast('請先建立編輯組。',true);return;}
  const target=editor.tracks[editor.active];
  try{const r=await call('import_score');if(r.cancelled)return;stopScorePlayback();target.comparison=cloneScore(r.score);drawScore();}catch(e){toast(e.message,true);}
};
$('switchCompare').onclick=()=>{
  if(!editor.tracks[editor.active]?.comparison)return;
  const playing=scorePlayback.enabled;stopScorePlayback(true);editor.compare=!editor.compare;drawScore();if(playing)startScorePlayback();
};
function copyNotes(){
  if(!editor.score)return;
  const ids=editor.boxMode?[...editor.selection]:editor.selected<0?[]:[editor.selected];
  if(!ids.length)return;
  const notes=ids.map(i=>editor.score.notes[i]),start=Math.min(...notes.map(n=>n.s));
  editor.clipboard=notes.map(n=>({...n,s:n.s-start,e:n.e-start}));
}
function pasteNotes(){
  if(!editor.score||!editor.clipboard.length)return;
  const start=scorePlayback.position;
  if(editor.clipboard.some(n=>n.e+start>2400)||editor.score.notes.length+editor.clipboard.length>20000){toast('貼上後超出樂譜範圍。',true);return;}
  remember();clearScoreSelection();editor.boxMode=true;
  editor.clipboard.forEach(n=>{editor.selection.add(editor.score.notes.length);editor.score.notes.push({...n,s:+(n.s+start).toFixed(3),e:+(n.e+start).toFixed(3),p:editor.score.settings.root+scaleSteps[keyOrder.indexOf(n.k)]});});drawScore();
}
$('copyNotes').onclick=copyNotes;$('pasteNotes').onclick=pasteNotes;
document.addEventListener('keydown',e=>{
  if($('editorPage').hidden||editor.drag||e.target?.isContentEditable||['INPUT','TEXTAREA','SELECT'].includes(e.target?.tagName))return;
  if(!(e.ctrlKey||e.metaKey)||e.altKey)return;
  const key=e.key.toLowerCase();
  if(!['c','v','z','y'].includes(key))return;e.preventDefault();
  if(key==='c')copyNotes();else if(key==='v')pasteNotes();else if(key==='y'||e.shiftKey)historyScore(editor.redo,editor.undo);else historyScore(editor.undo,editor.redo);
});


function referenceTiming(position){
  const at=position+referenceAudio.offset;
  return {delay:Math.max(0,-at),offset:Math.max(0,at)};
}
function scheduleReference(ctx,origin,position){
  const buffer=referenceAudio.buffer;if(!buffer)return;
  const timing=referenceTiming(position);if(timing.offset>=buffer.duration)return;
  const source=ctx.createBufferSource(),gain=ctx.createGain();
  source.buffer=buffer;gain.gain.value=referenceAudio.muted?0:referenceAudio.volume;
  source.connect(gain);gain.connect(ctx.destination);referenceAudio.gain=gain;
  source.onended=()=>{source.disconnect();gain.disconnect();if(referenceAudio.gain===gain)referenceAudio.gain=null;};
  source.start(origin+timing.delay,timing.offset);
}
function updateReferenceVolume(){
  const gain=referenceAudio.gain;
  if(gain)gain.gain.value=referenceAudio.muted?0:referenceAudio.volume;
  $('referenceVolumeLabel').textContent=Math.round(referenceAudio.volume*100)+'%';
  $('referenceMute').textContent=referenceAudio.muted?'🔇 原曲靜音':'🔊 原曲開啟';
  $('referenceMute').setAttribute('aria-pressed',String(referenceAudio.muted));
}
$('importReference').onclick=()=>$('referenceFile').click();
$('referenceFile').onchange=async event=>{
  const file=event.target.files?.[0];event.target.value='';if(!file)return;
  if(!file.name.toLowerCase().endsWith('.mp3')||file.size>50*1024*1024||!file.size){toast('請選擇非空白且小於 50 MB 的 MP3。',true);return;}
  const generation=++referenceAudio.loading;let ctx;
  $('referenceName').textContent='正在載入 '+file.name+'…';
  try{
    ctx=new AudioContext();const buffer=await ctx.decodeAudioData(await file.arrayBuffer());
    if(generation!==referenceAudio.loading)return;
    if(buffer.duration>1200)throw Error('參考 MP3 最長支援 20 分鐘。');
    stopScorePlayback();referenceAudio.buffer=buffer;referenceAudio.name=file.name;referenceAudio.offset=0;
    $('referenceOffset').value=0;$('referenceName').textContent=file.name+' · '+buffer.duration.toFixed(2)+' 秒';drawScore();
  }catch(error){if(generation===referenceAudio.loading){$('referenceName').textContent=referenceAudio.name||'尚未匯入原曲';toast('無法載入 MP3：'+error.message,true);}}
  finally{if(ctx)await ctx.close();}
};
$('referenceVolume').oninput=e=>{referenceAudio.volume=Math.max(0,Math.min(1,Number(e.target.value)/100));updateReferenceVolume();};
$('referenceMute').onclick=()=>{referenceAudio.muted=!referenceAudio.muted;updateReferenceVolume();};
$('referenceOffset').onchange=e=>{
  const value=Number(e.target.value);
  if(!Number.isFinite(value)||Math.abs(value)>1200){e.target.value=referenceAudio.offset;toast('偏移需介於 -1200 與 1200 秒。',true);return;}
  const playing=scorePlayback.enabled;stopScorePlayback(true);referenceAudio.offset=value;drawScore();if(playing)startScorePlayback();
};
$('removeReference').onclick=()=>{
  const playing=scorePlayback.enabled;stopScorePlayback(true);referenceAudio.loading++;referenceAudio.buffer=null;referenceAudio.name='';referenceAudio.offset=0;
  $('referenceOffset').value=0;$('referenceName').textContent='尚未匯入原曲';drawScore();if(playing)startScorePlayback();
};
updateReferenceVolume();

drawScore();
