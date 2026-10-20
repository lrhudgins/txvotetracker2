(function(root){
  function score(value){
    if(typeof value!=='number'||!Number.isFinite(value))return '#94a3b8';
    const v=Math.max(-100,Math.min(100,value));
    const from=v<0?[239,68,68]:[248,250,252];
    const to=v<0?[248,250,252]:[37,99,235];
    const t=v<0?(v+100)/100:v/100;
    return '#'+from.map((c,i)=>Math.round(c+(to[i]-c)*t).toString(16).padStart(2,'0')).join('');
  }
  function count(value){return typeof value!=='number'?'#94a3b8':value>1000?'#086951':value>250?'#26a985':'#84d4b5'}
  function summarizeScores(rows){
    const counties=new Map();
    const total={weightedSum:0,scored_count:0,stale_count:0,mean_score:null};
    for(const row of rows||[]){
      const n=row.scored_count,mean=row.mean_score;
      if(typeof row.county!=='string'||!Number.isSafeInteger(n)||n<=0||typeof mean!=='number'||!Number.isFinite(mean)||mean < -100||mean > 100)continue;
      let county=counties.get(row.county);
      if(!county){county={weightedSum:0,scored_count:0,stale_count:0,mean_score:null};counties.set(row.county,county)}
      for(const item of [county,total]){
        item.weightedSum+=mean*n;item.scored_count+=n;
        if(row.status==='stale')item.stale_count+=n;
      }
    }
    for(const item of [...counties.values(),total]){
      item.mean_score=item.scored_count?item.weightedSum/item.scored_count:null;
      delete item.weightedSum;
    }
    return {counties,total};
  }
  const api={score,count,summarizeScores};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else root.TX10Colors=api;
})(typeof window==='undefined'?globalThis:window);
