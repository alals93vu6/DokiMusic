'use strict';
const $ = id => document.getElementById(id);
const state = {ready:false, file:null, mode:'piano', busy:false, result:null, dirty:false, ctx:null, raf:0, poll:null};
const keyOrder = 'ASDFGHJQWERTYUI';
const scaleSteps = [0,2,4,5,7,9,11,12,14,16,17,19,21,23,24];
const noteName = p => ['C','C♯','D','D♯','E','F','F♯','G','G♯','A','A♯','B'][p%12] + (Math.floor(p/12)-1);
const timeLabel = t => `${Math.floor(t/60)}:${String(Math.floor(t%60)).padStart(2,'0')}`;
for(let p=36;p<=72;p++){ const o = new Option(noteName(p),p); o.selected=p===60; $('root').add(o); }
for(let p=-12;p<=12;p++){ const o=new Option(p===0?'0 · 不移調':`${p>0?'+':''}${p} 半音`,p);o.selected=p===0;$('transpose').add(o); }
function options(){return {texture:document.getElementById("texture").value,mode:state.mode,max_voices:Number($('voices').value),countdown:Number($('countdown').value),speed:Number($('speed').value),root:Number($('root').value),transpose:Number($('transpose').value),accidental:$('accidental').value,isolation:$('isolation').value,strictness:$('strictness').value,device:$('device').value};}
function toast(message,error=false){$('notice').textContent=message;$('notice').classList.toggle('error',error);$('notice').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('notice').hidden=true,error?14000:9000);}
async function call(name,...args){if(!state.ready)throw new Error('本機引擎尚未連接，請使用桌面啟動檔開啟工具。');const r=await window.pywebview.api[name](...args);if(r && r.ok===false)throw new Error(r.error);return r;}
function controls(){
  $('choose').disabled=$('demo').disabled=!state.ready||state.busy;
  $('analyze').disabled=!state.ready||!state.file||state.busy;
  $('cancel').hidden=!state.busy;
  $('piano').disabled=$('cello').disabled=state.busy;
  for(const id of ['voices','countdown','speed','root','transpose','accidental','isolation','strictness','device','texture'])$(id).disabled=state.busy;
  if($('texture').value==='melody'){
    if(!$('voices').dataset.fullVoices)$('voices').dataset.fullVoices=$('voices').value;
    $('voices').value='1';$('voices').disabled=true;
  }else if($('voices').dataset.fullVoices){
    $('voices').value=$('voices').dataset.fullVoices;delete $('voices').dataset.fullVoices;
  }
  if($('isolation').value==='solo')$('strictness').disabled=$('device').disabled=true;
  $('export').disabled=$('preview').disabled=!state.result||state.busy||state.dirty;
  $('analyze').innerHTML=state.busy?'正在分析…':state.result?'套用設定並重新編排 <span>→</span>':'分析並編排 <span>→</span>';
}
function keyboard(){
  const root=Number($('root').value);$('keyboard').replaceChildren();
  [...keyOrder].forEach((k,i)=>{const el=document.createElement('div');el.className='key';el.id='key-'+k;el.append(document.createTextNode(k));const small=document.createElement('small');small.textContent=noteName(root+scaleSteps[i]);el.append(small);$('keyboard').append(el);});
}
function changed(){stopPreview();state.dirty=!!state.result;if(state.result){$('resultTag').textContent='設定已變更';$('engineState').textContent='按「套用設定」更新編排後再匯出。';}keyboard();controls();}
for(const id of ['voices','countdown','speed','root','transpose','accidental','isolation','strictness','device','texture'])$(id).addEventListener('change',()=>{updateModeHint();changed();});
function updateModeHint(){const name=state.mode==='piano'?'鋼琴':'大提琴';$('modeHint').textContent=$('isolation').value==='mixed'?`先分離${name}，再辨識${state.mode==='piano'?'旋律與和弦':'持續音與主旋律'}。`:`純獨奏模式：沿用原有${name}辨識，不分離其他樂器。`;}
for(const mode of ['piano','cello'])$(mode).addEventListener('click',()=>{
  state.mode=mode;for(const m of ['piano','cello']){$(m).classList.toggle('selected',m===mode);$(m).setAttribute('aria-pressed',m===mode?'true':'false');}
  $('voices').value=mode==='piano'?'8':'1';
  updateModeHint();changed();
});
async function choose(method){
  try{stopPreview();const r=await call(method);if(r.cancelled)return;state.file=r.file;state.result=null;state.dirty=false;
    $('fileName').textContent=r.file.name;$('fileMeta').textContent=`${(r.file.size/1024/1024).toFixed(2)} MB · 已匯入`;
    $('empty').hidden=false;$('result').hidden=true;$('resultTag').textContent='等待分析';$('progressArea').hidden=true;$('engineState').textContent='本機引擎已就緒';controls();
  }catch(e){toast(e.message,true);}
}
$('choose').addEventListener('click',()=>choose('choose_file'));
$('demo').addEventListener('click',()=>choose('choose_demo'));
$('analyze').addEventListener('click',async()=>{
  stopPreview();state.busy=true;controls();$('progressArea').hidden=false;$('progressText').textContent='準備分析…';$('progressBar').style.width='1%';$('percent').textContent='1%';$('engineState').textContent='分析期間可以取消';
  try{await call('analyze',options());poll();}catch(e){state.busy=false;controls();toast(e.message,true);}
});
$('cancel').addEventListener('click',async()=>{try{$('cancel').disabled=true;await call('cancel');}catch(e){toast(e.message,true);}finally{$('cancel').disabled=false;}});
async function poll(){
  try{const s=await call('get_status');$('progressText').textContent=s.message;$('progressBar').style.width=s.progress+'%';$('percent').textContent=s.progress+'%';
    if(s.status==='running'){state.poll=setTimeout(poll,650);return;}
    state.busy=false;
    if(s.status==='done'){state.result=s.result;state.dirty=false;render();$('engineState').textContent='編排完成 · 可調整設定或匯出';}
    else{$('engineState').textContent=s.status==='cancelled'?'已取消分析':'分析未完成';toast(s.message,s.status==='error');state.result=null;$('result').hidden=true;$('empty').hidden=false;$('resultTag').textContent=s.status==='cancelled'?'已取消':'請重試';}
    controls();
  }catch(e){state.busy=false;controls();toast(e.message,true);}
}
function render(){
  const r=state.result,s=r.stats;$('empty').hidden=true;$('result').hidden=false;$('resultTag').textContent='READY TO PLAY';
  $('noteCount').textContent=s.playable.toLocaleString();$('songDuration').textContent=timeLabel(s.duration);$('peakVoices').textContent=s.peak_voices+' 音';
  $('previewRange').textContent=`0:00 — ${timeLabel(Math.min(30,s.duration))}`;
  $('mappingNote').textContent=`辨識 ${s.detected} 音 → 編排 ${s.playable} 音。${s.octave_shifted} 音移八度、${s.approximated} 音近似替換、${s.skipped} 音略過；已移除開頭 ${s.trimmed_seconds} 秒空白。最低音預設／校準為 ${noteName(r.settings.root)}。`;
  const iso=r.isolation||{};$('isolationNote').hidden=false;
  if(r.settings.texture==='melody')$('mappingNote').textContent+=` 僅主旋律：候選中排除 ${s.melody_removed} 音；自動選線可能誤判，建議進編輯模式檢查。`;
  $('isolationNote').textContent=iso.enabled?`目標分離已完成 · ${iso.device} · ${iso.seconds} 秒。分離後 ${iso.candidate_notes} 個候選音，篩除 ${iso.rejected_notes} 個低可信度音符。可信度是訊號證據分數，並非準確率；仍可能有樂器殘留。`:'純獨奏：已沿用原始音訊與原本辨識流程，未啟用目標樂器分離。';
  drawRoll();
}
function drawRoll(cursor=-1){
  const canvas=$('roll');const w=canvas.clientWidth||600,h=170,dpr=window.devicePixelRatio||1;canvas.width=w*dpr;canvas.height=h*dpr;const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);ctx.clearRect(0,0,w,h);
  if(!state.result)return;const duration=Math.min(30,state.result.stats.duration),left=27,top=8,usable=w-left-9,row=9;
  ctx.font='8px Segoe UI';ctx.textBaseline='middle';
  [...keyOrder].forEach((k,i)=>{const y=top+(14-i)*row;ctx.strokeStyle='#23302a';ctx.beginPath();ctx.moveTo(left,y+row);ctx.lineTo(w-5,y+row);ctx.stroke();ctx.fillStyle='#7f9686';ctx.fillText(k,8,y+row/2);});
  for(let t=0;t<=duration;t+=5){const x=left+t/duration*usable;ctx.strokeStyle='#2c3930';ctx.beginPath();ctx.moveTo(x,top);ctx.lineTo(x,top+135);ctx.stroke();ctx.fillStyle='#72877a';ctx.fillText(timeLabel(t),Math.min(x,w-28),157);}
  for(const n of state.result.notes){if(n.s>=duration)continue;const x=left+n.s/duration*usable,y=top+(14-keyOrder.indexOf(n.k))*row+1;ctx.fillStyle=keyOrder.indexOf(n.k)<7?'#79cfc2':'#c5e99b';ctx.fillRect(x,y,Math.max(2,(Math.min(n.e,duration)-n.s)/duration*usable),6);}
  if(cursor>=0){const x=left+cursor/duration*usable;ctx.strokeStyle='#fff';ctx.beginPath();ctx.moveTo(x,top);ctx.lineTo(x,top+135);ctx.stroke();}
}
window.addEventListener('resize',()=>{if(state.result)drawRoll();});
function stopPreview(){
  cancelAnimationFrame(state.raf);state.raf=0;
  if(state.ctx){state.ctx.close().catch(()=>{});state.ctx=null;}
  $('preview').textContent='▷ 試聽前 30 秒';document.querySelectorAll('.key.active').forEach(k=>k.classList.remove('active'));if(state.result)drawRoll();
}
$('preview').addEventListener('click',async()=>{
  if(state.ctx){stopPreview();return;}
  try{
    const ctx=new AudioContext();state.ctx=ctx;await ctx.resume();
    const master=ctx.createGain();master.gain.value=.12/Math.sqrt(Math.max(1,state.result.stats.peak_voices));master.connect(ctx.destination);
    const duration=Math.min(30,state.result.stats.duration),start=ctx.currentTime+.1;
    for(const n of state.result.notes){if(n.s>=duration)continue;const s=start+n.s,e=start+Math.min(n.e,duration);const osc=ctx.createOscillator(),gain=ctx.createGain();
      osc.type=state.mode==='piano'?'triangle':'sawtooth';osc.frequency.value=440*2**((n.p-69)/12);const volume=Math.max(.15,Math.min(1,n.v));
      gain.gain.setValueAtTime(0,s);gain.gain.linearRampToValueAtTime(volume,Math.min(e,s+.015));gain.gain.setValueAtTime(volume,Math.max(s+.015,e-.025));gain.gain.linearRampToValueAtTime(0,e);
      osc.connect(gain);gain.connect(master);osc.start(s);osc.stop(e+.01);
    }
    $('preview').textContent='■ 停止試聽';
    function frame(){if(state.ctx!==ctx)return;const t=ctx.currentTime-start;if(t>duration+.1){stopPreview();return;}
      drawRoll(Math.max(0,t));const keys=new Set(state.result.notes.filter(n=>n.s<=t&&n.e>t).map(n=>n.k));[...keyOrder].forEach(k=>$('key-'+k).classList.toggle('active',keys.has(k)));state.raf=requestAnimationFrame(frame);}
    frame();
  }catch(e){stopPreview();toast('無法啟動試聽：'+e.message,true);}
});
$('export').addEventListener('click',async()=>{stopPreview();$('export').disabled=true;try{const r=await call('save_python');if(!r.cancelled)toast('已儲存：'+r.path);}catch(e){toast(e.message,true);}finally{controls();}});
function ready(){state.ready=true;$('engineState').textContent='本機引擎已就緒';controls();}
window.addEventListener('pywebviewready',ready);
window.addEventListener('beforeunload',stopPreview);
keyboard();controls();
if(window.pywebview&&window.pywebview.api)ready();
