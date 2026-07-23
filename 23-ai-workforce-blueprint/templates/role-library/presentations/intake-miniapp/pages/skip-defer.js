/**
 * U057: Interview skip/defer bypass module.
 * Provides 1-hour dashboard bypass with persistent reminder banner.
 * Include: <script src="/s/skip-defer.js" defer></script>
 */
(function(){"use strict";var N="intake_skip_defer",S=3600;
function G(){var c=(document.cookie||"").split(";");for(var i=0;i<c.length;i++){var p=c[i].trim();if(p.indexOf(N+"=")===0)return p.substring(N.length+1)==="1"}return false}
function set(){document.cookie=N+"=1; max-age="+S+"; path=/; SameSite=Lax"}
function clr(){document.cookie=N+"=0; max-age=0; path=/; SameSite=Lax"}
function M(t,a,k){var e=document.createElement(t);a=a||{};Object.keys(a).forEach(function(x){if(x==="class")e.className=a[x];else if(x==="text")e.textContent=a[x];else if(x==="html")e.innerHTML=a[x];else if(x==="style")e.setAttribute("style",a[x]);else e.setAttribute(x,a[x])});(k||[]).forEach(function(c){if(c)e.appendChild(c)});return e}
function B(){var b=M("div",{class:"skip-banner"});b.appendChild(M("span",{text:"Your interview is not complete. Dashboard access is limited."}));var x=M("button",{"aria-label":"Dismiss"});x.innerHTML="&times;";x.onclick=function(){b.style.display="none"};b.appendChild(x);return b}
function MT(t,s){var d=M("div",{class:"dash-tile"});d.appendChild(M("div",{class:"dash-tile-title",text:t}));d.appendChild(M("div",{class:"dash-tile-subtitle",text:s}));return d}
function DASH(){
  var app=document.getElementById("app");if(!app)return;
  while(app.firstChild)app.removeChild(app.firstChild);
  var bar=document.getElementById("progress");if(bar)bar.style.width="100%";
  var banner=B();app.appendChild(banner);
  var card=M("div",{class:"card center"});
  card.appendChild(M("div",{class:"big",text:"Dashboard (Limited Access)"}));
  card.appendChild(M("p",{class:"help",text:"Interview skipped - access expires in 1 hour. When ready, complete your interview for full access."}));
  var row=M("div",{class:"row",style:"justify-content:center; gap:12px; margin-top:20px;"});
  var sb=M("button",{class:"primary",text:"Start interview"});sb.onclick=function(){clr();window.location.reload()};row.appendChild(sb);
  var db=M("button",{class:"ghost",text:"Dismiss for now"});db.onclick=function(){banner.style.display="none"};row.appendChild(db);
  card.appendChild(row);app.appendChild(card);
  var stub=M("div",{style:"max-width:640px; margin:20px auto; padding:0 18px;"});
  stub.appendChild(M("h2",{style:"font-size:18px; font-weight:650; color:var(--muted); margin-bottom:10px;",text:"Available panels"}));
  var tr=M("div",{style:"display:flex; flex-wrap:wrap; gap:12px;"});
  tr.appendChild(MT("System status","All systems operational"));tr.appendChild(MT("Recent activity","No recent activity"));tr.appendChild(MT("Message center","No new messages"));
  stub.appendChild(tr);app.appendChild(stub);
}
(function(){
  var s=document.createElement("style");s.textContent=".skip-banner{background:var(--accent,#f2b134);color:var(--accent-ink,#1c1c22);text-align:center;padding:12px 16px;font-size:14px;font-weight:600}.skip-banner button{margin-left:12px;background:transparent;color:inherit;border:1px solid currentColor;border-radius:50%;width:22px;height:22px;cursor:pointer;font-weight:700;line-height:1;vertical-align:middle}.dash-tile{flex:1;min-width:150px;background:var(--card,#fff);border:1px solid var(--line,#e6e6ee);border-radius:12px;padding:16px}.dash-tile-title{font-weight:650;font-size:14px;margin-bottom:4px}.dash-tile-subtitle{color:var(--muted,#6b6b78);font-size:13px}";document.head.appendChild(s);
  if(G()){
    var a=0;function ck(){a++;var app=document.getElementById("app");if(!app||a>20)return;if(!app.querySelector(".spin")&&app.children.length>0){DASH();return}setTimeout(ck,200)}setTimeout(ck,300);
  }
  var app=document.getElementById("app");if(!app)return;
  var obs=new MutationObserver(function(){setTimeout(ij,100)});obs.observe(app,{childList:true,subtree:true});setTimeout(ij,500);
  var done=false;
  function ij(){
    if(done)return;
    var cards=app.querySelectorAll(".card.center");
    for(var i=0;i<cards.length;i++){
      var c=cards[i];var h=c.querySelector(".big");
      if(!h||h.textContent!=="Hmm.")continue;
      if(c.querySelector(".skip-bypass-row"))return;
      var r=M("div",{class:"row skip-bypass-row",style:"justify-content:center; gap:12px;"});
      var sb=M("button",{class:"primary",text:"Skip for now"});sb.onclick=function(){set();DASH()};r.appendChild(sb);
      var rb=M("button",{class:"ghost",text:"Try again"});rb.onclick=function(){window.location.reload()};r.appendChild(rb);
      c.appendChild(r);c.appendChild(M("p",{class:"help",style:"font-size:13px;",text:"Skip lets you access the dashboard for 1 hour. A reminder banner will stay until your interview is complete."}));
      done=true;return;
    }
  }
})();})();
