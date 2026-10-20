let precinctMap, precinctLayers=[], currentVoteRows=[];
async function drawMap(rows){
 currentVoteRows=rows;
 if(typeof L==='undefined'){$('map').textContent='Map library unavailable. Counts remain available below.';return}
 const firstView=!precinctMap;
 if(!precinctMap){
  precinctMap=L.map('map').setView([30.8,-96.3],7);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap contributors',maxZoom:18}).addTo(precinctMap);
 }
 precinctLayers.forEach(layer=>precinctMap.removeLayer(layer));precinctLayers=[];
 const metric=$('mapmetric').value;
 const counts=new Map();
 rows.forEach(r=>{const key=r.county+'|'+pct(r.precinct);counts.set(key,(counts.get(key)||0)+r.count)});
 let scores={rows:[],errors:[]};
 try{scores=await get('data/precinct_scores.json')}catch(e){}
 const scoreByKey=new Map(scores.rows.map(r=>[r.county+'|'+pct(r.precinct),r]));
 const legend=$('maplegend');
 legend.innerHTML=metric==='score'?'<div style="height:12px;border-radius:4px;background:linear-gradient(to right,#2563eb,#f8fafc,#f97316)"></div><div style="display:flex;justify-content:space-between;margin-top:5px"><span>−100</span><span>0</span><span>+100</span></div><div style="margin-top:6px">Gray: no populated score. Colors express numeric values; no party labels are inferred.</div>':'Early-vote counts: lighter green ≤250; medium green 251–1,000; dark green >1,000. Gray: no report.';
 let border;
 try{
  const geo=await get('data/district.geojson');
  border=L.geoJSON(geo,{interactive:false,style:{color:'#1a3a60',weight:3,fillOpacity:0}}).addTo(precinctMap);
  precinctLayers.push(border);if(firstView)precinctMap.fitBounds(border.getBounds());
 }catch(e){}
 try{
  const geo=await get('data/precincts.geojson');let matched=0;
  const layer=L.geoJSON(geo,{
   style:feature=>{
    const key=feature.properties.county+'|'+pct(feature.properties.precinct);
    const value=metric==='score'?scoreByKey.get(key)?.mean_score:counts.get(key);
    return {color:'#45647d',weight:.7,fillColor:metric==='score'?TX10Colors.score(value):TX10Colors.count(value),fillOpacity:typeof value==='number' ? .8 : .2};
   },
   onEachFeature:(feature,layer)=>{
    const p=feature.properties,key=p.county+'|'+pct(p.precinct),s=scoreByKey.get(key),n=counts.get(key);
    if(s&&typeof s.mean_score==='number')matched++;
    const mean=s&&typeof s.mean_score==='number'?s.mean_score.toFixed(2):'Missing';
    layer.bindPopup(`<strong>${escape(p.county)} · Precinct ${escape(p.precinct)}</strong><br>Average uploaded score: ${mean}<br>Rows with scores: ${fmt(s?.scored_count)}<br>Rows missing scores: ${fmt(s?.missing_score_count)}<br>Score as of: ${escape(s?.as_of||'Unavailable')}${s?.status==='stale'?'<br><strong>Score data is stale; check diagnostics.</strong>':''}<br>Reported early voters: ${fmt(n)}<br><small>Score averages use supplied CSV rows; they are not restricted to early voters.<br>2026 primary outline; November continuity is unverified.</small>`);
   }
  }).addTo(precinctMap);
  precinctLayers.push(layer);if(border)border.bringToFront();
  $('mapnote').textContent=`${geo.features.length} primary-reference precincts assigned to CD-10; ${matched} have populated average scores. Full reference outlines may differ from November boundaries. Score averages and early-vote counts describe different supplied data.`;
 }catch(e){$('mapnote').textContent='Precinct map unavailable. Copy docs/data/precincts.geojson from the update package.'}
 $('scoreerrors').textContent=(scores.errors||[]).length?'Score import error: '+scores.errors.join(' '):'';
}
