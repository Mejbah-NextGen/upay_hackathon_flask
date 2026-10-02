(() => {
  'use strict';
  const source = document.getElementById('reportChartData');
  if (!source) return;
  const data = JSON.parse(source.textContent), labels = JSON.parse(document.getElementById('reportChartLabels').textContent);
  const ns = 'http://www.w3.org/2000/svg', colors = { incoming: '#17a769', outgoing: '#0b63ce', net: '#a276ef' };
  const money = value => `BDT ${Number(value).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
  const translate = value => typeof window.upayT === 'function' ? window.upayT(value) : value;
  const number = value => Number(value).toLocaleString(undefined, {maximumFractionDigits: 1, notation: Math.abs(value) >= 10000 ? 'compact' : 'standard'});
  const node = (name, attributes = {}, content) => {const item = document.createElementNS(ns, name); Object.entries(attributes).forEach(([key,value]) => item.setAttribute(key, value)); if (content !== undefined) item.textContent = content; return item;};
  const append = (parent, name, attributes, content) => {const item = node(name, attributes, content); parent.append(item); return item;};
  const tooltip = (item, text) => {item.setAttribute('tabindex','0');item.setAttribute('aria-label',text);append(item,'title',{},text);};
  const empty = target => {const p = document.createElement('p');p.className='report-chart-empty';p.textContent=labels.empty;document.getElementById(target).append(p);};
  const compactViewport = window.matchMedia('(max-width: 620px)');
  const render = () => {
  ['reportBarChart','reportCumulativeChart','reportPieChart','reportHistogramChart','reportPieLegend'].forEach(id => document.getElementById(id).replaceChildren());
  const chart = (target, values, minimum = 0) => {
    const svg = append(document.getElementById(target), 'svg', {viewBox:'0 0 600 300', 'aria-hidden':'true'});
    const low = Math.min(minimum, ...values), high = Math.max(1, ...values), range = high-low || 1;
    const y = value => 250-(value-low)/range*215;
    for(let i=0;i<=4;i++){const value=low+range*i/4,position=y(value);append(svg,'line',{x1:66,x2:550,y1:position,y2:position,class:'chart-grid'});append(svg,'text',{x:59,y:position+4,'text-anchor':'end','font-size':12,class:'chart-axis-text'},number(value));}
    append(svg,'line',{x1:66,x2:550,y1:y(0),y2:y(0),stroke:'var(--muted)','stroke-width':1});
    return {svg,y,left:66,right:550,top:35,bottom:250};
  };
  const barRows = [];
  const groupSize = Math.max(1, Math.ceil(data.daily.length/(compactViewport.matches ? 5 : 10)));
  for(let i=0;i<data.daily.length;i+=groupSize){const rows=data.daily.slice(i,i+groupSize);barRows.push({start:rows[0].date,end:rows[rows.length-1].date,incoming:rows.reduce((s,r)=>s+r.incoming,0),outgoing:rows.reduce((s,r)=>s+r.outgoing,0)});}
  const bars=chart('reportBarChart',barRows.flatMap(row=>[row.incoming,row.outgoing]));
  const step=(bars.right-bars.left)/Math.max(1,barRows.length);
  barRows.forEach((row,i)=>{
    const center=bars.left+step*(i+.5),width=Math.min(20,step*.32);
    ['incoming','outgoing'].forEach((key,k)=>{const x=center+(k-1)*width,rect=append(bars.svg,'rect',{x,y:bars.y(row[key]),width:Math.max(2,width-2),height:Math.max(0,bars.y(0)-bars.y(row[key])),fill:colors[key],rx:2});tooltip(rect,`${row.start}${row.end!==row.start?' – '+row.end:''}: ${labels[key]} ${money(row[key])}`);});
    const label=append(bars.svg,'text',{x:center,y:273,'font-size':11,'text-anchor':'middle',class:'chart-axis-text'},row.start.slice(5));
    tooltip(label,`${row.start}${row.end!==row.start?' – '+row.end:''}`);
  });
  append(bars.svg,'text',{x:550,y:17,'font-size':12,'text-anchor':'end',class:'chart-axis-text'},'BDT');
  const cumulative=chart('reportCumulativeChart',[0,...data.daily.flatMap(row=>[row.cumulative_incoming,row.cumulative_outgoing,row.cumulative_net])]);
  const first=Date.parse(data.daily[0].date),last=Date.parse(data.daily[data.daily.length-1].date),span=last-first;
  const xAt = row => span ? 100+(Date.parse(row.date)-first)/span*450 : 550;
  ['incoming','outgoing','net'].forEach(key=>{
    const field=`cumulative_${key}`, points=[[66,cumulative.y(0)],...data.daily.map(row=>[xAt(row),cumulative.y(row[field])])];
    append(cumulative.svg,'polyline',{points:points.map(p=>p.join(',')).join(' '),fill:'none',stroke:colors[key],'stroke-width':3});
    data.daily.forEach(row=>{const circle=append(cumulative.svg,'circle',{cx:xAt(row),cy:cumulative.y(row[field]),r:4,fill:colors[key]});tooltip(circle,`${row.date}: ${labels[key]} ${money(row[field])}`);});
  });
  append(cumulative.svg,'text',{x:66,y:273,'font-size':11,class:'chart-axis-text'},data.daily[0].date);
  append(cumulative.svg,'text',{x:550,y:273,'font-size':11,'text-anchor':'end',class:'chart-axis-text'},data.daily[data.daily.length-1].date);
  append(cumulative.svg,'text',{x:550,y:17,'font-size':12,'text-anchor':'end',class:'chart-axis-text'},'BDT');
  const palette=['#0b63ce','#17a769','#a276ef','#ef9550','#e33d52','#14a6a6','#cc65ab','#8b9a31'];
  if(!data.outgoing_count){empty('reportPieChart');empty('reportHistogramChart');return;}
  const pie=append(document.getElementById('reportPieChart'),'svg',{viewBox:'0 0 600 300','aria-hidden':'true'}),radius=99,circumference=2*Math.PI*radius;let offset=0;
  data.categories.forEach((row,i)=>{
    const percentage=row.amount/data.outgoing_total, color=palette[i%palette.length];
    const circle=append(pie,'circle',{cx:300,cy:150,r:radius,fill:'none',stroke:color,'stroke-width':58,'stroke-dasharray':`${percentage*circumference} ${circumference}`,'stroke-dashoffset':-offset*circumference,transform:'rotate(-90 300 150)'});tooltip(circle,`${translate(row.label)}: ${money(row.amount)} (${(percentage*100).toFixed(1)}%)`);offset+=percentage;
    const legend=document.createElement('span'),swatch=document.createElement('i');swatch.className='chart-swatch';swatch.style.background=color;legend.append(swatch,document.createTextNode(`${translate(row.label)} ${(percentage*100).toFixed(1)}%`));document.getElementById('reportPieLegend').append(legend);
  });
  append(pie,'text',{x:300,y:146,'font-size':14,'text-anchor':'middle',class:'chart-axis-text'},labels.outgoing);
  append(pie,'text',{x:300,y:176,'font-size':19,'font-weight':700,'text-anchor':'middle',class:'chart-total-text'},money(data.outgoing_total));
  const histogram=chart('reportHistogramChart',[...data.histogram.map(row=>row.count),Math.max(4,Math.ceil(Math.max(...data.histogram.map(row=>row.count))/4)*4)]),histStep=(histogram.right-histogram.left)/data.histogram.length;
  const linePoints=[];
  data.histogram.forEach((row,i)=>{
    const center=histogram.left+histStep*(i+.5),rect=append(histogram.svg,'rect',{x:center-histStep*.29,y:histogram.y(row.count),width:histStep*.58,height:histogram.y(0)-histogram.y(row.count),fill:colors.outgoing,rx:3});tooltip(rect,`BDT ${row.label}: ${row.count} ${labels.transactions}`);
    const percentageY=250-row.cumulative_percent/100*215;linePoints.push([center,percentageY]);
    const circle=append(histogram.svg,'circle',{cx:center,cy:percentageY,r:4,fill:colors.net});tooltip(circle,`BDT ${row.label}: ${row.cumulative_percent}% ${labels.cumulative}`);
    const bound = value => value >= 1000 ? `${value/1000}k` : String(value);
    const shortLabel = row.upper === null ? `${bound(row.lower)}+` : `${bound(row.lower)}–${bound(row.upper)}`;
    const label=append(histogram.svg,'text',{x:center,y:274,'font-size':10,'text-anchor':'middle',class:'chart-axis-text chart-band-text'},shortLabel);
    tooltip(label,`BDT ${row.label}`);
  });
  append(histogram.svg,'polyline',{points:linePoints.map(point=>point.join(',')).join(' '),fill:'none',stroke:colors.net,'stroke-width':3});
  for(let percent=0;percent<=100;percent+=25)append(histogram.svg,'text',{x:596,y:254-percent/100*215,'font-size':11,'text-anchor':'end',class:'chart-axis-text chart-percent-text'},`${percent}%`);
  };
  render();
  compactViewport.addEventListener('change',render);
})();
