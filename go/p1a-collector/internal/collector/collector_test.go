package collector

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestCollectUsesOKXAndSortsClosedCandles(t *testing.T) {
	now := time.Date(2026, 11, 11, 12, 7, 0, 0, time.UTC)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.Contains(r.URL.Path, "/api/v5/market/candles") { t.Fatalf("unexpected path %s", r.URL.Path) }
		w.Header().Set("Content-Type", "application/json")
		// 12:00 is still open; 11:45 and 11:30 are closed.
		_, _ = w.Write([]byte(`{"code":"0","data":[["1794408000000","3","4","2","3.5","10"],["1794407100000","2","3","1","2.5","9"]]}`))
	}))
	defer srv.Close()
	c := New(Config{OKXBaseURL:srv.URL, BybitBaseURL:srv.URL, HTTPClient:srv.Client(), Workers:2, Now:func()time.Time{return now}})
	got,err:=c.Collect(context.Background(),Request{Symbols:[]string{"BTCUSDT"},Timeframe:"15m",Limit:100})
	if err!=nil {t.Fatal(err)}
	if len(got.Results)!=1 || got.Results[0].Provider!="okx" || got.Results[0].Status!="OK" {t.Fatalf("unexpected result: %+v",got)}
	if len(got.Results[0].Candles)!=1 {t.Fatalf("expected only one closed candle, got %d",len(got.Results[0].Candles))}
}

func TestFallsBackPerSymbolWithoutMixing(t *testing.T) {
	now:=time.Date(2026,11,11,12,7,0,0,time.UTC)
	var okxCalls,bybitCalls int
	okx:=httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter,r *http.Request){okxCalls++;w.WriteHeader(451)}));defer okx.Close()
	bybit:=httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter,r *http.Request){
		bybitCalls++;w.Header().Set("Content-Type","application/json")
		_,_=w.Write([]byte(`{"retCode":0,"result":{"list":[["1794407100000","2","3","1","2.5","9"]]}}`))
	}));defer bybit.Close()
	c:=New(Config{OKXBaseURL:okx.URL,BybitBaseURL:bybit.URL,HTTPClient:bybit.Client(),Workers:1,Now:func()time.Time{return now}})
	got,err:=c.Collect(context.Background(),Request{Symbols:[]string{"ETHUSDT"},Limit:100})
	if err!=nil {t.Fatal(err)}
	if got.Results[0].Provider!="bybit" || got.Results[0].Status!="OK" {t.Fatalf("fallback failed: %+v",got.Results[0])}
	if okxCalls!=1 || bybitCalls!=1 {t.Fatalf("unexpected calls: okx=%d bybit=%d",okxCalls,bybitCalls)}
}

func TestRejectsDuplicateAndNonUSDT(t *testing.T) {
	c:=New(Config{})
	if _,err:=c.Collect(context.Background(),Request{Symbols:[]string{"BTCUSDT","BTCUSDT"}});err==nil {t.Fatal("duplicate symbol accepted")}
	if _,err:=c.Collect(context.Background(),Request{Symbols:[]string{"BTCUSD"}});err==nil {t.Fatal("non-USDT symbol accepted")}
}

func TestNoDataIsExplicitlyUnavailable(t *testing.T) {
	srv:=httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter,r *http.Request){w.Header().Set("Content-Type","application/json");_,_=w.Write([]byte(`{"code":"0","data":[]}`))}))
	defer srv.Close()
	c:=New(Config{OKXBaseURL:srv.URL,BybitBaseURL:srv.URL,HTTPClient:srv.Client()})
	got,err:=c.Collect(context.Background(),Request{Symbols:[]string{"SOLUSDT"}})
	if err!=nil {t.Fatal(err)}
	if got.Results[0].Status!="UNAVAILABLE" || len(got.Results[0].Candles)!=0 {t.Fatalf("bad unavailable state: %+v",got.Results[0])}
}
