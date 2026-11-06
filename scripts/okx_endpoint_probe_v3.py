import json,time,urllib.parse,urllib.request
tests=[
("okx_mark_price","https://www.okx.com/api/v5/public/mark-price",{"instType":"SWAP","instId":"BTC-USDT-SWAP"}),
("okx_index_ticker","https://www.okx.com/api/v5/market/index-tickers",{"quoteCcy":"USDT","instId":"BTC-USDT"}),
("okx_oi_history","https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-history",{"instId":"BTC-USDT-SWAP","period":"1H"}),
]
for name,base,params in tests:
 u=base+"?"+urllib.parse.urlencode(params);q=urllib.request.Request(u,headers={"User-Agent":"FuturesSignalAutopilot/5.0","Accept":"application/json"})
 try:
  with urllib.request.urlopen(q,timeout=12) as r:
   o=json.loads(r.read().decode());print(json.dumps({"name":name,"status":r.status,"code":o.get("code"),"data":o.get("data",[])[:3]}))
 except Exception as e:print(json.dumps({"name":name,"error":type(e).__name__,"detail":str(e)[:150]}))
