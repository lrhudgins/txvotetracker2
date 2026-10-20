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
 legend.innerHTML=metric==='score'?'<div style="height:12px;border-radius:4px;background:linear-gradient(to right,#ef4444,#f8fafc,#2563eb)"></div><div style="display:flex;justify-content:space-between;margin-top:5px"><span>Republican</span><span>0</span><span>Democrat</span></div><div style="margin-top:6px">Gray: no populated score. Party labels describe the supplied score scale, not a recorded ballot choice.</div>':'Early-vote counts: lighter green ≤250; medium green 251–1,000; dark green >1,000. Gray: no report.';
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
    layer.bindPopup(`<strong>${escape(p.county)} · Precinct ${escape(p.precinct)}</strong><br>Average early-voter score: ${mean}<br>Matched early voters with scores: ${fmt(s?.scored_count)}<br>Matched early voters missing scores: ${fmt(s?.missing_score_count)}<br>Matched by ID: ${fmt(s?.id_match_count)} · by name: ${fmt(s?.name_match_count)}<br>Unmatched: ${fmt(s?.unmatched_count)} · ambiguous: ${fmt(s?.ambiguous_count)} · conflicting ID: ${fmt(s?.identifier_conflict_count)}<br>Score as of: ${escape(s?.as_of||'Unavailable')}${s?.status==='stale'?'<br><strong>Score data is stale; check diagnostics.</strong>':''}<br>Reported early voters: ${fmt(n)}<br><small>Scores describe matched early voters only. Unmatched voters are excluded, not assigned zero.<br>2026 primary outline; November continuity is unverified.</small>`);
   }
  }).addTo(precinctMap);
  precinctLayers.push(layer);if(border)border.bringToFront();
  $('mapnote').textContent=`${geo.features.length} primary-reference precincts assigned to CD-10; ${matched} have populated average scores. Full reference outlines may differ from November boundaries. Scores average only matched early voters with populated scores; match coverage varies by precinct.`;
 }catch(e){$('mapnote').textContent='Precinct map unavailable. Copy docs/data/precincts.geojson from the update package.'}
 const waiting=(scores.diagnostics||[]).filter(r=>r.status==='waiting_for_roster').map(r=>r.county);
 const incomplete=(scores.diagnostics||[]).reduce((sum,r)=>sum+(r.incomplete_rows_ignored||0),0);
 const unidentified=(scores.diagnostics||[]).reduce((sum,r)=>sum+(r.unidentifiable_rows_ignored||0),0);
 $('scoreerrors').textContent=[...(scores.errors||[]),...(waiting.length?['Waiting for local rosters: '+waiting.join(', ')]:[]),...(incomplete?[`${incomplete} truncated score row(s) skipped. Re-export incomplete input rows to include them.`]:[]),...(unidentified?[`${unidentified} scored row(s) skipped: missing state voter ID and usable first/last names. VAN ID alone cannot match county rosters.`]:[])].join(' ');
}
