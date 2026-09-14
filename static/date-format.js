/* Work and provider timestamps use the application's Europe/Berlin calendar.
   Naive imported provider timestamps follow the UTC convention of the server. */
(()=>{
 const timeZone='Europe/Berlin';
 function parse(value){if(value==null||value==='')return null;if(value instanceof Date)return Number.isNaN(+value)?null:value;let text=String(value);if(/^\d{4}-\d{2}-\d{2}$/.test(text))return new Date(text+'T12:00:00Z');if(/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(text)&&!/(Z|[+-]\d{2}:?\d{2})$/i.test(text))text=text.replace(' ','T')+'Z';const date=new Date(text);return Number.isNaN(+date)?null:date;}
 const format=(value,options)=>{const date=parse(value);return date?date.toLocaleString('de-DE',{timeZone,...options}):'–';};
 window.pzDate={parse,timeZone,date:value=>format(value,{day:'2-digit',month:'2-digit',year:'numeric'}),time:(value,seconds=false)=>format(value,{hour:'2-digit',minute:'2-digit',...(seconds?{second:'2-digit'}:{})}),dateTime:(value,seconds=false)=>format(value,{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',...(seconds?{second:'2-digit'}:{})})};
})();
