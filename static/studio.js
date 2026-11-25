const $ = id => document.getElementById(id);
const token = document.querySelector('[name="studio-token"]').content;
const time = seconds => Math.floor(seconds / 60) + ":" + String(Math.floor(seconds % 60)).padStart(2,"0");
let fileMode = false, source, job, ctx, channels = [], nodes = [], offset = 0, started = 0, duration = 0;
function status(message){ $("status").textContent = message; }
async function api(path, options={}){
  const response = await fetch(path, {...options,headers:{"X-Studio":token,...options.headers}});
  if(!response.ok){
    const detail = await response.json().catch(()=>({}));
    throw Error(detail.error || "Request failed (" + response.status + ").");
  }
  return response;
}
function lock(on){
  for(const el of [...$("importForm").elements,$("split"),$("model")]) el.disabled=on;
}
function mode(useFile){
  fileMode=useFile;
  $("url").hidden=useFile; $("url").required=!useFile;
  $("file").hidden=!useFile; $("file").required=useFile;
  $("fileTab").setAttribute("aria-pressed",useFile); $("linkTab").setAttribute("aria-pressed",!useFile);
}
$("linkTab").onclick=()=>mode(false);
$("fileTab").onclick=()=>mode(true);
function clearMixer(){
  pause(); offset=0; channels=[]; $("mixer").hidden=true;
}
$("importForm").onsubmit=async event=>{
  event.preventDefault(); lock(true); clearMixer(); $("confirm").hidden=true;
  status("Reading song details…");
  try{
    const data=new FormData();
    if(fileMode) data.set("file",$("file").files[0]); else data.set("url",$("url").value);
    source=await (await api("/source",{method:"POST",body:data})).json();
    $("song").textContent=source.title+" · "+time(source.duration);
    $("confirm").hidden=false; status("");
  }catch(error){status(error.message+(fileMode?"":" You can also import an audio file."));}
  finally{lock(false);}
};
$("split").onclick=async()=>{
  clearMixer(); lock(true);
  try{
    const data=new FormData(); data.set("model",$("model").value);
    job=(await (await api("/split/"+source.id,{method:"POST",body:data})).json()).id;
    let state;
    do{
      state=await (await api("/job/"+job)).json(); status(state.status);
      if(state.error) throw Error(state.error);
      if(state.status!=="Ready") await new Promise(resolve=>setTimeout(resolve,1200));
    }while(state.status!=="Ready");
    status("Loading tracks into the mixer…");
    ctx ||= new AudioContext({sampleRate:44100});
    const loaded=[];
    for(const name of state.stems){
      const data=await (await api("/audio/"+job+"/"+name)).arrayBuffer();
      loaded.push({name,buffer:await ctx.decodeAudioData(data),volume:1,mute:false,solo:false});
    }
    channels=loaded; duration=Math.min(...channels.map(c=>c.buffer.duration));
    $("seek").max=duration; $("zip").href="/archive/"+job;
    render(); $("mixer").hidden=false; status("");
  }catch(error){status(error.message);}
  finally{lock(false);}
};
function level(c){return c.mute || (channels.some(x=>x.solo)&&!c.solo) ? 0 : c.volume;}
function updateLevels(){channels.forEach((c,i)=>{if(nodes[i]) nodes[i].gain.gain.value=level(c);});}
function render(){
  $("channels").replaceChildren();
  for(const c of channels){
    const row=document.createElement("div"); row.className="channel";
    const name=document.createElement("strong"); name.textContent=c.name; row.append(name);
    for(const key of ["solo","mute"]){
      const button=document.createElement("button"); button.textContent=key==="solo"?"Solo":"Mute";
      button.setAttribute("aria-label",button.textContent+" "+c.name); button.setAttribute("aria-pressed",false);
      button.onclick=()=>{c[key]=!c[key];button.setAttribute("aria-pressed",c[key]);updateLevels();};row.append(button);
    }
    const slider=document.createElement("input");slider.type="range";slider.min=0;slider.max=1;slider.step=.01;slider.value=1;
    slider.setAttribute("aria-label",c.name+" volume");slider.oninput=()=>{c.volume=Number(slider.value);updateLevels();};
    row.append(slider);$("channels").append(row);
  }
}
function position(){return nodes.length?Math.min(duration,Math.max(offset,ctx.currentTime-started)):offset;}
function pause(){
  offset=position();
  for(const {player,gain} of nodes){player.stop();player.disconnect();gain.disconnect();}
  nodes=[];$("play").textContent="Play";
}
function play(){
  if(offset>=duration) offset=0;
  const when=ctx.currentTime+.04;started=when-offset;
  nodes=channels.map(c=>{
    const player=ctx.createBufferSource(), gain=ctx.createGain();
    gain.gain.value=level(c);player.buffer=c.buffer;player.connect(gain).connect(ctx.destination);
    player.start(when,offset);return {player,gain};
  });$("play").textContent="Pause";
}
$("play").onclick=async()=>{await ctx.resume();if(nodes.length)pause();else play();};
$("seek").oninput=()=>{const active=nodes.length;pause();offset=Number($("seek").value);if(active)play();};
setInterval(()=>{if($("mixer").hidden)return;const pos=position();if(nodes.length&&pos>=duration)pause();$("clock").textContent=time(pos)+" / "+time(duration);$("seek").value=pos;},100);
$("export").onclick=async()=>{
  $("export").disabled=true;
  try{
    const levels=Object.fromEntries(channels.map(c=>[c.name,level(c)]));
    const res=await api("/mix/"+job,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(levels)});
    const link=document.createElement("a");link.href=URL.createObjectURL(await res.blob());link.download=source.title+" - mix.mp3";link.click();
    setTimeout(()=>URL.revokeObjectURL(link.href),60000);
  }catch(error){status(error.message);}finally{$("export").disabled=false;}
};
