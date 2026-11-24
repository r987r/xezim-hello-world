// GitHub Pages serves .gz as a downloadable file, not HTTP Content-Encoding.
async function loadReportCapture(path){
  const url=new URL(path,location.href);
  if(url.origin!==location.origin)throw Error("capture must be same-origin");
  const response=await fetch(url,{mode:"same-origin",redirect:"error"});
  if(!response.ok)throw Error("HTTP "+response.status);
  if(!url.pathname.endsWith(".gz"))return response.json();
  if(typeof DecompressionStream!=="function")throw Error("this browser cannot open gzip; download and decompress the original evidence");
  const decoded=response.body.pipeThrough(new DecompressionStream("gzip"));
  return new Response(decoded).json();
}
