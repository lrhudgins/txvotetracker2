(function(root){
  function score(value){
    if(typeof value!=='number'||!Number.isFinite(value))return '#94a3b8';
    const v=Math.max(-100,Math.min(100,value));
    const from=v<0?[37,99,235]:[248,250,252];
    const to=v<0?[248,250,252]:[249,115,22];
    const t=v<0?(v+100)/100:v/100;
    return '#'+from.map((c,i)=>Math.round(c+(to[i]-c)*t).toString(16).padStart(2,'0')).join('');
  }
  function count(value){return typeof value!=='number'?'#94a3b8':value>1000?'#086951':value>250?'#26a985':'#84d4b5'}
  const api={score,count};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else root.TX10Colors=api;
})(typeof window==='undefined'?globalThis:window);
